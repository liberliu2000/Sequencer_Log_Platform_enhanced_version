from __future__ import annotations

import gc
import os
import shutil
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson
from sqlalchemy.orm import Session

from app.core.logging_config import logger
from app.core.settings import get_settings
from app.correlators.pairing import pair_start_end
from app.db.session import SessionLocal
from app.detectors.error_detection import annotate_errors, top_error_clusters
from app.repositories.task_repository import TaskRepository
from app.schemas.common import NormalizedEvent
from app.services.cycle_inference import infer_missing_cycles
from app.services.cycle_service import aggregate_metric_steps, build_parameter_summaries
from app.services.performance_service import PerformanceService
from app.services.pipeline_parallel import (
    PIPELINE_STAGE_PLAN,
    build_worker_output_path,
    compute_optimal_parse_chunks,
    iter_batches,
    parse_file_to_jsonl,
    prescan_file,
    resolve_parallel_workers,
)
from app.services.task_state_cache import task_state_cache
from app.utils.files import ArchiveHandlingError, iter_supported_files, unpack_archive


class IngestionService:
    """
    性能优化边界：
    - I/O 密集：文件发现、压缩包展开、预扫描 -> 线程池
    - CPU 密集：单文件解析、规则匹配、标准事件转换 -> 进程池
    - 跨文件聚合、SQLite 写入 -> 主进程串行
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
            )

    def _discover_inputs(self, stored_root: Path, work_dir: Path, task_id: int, task_uuid: str, cpu_cores: int) -> list[Path]:
        collected_files: list[Path] = []
        upload_inputs = [p for p in stored_root.rglob("*") if p.is_file()] if stored_root.is_dir() else [stored_root]
        input_total = max(len(upload_inputs), 1)
        for idx, src in enumerate(upload_inputs, start=1):
            base_percent = 2 + int((idx - 1) / input_total * 10)
            self._progress(task_id, f"输入发现与解压 {idx}/{input_total}", base_percent, task_uuid=task_uuid, message=f"检查/解压: {src.name}", cpu_cores=cpu_cores)
            extracted = unpack_archive(
                src,
                work_dir / f"part_{idx}",
                progress_callback=lambda stage, p, base=base_percent: self._progress(
                    task_id, stage, min(14, base + int(p * 0.12)), task_uuid=task_uuid, cpu_cores=cpu_cores
                ),
            )
            collected_files.extend(extracted)
        files = iter_supported_files(collected_files)
        self.repo.add_audit_log(task_id, task_uuid, "discover_complete", "success", "输入发现", f"inputs={len(upload_inputs)}, extracted_files={len(files)}")
        return files

    def _prescan_files(self, files: list[Path], task_id: int, task_uuid: str, cpu_cores: int) -> list[dict]:
        if not files:
            return []
        total = len(files)
        workers = min(self.settings.prescan_thread_workers, self.settings.max_thread_workers, max(1, total))
        self._progress(task_id, "文件预扫描", 16, task_uuid=task_uuid, message=f"开始预扫描 {total} 个文件", file_count=total, cpu_cores=cpu_cores)

        results: list[dict] = []
        if self.settings.enable_threaded_prescan and total >= self.settings.parallel_min_files:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prescan") as pool:
                futures = {pool.submit(prescan_file, str(file_path)): file_path for file_path in files}
                for idx, future in enumerate(as_completed(futures), start=1):
                    payload = future.result()
                    results.append(payload)
                    pct = 16 + int(idx / total * 8)
                    self._progress(task_id, f"文件预扫描 {idx}/{total}", pct, task_uuid=task_uuid, message=f"{payload['file_name']} [{payload['parser_name']}/{payload['encoding']}]", file_count=total, cpu_cores=cpu_cores)
        else:
            for idx, file_path in enumerate(files, start=1):
                payload = prescan_file(str(file_path))
                results.append(payload)
                pct = 16 + int(idx / total * 8)
                self._progress(task_id, f"文件预扫描 {idx}/{total}", pct, task_uuid=task_uuid, message=f"{payload['file_name']} [{payload['parser_name']}/{payload['encoding']}]", file_count=total, cpu_cores=cpu_cores)
        return [r for r in results if r.get("supported")]

    def _parse_files_parallel(self, prescanned_files: list[dict], intermediate_dir: Path, task_id: int, task_uuid: str, cpu_cores: int) -> tuple[list[dict], dict]:
        if not prescanned_files:
            return [], {"worker_count": 0, "parallel_enabled": False, "parse_failures": 0}

        total_files = len(prescanned_files)
        use_parallel = self.settings.enable_multiprocess_parse and cpu_cores > 1 and total_files >= self.settings.parallel_min_files
        results: list[dict] = []
        failures: list[dict] = []
        worker_count = min(cpu_cores, self.settings.max_process_workers, self.settings.max_parallel_cpu_cores, total_files)

        if use_parallel:
            self._progress(task_id, "多进程解析与标准化", 26, task_uuid=task_uuid, message=f"启用多进程解析，workers={worker_count}", file_count=total_files, cpu_cores=worker_count)
            chunk_size = compute_optimal_parse_chunks(total_files, worker_count, self.settings.parse_batch_size)
            completed = 0
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                future_map = {}
                submitted = 0
                source_iter = iter(prescanned_files)

                def _submit_more(n: int) -> None:
                    nonlocal submitted
                    for _ in range(n):
                        try:
                            item = next(source_iter)
                        except StopIteration:
                            return
                        input_payload = {
                            "path": item["path"],
                            "output_path": str(build_worker_output_path(intermediate_dir, Path(item["path"]))),
                            "parser_name_hint": item.get("parser_name"),
                        }
                        fut = pool.submit(parse_file_to_jsonl, input_payload)
                        future_map[fut] = item
                        submitted += 1

                _submit_more(chunk_size)

                while future_map:
                    for future in as_completed(list(future_map.keys()), timeout=None):
                        item = future_map.pop(future)
                        payload = future.result()
                        completed += 1
                        if payload.get("ok"):
                            results.append(payload)
                            msg = f"{Path(payload['path']).name} [{payload['parser_name']}] events={payload['event_count']}"
                        else:
                            failures.append(item)
                            msg = f"{Path(payload['path']).name} 解析失败，待串行回退"
                        pct = 26 + int(completed / total_files * 34)
                        self._progress(task_id, f"多进程解析 {completed}/{total_files}", pct, task_uuid=task_uuid, message=msg, file_count=total_files, cpu_cores=worker_count)
                        _submit_more(1)
                        break
        else:
            self._progress(task_id, "串行解析与标准化", 26, task_uuid=task_uuid, message="文件数较少或禁用多进程，切换串行解析", file_count=total_files, cpu_cores=1)
            failures = list(prescanned_files)
            worker_count = 1

        # 串行回退，隔离失败文件
        for retry_round in range(self.settings.failed_worker_retries + 1):
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
                self._progress(task_id, f"串行回退解析 {idx}/{len(failures)}", 62 + int(idx / max(1, len(failures)) * 6), task_uuid=task_uuid, message=f"{Path(item['path']).name} 回退解析", file_count=total_files, cpu_cores=worker_count)
            failures = remaining

        if failures:
            self.repo.add_audit_log(task_id, task_uuid, "parse_partial_failures", "warning", "解析回退", f"unparsed_files={len(failures)}")

        results.sort(key=lambda x: x["path"])
        perf = {
            "worker_count": worker_count,
            "parallel_enabled": use_parallel,
            "parse_failures": len(failures),
            "parsed_files": len(results),
        }
        return results, perf

    def _load_events_from_intermediate(self, worker_results: list[dict], task_id: int, task_uuid: str, cpu_cores: int) -> list[NormalizedEvent]:
        total = max(len(worker_results), 1)
        all_events: list[NormalizedEvent] = []
        self._progress(task_id, "主进程汇总解析结果", 68, task_uuid=task_uuid, message=f"读取 {len(worker_results)} 个中间结果文件", cpu_cores=cpu_cores)
        for idx, batch in enumerate(iter_batches(worker_results, self.settings.load_batch_size), start=1):
            for item in batch:
                output_path = Path(item["output_path"])
                if not output_path.exists():
                    continue
                with output_path.open("rb") as fr:
                    for line in fr:
                        if not line.strip():
                            continue
                        payload = orjson.loads(line)
                        all_events.append(NormalizedEvent(**payload))
            pct = 68 + int((idx * self.settings.load_batch_size) / total * 6)
            self._progress(task_id, f"主进程汇总解析结果 {min(idx * self.settings.load_batch_size, total)}/{total}", min(74, pct), task_uuid=task_uuid, message=f"已合并 {min(idx * self.settings.load_batch_size, total)} 个文件中间结果", cpu_cores=cpu_cores)
        return all_events

    @staticmethod
    def _iter_event_rows(events: list[NormalizedEvent]):
        for event in events:
            payload = event.model_dump()
            payload["extra_json"] = orjson.dumps(payload.get("extra_json") or {}).decode("utf-8")
            yield payload

    @staticmethod
    def _collect_error_stats(events: list[NormalizedEvent]) -> tuple[int, dict[str, dict[str, int | None]]]:
        total_errors = 0
        bounds: dict[str, dict[str, int | None]] = {}
        for event in events:
            signature = event.normalized_signature
            if not signature:
                continue
            total_errors += 1
            epoch_ms = event.epoch_ms
            state = bounds.setdefault(signature, {"first": None, "last": None})
            if epoch_ms is None:
                continue
            if state["first"] is None or epoch_ms < int(state["first"]):
                state["first"] = epoch_ms
            if state["last"] is None or epoch_ms > int(state["last"]):
                state["last"] = epoch_ms
        return total_errors, bounds

    def process_task(self, task_id: int, stored_root: Path, task_uuid: str | None = None, cpu_cores: int | None = None) -> None:
        settings = get_settings()
        resolved_cores = resolve_parallel_workers(cpu_cores, os.cpu_count() or 1, settings.max_parallel_cpu_cores)
        if task_uuid:
            task_state_cache.mark_started(task_uuid)
            task_state_cache.update(task_uuid, status="processing", cpu_cores=resolved_cores, message=f"开始处理，CPU核心数={resolved_cores}")

        self._progress(task_id, "准备处理中", 1, task_uuid=task_uuid, message="开始创建本地工作区", cpu_cores=resolved_cores)
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
            "pipeline_stage_plan": PIPELINE_STAGE_PLAN,
        }
        overall_start = time.perf_counter()

        try:
            t0 = time.perf_counter(); files = self._discover_inputs(stored_root, work_dir, task_id, task_uuid or "", resolved_cores); stage_timing["file_scan_seconds"] = round(time.perf_counter()-t0, 4)
            candidate_file_count = len(files)
            self._progress(task_id, "文件识别完成", 15, task_uuid=task_uuid, message=f"识别到 {candidate_file_count} 个候选文件", file_count=candidate_file_count, cpu_cores=resolved_cores)

            t0 = time.perf_counter(); prescanned = self._prescan_files(files, task_id, task_uuid or "", resolved_cores); stage_timing["prescan_seconds"] = round(time.perf_counter()-t0, 4)
            perf_summary["prescanned_files"] = len(prescanned)

            t0 = time.perf_counter(); parse_results, parse_perf = self._parse_files_parallel(prescanned, intermediate_dir, task_id, task_uuid or "", resolved_cores); stage_timing["parse_seconds"] = round(time.perf_counter()-t0, 4)
            perf_summary.update(parse_perf)
            parsed_file_count = len(parse_results)
            del prescanned
            gc.collect()

            t0 = time.perf_counter(); all_events = self._load_events_from_intermediate(parse_results, task_id, task_uuid or "", resolved_cores); stage_timing["normalize_merge_seconds"] = round(time.perf_counter()-t0, 4)
            total_event_count = len(all_events)
            perf_summary["total_events_before_postprocess"] = total_event_count
            del parse_results
            gc.collect()

            self._progress(task_id, "cycle 推断与错误归一化", 76, task_uuid=task_uuid, message=f"已生成 {total_event_count} 条标准事件，开始跨文件关联", file_count=candidate_file_count, cpu_cores=resolved_cores)
            t0 = time.perf_counter(); all_events = infer_missing_cycles(all_events); all_events = annotate_errors(all_events); stage_timing["postprocess_seconds"] = round(time.perf_counter()-t0, 4)

            t0 = time.perf_counter()
            self.repo.save_events(task_id, self._iter_event_rows(all_events), batch_size=max(500, self.settings.metrics_batch_size * 4))
            stage_timing["db_write_events_seconds"] = round(time.perf_counter()-t0, 4)

            self._progress(task_id, "参数统计与 metrics 聚合", 84, task_uuid=task_uuid, message="开始 workflow 配对、metrics 聚合与各 cycle 参数统计", file_count=candidate_file_count, cpu_cores=resolved_cores)
            t0 = time.perf_counter(); paired_steps = pair_start_end(all_events); metric_steps = aggregate_metric_steps(all_events); base_steps = paired_steps + metric_steps; parameter_steps = build_parameter_summaries(all_events, base_steps); all_step_summaries = base_steps + parameter_steps; stage_timing["aggregate_seconds"] = round(time.perf_counter()-t0, 4)
            step_summary_count = len(all_step_summaries)
            if all_step_summaries:
                t0 = time.perf_counter(); self.repo.save_step_summaries(task_id, all_step_summaries, batch_size=max(500, self.settings.metrics_batch_size * 4)); stage_timing["db_write_steps_seconds"] = round(time.perf_counter()-t0, 4)
            del paired_steps, metric_steps, parameter_steps, base_steps, all_step_summaries
            gc.collect()

            self._progress(task_id, "错误簇预处理与图表数据预计算", 92, task_uuid=task_uuid, message="开始汇总错误簇与首页/图表基础数据", file_count=candidate_file_count, cpu_cores=resolved_cores)
            t0 = time.perf_counter(); total_errors, cluster_bounds = self._collect_error_stats(all_events); cluster_rows = top_error_clusters(all_events, limit=200); stage_timing["error_prep_seconds"] = round(time.perf_counter()-t0, 4)
            clusters = []
            for row in cluster_rows:
                signature = row["normalized_signature"]
                bounds = cluster_bounds.get(signature, {})
                clusters.append(
                    {
                        "normalized_signature": signature,
                        "error_family": row["error_family"],
                        "severity": row["severity"],
                        "representative_message": row["display_signature"],
                        "representative_exception": row["exception_type"],
                        "component": row["component"],
                        "count": row["count"],
                        "first_seen_epoch_ms": bounds.get("first"),
                        "last_seen_epoch_ms": bounds.get("last"),
                    }
                )
            cluster_count = len(clusters)
            if clusters:
                t0 = time.perf_counter(); self.repo.replace_error_clusters(task_id, clusters, batch_size=max(200, self.settings.metrics_batch_size * 2)); stage_timing["db_write_clusters_seconds"] = round(time.perf_counter()-t0, 4)

            self.repo.finalize_task(task_id, file_count=candidate_file_count, total_events=total_event_count, total_errors=total_errors)
            elapsed = round(time.perf_counter() - overall_start, 3)
            stage_timing["total_seconds"] = elapsed
            perf_summary["stage_timings"] = stage_timing
            perf_summary["final_counts"] = {
                "candidate_files": candidate_file_count,
                "parsed_files": parsed_file_count,
                "total_events": total_event_count,
                "total_errors": total_errors,
                "step_summaries": step_summary_count,
                "error_clusters": cluster_count,
            }
            del all_events, cluster_bounds, clusters
            gc.collect()
            if task_uuid:
                self.performance.write_summary(task_uuid, perf_summary)
                task_state_cache.update(task_uuid, status="completed", progress_percent=100, current_stage="已完成", file_count=candidate_file_count, message=f"处理完成，用时 {elapsed} 秒", cpu_cores=resolved_cores)
                task_state_cache.mark_finished(task_uuid, status="completed")
            self.repo.add_audit_log(task_id, task_uuid, "task_timing", "success", "性能摘要", orjson.dumps(perf_summary).decode("utf-8")[:4000])
        except ArchiveHandlingError as exc:
            logger.exception("archive_processing_failed", task_id=task_id, error=str(exc))
            self.repo.update_task_progress(task_id, status="failed", progress_percent=100, current_stage="解压失败", message=str(exc))
            if task_uuid:
                self.performance.write_summary(task_uuid, {"task_id": task_id, "task_uuid": task_uuid, "stage_timings": stage_timing, "failed_at_stage": "discover", "error": str(exc)})
                task_state_cache.update(task_uuid, status="failed", progress_percent=100, current_stage="解压失败", message=str(exc), cpu_cores=resolved_cores)
                task_state_cache.mark_finished(task_uuid, status="failed")
        except Exception as exc:
            logger.exception("task_processing_failed", task_id=task_id, error=str(exc))
            self.repo.update_task_progress(task_id, status="failed", progress_percent=100, current_stage="处理失败", message=str(exc))
            if task_uuid:
                self.performance.write_summary(task_uuid, {"task_id": task_id, "task_uuid": task_uuid, "stage_timings": stage_timing, "failed_at_stage": "runtime", "error": str(exc)})
                task_state_cache.update(task_uuid, status="failed", progress_percent=100, current_stage="处理失败", message=str(exc), cpu_cores=resolved_cores)
                task_state_cache.mark_finished(task_uuid, status="failed")
