from __future__ import annotations

import gc
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson
from sqlalchemy.orm import Session

from app.core.logging_config import logger
from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.repositories.task_repository import TaskRepository
from app.services.performance_service import PerformanceService
from app.services.pipeline_parallel import (
    PIPELINE_STAGE_PLAN,
    build_worker_output_path,
    compute_optimal_parse_chunks,
    parse_file_to_jsonl,
    prescan_file,
    resolve_parallel_workers,
)
from app.services.streaming_aggregation import StreamingAggregationCoordinator
from app.services.system_runtime_service import SystemRuntimeService
from app.services.task_state_cache import task_state_cache
from app.utils.files import ArchiveHandlingError, iter_supported_files, unpack_archive


class IngestionService:
    """
    Performance envelope:
    - I/O-heavy steps (discovery, archive expansion, prescan) stay lightweight.
    - CPU-heavy parsing uses a small adaptive process pool.
    - Cross-file merge/postprocess stays in the main process with streaming writes.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.repo = TaskRepository(db)
        self.performance = PerformanceService()

    @staticmethod
    def process_task_by_uuid(task_uuid: str, cpu_cores: int | None = None) -> None:
        db = SessionLocal()
        try:
            service = IngestionService(db)
            task = service.repo.get_task_by_uuid(task_uuid)
            if task:
                service.process_task(task.id, Path(task.stored_path), task_uuid=task_uuid, cpu_cores=cpu_cores)
        finally:
            db.close()

    def _progress(
        self,
        task_id: int,
        stage: str,
        percent: int,
        task_uuid: str | None = None,
        message: str | None = None,
        file_count: int | None = None,
        cpu_cores: int | None = None,
        runtime_snapshot: dict | None = None,
    ) -> None:
        self.repo.update_task_progress(
            task_id,
            status="processing",
            current_stage=stage,
            progress_percent=percent,
            message=message,
            file_count=file_count,
            queue_position=None,
        )
        if task_uuid:
            task_state_cache.update(
                task_uuid,
                status="processing",
                progress_percent=percent,
                current_stage=stage,
                message=message,
                file_count=file_count,
                queue_position=0,
                cpu_cores=cpu_cores,
                runtime_snapshot=runtime_snapshot,
            )

    def _discover_inputs(
        self,
        stored_root: Path,
        work_dir: Path,
        task_id: int,
        task_uuid: str,
        cpu_cores: int,
    ) -> list[Path]:
        collected_files: list[Path] = []
        upload_inputs = [p for p in stored_root.rglob("*") if p.is_file()] if stored_root.is_dir() else [stored_root]
        input_total = max(len(upload_inputs), 1)
        for idx, src in enumerate(upload_inputs, start=1):
            base_percent = 2 + int((idx - 1) / input_total * 10)
            self._progress(
                task_id,
                f"discovering_inputs {idx}/{input_total}",
                base_percent,
                task_uuid=task_uuid,
                message=f"checking archive/file: {src.name}",
                cpu_cores=cpu_cores,
            )
            extracted = unpack_archive(
                src,
                work_dir / f"part_{idx}",
                progress_callback=lambda stage, p, base=base_percent: self._progress(
                    task_id,
                    stage,
                    min(14, base + int(p * 0.12)),
                    task_uuid=task_uuid,
                    cpu_cores=cpu_cores,
                ),
            )
            collected_files.extend(extracted)
        files = iter_supported_files(collected_files)
        self.repo.add_audit_log(
            task_id,
            task_uuid,
            "discover_complete",
            "success",
            "discover_inputs",
            f"inputs={len(upload_inputs)}, extracted_files={len(files)}",
        )
        return files

    def _prescan_files(self, files: list[Path], task_id: int, task_uuid: str, cpu_cores: int) -> list[dict]:
        if not files:
            return []
        total = len(files)
        workers = min(self.settings.prescan_thread_workers, self.settings.max_thread_workers, max(1, total))
        self._progress(
            task_id,
            "prescanning_files",
            16,
            task_uuid=task_uuid,
            message=f"prescanning {total} file(s)",
            file_count=total,
            cpu_cores=cpu_cores,
        )

        results: list[dict] = []
        if self.settings.enable_threaded_prescan and total >= self.settings.parallel_min_files:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prescan") as pool:
                futures = {pool.submit(prescan_file, str(file_path)): file_path for file_path in files}
                for idx, future in enumerate(as_completed(futures), start=1):
                    payload = future.result()
                    results.append(payload)
                    pct = 16 + int(idx / total * 8)
                    self._progress(
                        task_id,
                        f"prescanning_files {idx}/{total}",
                        pct,
                        task_uuid=task_uuid,
                        message=f"{payload['file_name']} [{payload['parser_name']}/{payload['encoding']}]",
                        file_count=total,
                        cpu_cores=cpu_cores,
                    )
        else:
            for idx, file_path in enumerate(files, start=1):
                payload = prescan_file(str(file_path))
                results.append(payload)
                pct = 16 + int(idx / total * 8)
                self._progress(
                    task_id,
                    f"prescanning_files {idx}/{total}",
                    pct,
                    task_uuid=task_uuid,
                    message=f"{payload['file_name']} [{payload['parser_name']}/{payload['encoding']}]",
                    file_count=total,
                    cpu_cores=cpu_cores,
                )
        return [result for result in results if result.get("supported")]

    def _parse_files_parallel(
        self,
        prescanned_files: list[dict],
        intermediate_dir: Path,
        task_id: int,
        task_uuid: str,
        cpu_cores: int,
    ) -> tuple[list[dict], dict]:
        if not prescanned_files:
            return [], {"worker_count": 0, "parallel_enabled": False, "parse_failures": 0}

        total_files = len(prescanned_files)
        use_parallel = (
            self.settings.enable_multiprocess_parse and cpu_cores > 1 and total_files >= self.settings.parallel_min_files
        )
        results: list[dict] = []
        failures: list[dict] = []
        worker_count = min(cpu_cores, self.settings.max_process_workers, self.settings.max_parallel_cpu_cores, total_files)

        if use_parallel:
            self._progress(
                task_id,
                "parsing_files_parallel",
                26,
                task_uuid=task_uuid,
                message=f"parallel parse enabled, workers={worker_count}",
                file_count=total_files,
                cpu_cores=worker_count,
            )
            chunk_size = compute_optimal_parse_chunks(total_files, worker_count, self.settings.parse_batch_size)
            completed = 0
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                future_map = {}
                source_iter = iter(prescanned_files)

                def submit_more(batch_count: int) -> None:
                    for _ in range(batch_count):
                        try:
                            item = next(source_iter)
                        except StopIteration:
                            return
                        payload = {
                            "path": item["path"],
                            "output_path": str(build_worker_output_path(intermediate_dir, Path(item["path"]))),
                            "parser_name_hint": item.get("parser_name"),
                        }
                        future_map[pool.submit(parse_file_to_jsonl, payload)] = item

                submit_more(chunk_size)
                while future_map:
                    for future in as_completed(list(future_map.keys()), timeout=None):
                        item = future_map.pop(future)
                        payload = future.result()
                        completed += 1
                        if payload.get("ok"):
                            results.append(payload)
                            message = f"{Path(payload['path']).name} [{payload['parser_name']}] events={payload['event_count']}"
                        else:
                            failures.append(item)
                            message = f"{Path(payload['path']).name} failed, will retry serially"
                        pct = 26 + int(completed / total_files * 34)
                        self._progress(
                            task_id,
                            f"parsing_files_parallel {completed}/{total_files}",
                            pct,
                            task_uuid=task_uuid,
                            message=message,
                            file_count=total_files,
                            cpu_cores=worker_count,
                        )
                        submit_more(1)
                        break
        else:
            self._progress(
                task_id,
                "parsing_files_serial",
                26,
                task_uuid=task_uuid,
                message="switching to serial parse because file count is low or parallel parse is disabled",
                file_count=total_files,
                cpu_cores=1,
            )
            failures = list(prescanned_files)
            worker_count = 1

        for _retry_round in range(self.settings.failed_worker_retries + 1):
            if not failures:
                break
            remaining: list[dict] = []
            for idx, item in enumerate(failures, start=1):
                payload = parse_file_to_jsonl(
                    {
                        "path": item["path"],
                        "output_path": str(build_worker_output_path(intermediate_dir, Path(item["path"]))),
                        "parser_name_hint": item.get("parser_name"),
                    }
                )
                if payload.get("ok"):
                    results.append(payload)
                else:
                    remaining.append(item)
                self._progress(
                    task_id,
                    f"retrying_failed_parse {idx}/{len(failures)}",
                    62 + int(idx / max(1, len(failures)) * 6),
                    task_uuid=task_uuid,
                    message=f"{Path(item['path']).name} retried serially",
                    file_count=total_files,
                    cpu_cores=worker_count,
                )
            failures = remaining

        if failures:
            self.repo.add_audit_log(
                task_id,
                task_uuid,
                "parse_partial_failures",
                "warning",
                "parse_retry",
                f"unparsed_files={len(failures)}",
            )

        results.sort(key=lambda item: item["path"])
        return results, {
            "worker_count": worker_count,
            "parallel_enabled": use_parallel,
            "parse_failures": len(failures),
            "parsed_files": len(results),
        }

    def process_task(
        self,
        task_id: int,
        stored_root: Path,
        task_uuid: str | None = None,
        cpu_cores: int | None = None,
    ) -> None:
        settings = get_settings()
        runtime_service = SystemRuntimeService()
        cpu_plan = runtime_service.adaptive_cpu_allocation(cpu_cores, os.cpu_count() or 1, settings.max_parallel_cpu_cores)
        runtime_snapshot = cpu_plan.get("snapshot") if isinstance(cpu_plan.get("snapshot"), dict) else {}
        resolved_cores = resolve_parallel_workers(
            cpu_plan.get("recommended_cpu_cores"),
            os.cpu_count() or 1,
            settings.max_parallel_cpu_cores,
        )

        if task_uuid:
            task_state_cache.mark_started(task_uuid)
            startup_message = f"task started with {resolved_cores} CPU core(s)"
            if cpu_plan.get("reason") != "requested":
                startup_message = (
                    f"{startup_message}; degraded from {cpu_plan.get('requested_cpu_cores')} core(s) "
                    f"because of {cpu_plan.get('reason')}"
                )
            task_state_cache.update(
                task_uuid,
                status="processing",
                cpu_cores=resolved_cores,
                message=startup_message,
                runtime_snapshot=runtime_snapshot,
            )

        self._progress(
            task_id,
            "preparing_workspace",
            1,
            task_uuid=task_uuid,
            message="preparing isolated work directories",
            cpu_cores=resolved_cores,
            runtime_snapshot=runtime_snapshot,
        )

        work_dir = Path(self.settings.temp_dir) / f"work_{task_id}"
        intermediate_dir = Path(self.settings.intermediate_cache_dir) / f"task_{task_id}" / "parse_outputs"
        for path in (work_dir, intermediate_dir.parent):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)

        stage_timing: dict[str, float] = {}
        perf_summary: dict[str, object] = {
            "task_id": task_id,
            "task_uuid": task_uuid,
            "cpu_cores": resolved_cores,
            "runtime_allocation": {
                "requested_cpu_cores": cpu_plan.get("requested_cpu_cores"),
                "recommended_cpu_cores": resolved_cores,
                "reason": cpu_plan.get("reason"),
            },
            "pipeline_stage_plan": PIPELINE_STAGE_PLAN,
        }
        overall_start = time.perf_counter()

        try:
            started = time.perf_counter()
            files = self._discover_inputs(stored_root, work_dir, task_id, task_uuid or "", resolved_cores)
            stage_timing["file_scan_seconds"] = round(time.perf_counter() - started, 4)
            candidate_file_count = len(files)
            self._progress(
                task_id,
                "input_discovery_complete",
                15,
                task_uuid=task_uuid,
                message=f"discovered {candidate_file_count} candidate file(s)",
                file_count=candidate_file_count,
                cpu_cores=resolved_cores,
            )

            started = time.perf_counter()
            prescanned = self._prescan_files(files, task_id, task_uuid or "", resolved_cores)
            stage_timing["prescan_seconds"] = round(time.perf_counter() - started, 4)
            perf_summary["prescanned_files"] = len(prescanned)

            started = time.perf_counter()
            parse_results, parse_perf = self._parse_files_parallel(
                prescanned,
                intermediate_dir,
                task_id,
                task_uuid or "",
                resolved_cores,
            )
            stage_timing["parse_seconds"] = round(time.perf_counter() - started, 4)
            perf_summary.update(parse_perf)
            parsed_file_count = len(parse_results)
            del prescanned
            gc.collect()

            aggregator = StreamingAggregationCoordinator(self.db, task_id, self.settings)
            aggregator.clear_existing_outputs()
            started = time.perf_counter()
            merge_result = aggregator.merge_intermediate_results(
                parse_results,
                progress_callback=lambda stage, percent, message: self._progress(
                    task_id,
                    stage,
                    percent,
                    task_uuid=task_uuid,
                    message=message,
                    file_count=candidate_file_count,
                    cpu_cores=resolved_cores,
                ),
            )
            stage_timing["normalize_merge_seconds"] = round(time.perf_counter() - started, 4)
            total_event_count = int(merge_result["total_events"])
            perf_summary["total_events_before_postprocess"] = total_event_count
            del parse_results
            gc.collect()

            self._progress(
                task_id,
                "building_cycle_context",
                76,
                task_uuid=task_uuid,
                message=f"{total_event_count} normalized event(s) ready for cross-file correlation",
                file_count=candidate_file_count,
                cpu_cores=resolved_cores,
            )
            started = time.perf_counter()
            cycle_context = aggregator.build_cycle_context(
                total_events=total_event_count,
                progress_callback=lambda stage, percent, message: self._progress(
                    task_id,
                    stage,
                    percent,
                    task_uuid=task_uuid,
                    message=message,
                    file_count=candidate_file_count,
                    cpu_cores=resolved_cores,
                ),
            )
            stage_timing["cycle_context_seconds"] = round(time.perf_counter() - started, 4)

            self._progress(
                task_id,
                "streaming_postprocess_and_aggregation",
                84,
                task_uuid=task_uuid,
                message="streaming pair correlation, metric aggregation, parameter materialization and error clustering",
                file_count=candidate_file_count,
                cpu_cores=resolved_cores,
            )
            started = time.perf_counter()
            postprocess_result = aggregator.postprocess_and_aggregate(
                cycle_context,
                total_events=total_event_count,
                progress_callback=lambda stage, percent, message: self._progress(
                    task_id,
                    stage,
                    percent,
                    task_uuid=task_uuid,
                    message=message,
                    file_count=candidate_file_count,
                    cpu_cores=resolved_cores,
                ),
            )
            stage_timing["postprocess_seconds"] = round(time.perf_counter() - started, 4)
            stage_timing.update(postprocess_result["timings"])
            perf_summary["memory_guard"] = postprocess_result["memory_guard"]
            total_errors = int(postprocess_result["total_errors"])
            step_summary_count = int(postprocess_result["step_summary_count"])
            parameter_result_count = int(postprocess_result.get("parameter_result_count") or 0)
            cluster_count = int(postprocess_result["cluster_count"])
            gc.collect()

            self._progress(
                task_id,
                "finalizing_dashboard_payload",
                92,
                task_uuid=task_uuid,
                message="preparing dashboard-safe summary data",
                file_count=candidate_file_count,
                cpu_cores=resolved_cores,
            )
            stage_timing.setdefault("error_prep_seconds", 0.0)

            self.repo.finalize_task(
                task_id,
                file_count=candidate_file_count,
                total_events=total_event_count,
                total_errors=total_errors,
            )
            elapsed = round(time.perf_counter() - overall_start, 3)
            stage_timing["total_seconds"] = elapsed
            perf_summary["stage_timings"] = stage_timing
            perf_summary["final_counts"] = {
                "candidate_files": candidate_file_count,
                "parsed_files": parsed_file_count,
                "total_events": total_event_count,
                "total_errors": total_errors,
                "step_summaries": step_summary_count,
                "parameter_results": parameter_result_count,
                "error_clusters": cluster_count,
            }
            gc.collect()

            if task_uuid:
                task_state_cache.update(
                    task_uuid,
                    status="completed",
                    progress_percent=100,
                    current_stage="completed",
                    file_count=candidate_file_count,
                    total_events=total_event_count,
                    total_errors=total_errors,
                    queue_position=0,
                    message=f"processing finished in {elapsed} second(s)",
                    cpu_cores=resolved_cores,
                )
                task_state_cache.mark_finished(task_uuid, status="completed")
                state_snapshot = task_state_cache.get(task_uuid) or {}
                perf_summary["progress_history"] = state_snapshot.get("progress_history", [])
                perf_summary["status_snapshot"] = state_snapshot
                self.performance.write_summary(task_uuid, perf_summary)

            self.repo.add_audit_log(
                task_id,
                task_uuid,
                "task_timing",
                "success",
                "performance_summary",
                orjson.dumps(perf_summary).decode("utf-8")[:4000],
            )
        except ArchiveHandlingError as exc:
            logger.exception("archive_processing_failed", task_id=task_id, error=str(exc))
            self.repo.update_task_progress(
                task_id,
                status="failed",
                progress_percent=100,
                current_stage="archive_failed",
                message=str(exc),
            )
            if task_uuid:
                task_state_cache.update(
                    task_uuid,
                    status="failed",
                    progress_percent=100,
                    current_stage="archive_failed",
                    message=str(exc),
                    cpu_cores=resolved_cores,
                )
                task_state_cache.mark_finished(task_uuid, status="failed")
                failure_snapshot = task_state_cache.get(task_uuid) or {}
                self.performance.write_summary(
                    task_uuid,
                    {
                        "task_id": task_id,
                        "task_uuid": task_uuid,
                        "stage_timings": stage_timing,
                        "failed_at_stage": "discover",
                        "error": str(exc),
                        "progress_history": failure_snapshot.get("progress_history", []),
                        "status_snapshot": failure_snapshot,
                    },
                )
        except Exception as exc:
            logger.exception("task_processing_failed", task_id=task_id, error=str(exc))
            self.repo.update_task_progress(
                task_id,
                status="failed",
                progress_percent=100,
                current_stage="processing_failed",
                message=str(exc),
            )
            if task_uuid:
                task_state_cache.update(
                    task_uuid,
                    status="failed",
                    progress_percent=100,
                    current_stage="processing_failed",
                    message=str(exc),
                    cpu_cores=resolved_cores,
                )
                task_state_cache.mark_finished(task_uuid, status="failed")
                failure_snapshot = task_state_cache.get(task_uuid) or {}
                self.performance.write_summary(
                    task_uuid,
                    {
                        "task_id": task_id,
                        "task_uuid": task_uuid,
                        "stage_timings": stage_timing,
                        "failed_at_stage": "runtime",
                        "error": str(exc),
                        "progress_history": failure_snapshot.get("progress_history", []),
                        "status_snapshot": failure_snapshot,
                    },
                )
