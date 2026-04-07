from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from app.core.bootstrap import bootstrap_for_local_run
from app.core.settings import get_settings
from app.db.base import Base
from app.models.db_models import UploadTaskModel
from app.services.pipeline_parallel import (
    build_parse_dispatch_items,
    build_worker_output_path,
    parse_file_to_jsonl,
    prescan_file,
    prioritize_parse_dispatch,
)
from app.services.streaming_aggregation import StreamingAggregationCoordinator

bootstrap_for_local_run()


SCENARIOS: dict[str, dict[str, int]] = {
    "small": {"files": 2, "lines_per_file": 5_000},
    "medium": {"files": 8, "lines_per_file": 50_000},
    "large": {"files": 16, "lines_per_file": 250_000},
}


def _make_service_line(file_index: int, line_index: int) -> str:
    dt = datetime(2026, 4, 1, 8, 0, 0) + timedelta(milliseconds=(file_index * 10_000_000 + line_index * 10))
    ts = f"{dt:%Y-%m-%d %H:%M:%S}.{dt.microsecond // 1000:03d}"
    cycle = max(1, line_index // 200 + 1)
    source = f"D:\\Benchmark\\Workflow{file_index % 4}.cs:{100 + (line_index % 500)}"

    mod = line_index % 40
    if mod == 0:
        message = f"Current imaging cycle {cycle}"
        component = "Workflow"
        level = "INFO"
        method = "RunCycle"
    elif mod == 1:
        message = f"Move slide from imager to chuck stage start. N{(line_index % 8) + 1}"
        component = "Workflow"
        level = "INFO"
        method = "MoveSlide"
    elif mod == 2:
        message = f"Move slide from imager to chuck stage finished. N{(line_index % 8) + 1}"
        component = "Workflow"
        level = "INFO"
        method = "MoveSlide"
    elif mod == 3:
        message = f"FineAlign Completed in {2.0 + (line_index % 5) * 0.1:.1f} sec"
        component = "OpticalBoard"
        level = "INFO"
        method = "FineAlign"
    elif mod == 4:
        message = f"Timeout while moving stage {1000 + (line_index % 100)}"
        component = "Workflow"
        level = "ERROR"
        method = "RunCycle"
    else:
        message = f"SetCamDirection is success . {file_index}-{cycle}-{line_index % 16}"
        component = "Imager"
        level = "INFO"
        method = "SetCamDirection"

    return (
        f"{ts} | {component} | {level} | {line_index + 1} | Worker{file_index % 8} | "
        f"{message} | BenchmarkRunner | {method} | {source}\n"
    )


def _generate_inputs(root: Path, *, files: int, lines_per_file: int) -> list[Path]:
    input_dir = root / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for file_index in range(files):
        path = input_dir / f"bench_{file_index:03d}.log"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for line_index in range(lines_per_file):
                handle.write(_make_service_line(file_index, line_index))
        generated.append(path)
    return generated


def _worker_payload(item: dict[str, Any], intermediate_dir: Path) -> dict[str, Any]:
    chunk_index = int(item.get("chunk_index") or 0)
    return {
        "path": item["path"],
        "output_path": str(build_worker_output_path(intermediate_dir, Path(item["path"]), chunk_index=chunk_index)),
        "parser_name_hint": item.get("parser_name"),
        "encoding_hint": item.get("encoding"),
        "chunk_start": item.get("chunk_start"),
        "chunk_end": item.get("chunk_end"),
        "chunk_index": chunk_index,
    }


def _parse_stage(
    dispatch_items: list[dict[str, Any]],
    *,
    intermediate_dir: Path,
    settings,
    cpu_cores: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    worker_count = max(
        1,
        min(
            int(cpu_cores),
            int(settings.max_workers),
            int(settings.max_process_workers),
            len(dispatch_items),
        ),
    )
    if len({item["path"] for item in dispatch_items}) == len(dispatch_items):
        worker_count = min(worker_count, int(settings.file_level_workers))
    use_parallel = bool(settings.enable_process_pool and worker_count > 1 and dispatch_items)

    results: list[dict[str, Any]] = []
    if use_parallel:
        with ProcessPoolExecutor(max_workers=worker_count) as pool:
            future_map = {
                pool.submit(parse_file_to_jsonl, _worker_payload(item, intermediate_dir)): item for item in dispatch_items
            }
            for future in as_completed(future_map):
                results.append(future.result())
    else:
        for item in dispatch_items:
            results.append(parse_file_to_jsonl(_worker_payload(item, intermediate_dir)))

    results.sort(key=lambda item: (item["path"], int(item.get("chunk_index") or 0), item["output_path"]))
    elapsed = time.perf_counter() - started
    return results, {
        "elapsed_seconds": round(elapsed, 4),
        "worker_count": worker_count,
        "parallel_enabled": use_parallel,
        "dispatch_units": len(dispatch_items),
    }


def _run_single_benchmark(
    name: str,
    scenario: dict[str, int],
    *,
    compare_label: str,
    settings,
    cpu_cores: int,
) -> dict[str, Any]:
    work_root = Path(tempfile.mkdtemp(prefix=f"sequencer-bench-{name}-{compare_label}-"))
    db_path = work_root / "benchmark.sqlite3"
    intermediate_dir = work_root / "intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    try:
        files = _generate_inputs(work_root, files=int(scenario["files"]), lines_per_file=int(scenario["lines_per_file"]))
        input_bytes = sum(path.stat().st_size for path in files)

        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

        with SessionLocal() as db:
            task = UploadTaskModel(task_uuid=uuid.uuid4().hex, filename=f"{name}.zip", stored_path=str(work_root / "inputs"))
            db.add(task)
            db.commit()
            db.refresh(task)

            t0 = time.perf_counter()
            prescanned = [prescan_file(str(path)) for path in files]
            prescan_seconds = time.perf_counter() - t0

            t0 = time.perf_counter()
            dispatch_items = prioritize_parse_dispatch(
                build_parse_dispatch_items(
                    prescanned,
                    streaming_enabled=bool(settings.enable_streaming_parse),
                    chunk_bytes=int(settings.streaming_parse_chunk_bytes),
                    max_chunks_per_file=int(settings.max_parse_chunks_per_file),
                )
            )
            dispatch_plan_seconds = time.perf_counter() - t0

            parse_results, parse_meta = _parse_stage(
                dispatch_items,
                intermediate_dir=intermediate_dir,
                settings=settings,
                cpu_cores=cpu_cores,
            )

            coordinator = StreamingAggregationCoordinator(db, task.id, settings)
            coordinator.clear_existing_outputs()

            t0 = time.perf_counter()
            merge_result = coordinator.merge_intermediate_results(parse_results)
            merge_seconds = time.perf_counter() - t0

            t0 = time.perf_counter()
            cycle_context = coordinator.build_cycle_context(total_events=int(merge_result["total_events"]))
            cycle_context_seconds = time.perf_counter() - t0

            t0 = time.perf_counter()
            postprocess = coordinator.postprocess_and_aggregate(
                cycle_context,
                total_events=int(merge_result["total_events"]),
            )
            postprocess_seconds = time.perf_counter() - t0

            total_seconds = prescan_seconds + dispatch_plan_seconds + parse_meta["elapsed_seconds"] + merge_seconds + cycle_context_seconds + postprocess_seconds
            total_events = int(merge_result["total_events"])
            return {
                "scenario": name,
                "mode": compare_label,
                "input_files": len(files),
                "input_bytes": input_bytes,
                "lines": total_events,
                "cpu_cores": cpu_cores,
                "parallel_enabled": bool(parse_meta["parallel_enabled"]),
                "dispatch_units": int(parse_meta["dispatch_units"]),
                "chunked_units": int(sum(1 for item in dispatch_items if item.get("dispatch_kind") == "chunk")),
                "workers": int(parse_meta["worker_count"]),
                "timings": {
                    "prescan_seconds": round(prescan_seconds, 4),
                    "dispatch_plan_seconds": round(dispatch_plan_seconds, 4),
                    "parse_seconds": round(float(parse_meta["elapsed_seconds"]), 4),
                    "merge_seconds": round(merge_seconds, 4),
                    "cycle_context_seconds": round(cycle_context_seconds, 4),
                    "postprocess_seconds": round(postprocess_seconds, 4),
                    "total_seconds": round(total_seconds, 4),
                },
                "throughput": {
                    "lines_per_sec": round(total_events / max(total_seconds, 0.001), 2),
                    "parse_lines_per_sec": round(total_events / max(float(parse_meta["elapsed_seconds"]), 0.001), 2),
                    "files_per_sec": round(len(files) / max(total_seconds, 0.001), 2),
                },
                "final_counts": {
                    "total_errors": int(postprocess["total_errors"]),
                    "step_summary_count": int(postprocess["step_summary_count"]),
                    "parameter_result_count": int(postprocess["parameter_result_count"]),
                    "cluster_count": int(postprocess["cluster_count"]),
                },
                "memory_guard": postprocess["memory_guard"],
                "tuning": {
                    "enable_process_pool": bool(settings.enable_process_pool),
                    "enable_streaming_parse": bool(settings.enable_streaming_parse),
                    "max_workers": int(settings.max_workers),
                    "file_level_workers": int(settings.file_level_workers),
                    "streaming_parse_chunk_bytes": int(settings.streaming_parse_chunk_bytes),
                    "max_parse_chunks_per_file": int(settings.max_parse_chunks_per_file),
                    "db_batch_size": int(settings.db_batch_size),
                },
            }
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


def _format_compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_total = float(before["timings"]["total_seconds"])
    after_total = float(after["timings"]["total_seconds"])
    before_parse = float(before["timings"]["parse_seconds"])
    after_parse = float(after["timings"]["parse_seconds"])
    before_throughput = float(before["throughput"]["lines_per_sec"])
    after_throughput = float(after["throughput"]["lines_per_sec"])
    return {
        "speedup_total": round(before_total / max(after_total, 0.001), 2),
        "speedup_parse": round(before_parse / max(after_parse, 0.001), 2),
        "throughput_gain": round(after_throughput / max(before_throughput, 0.001), 2),
    }


def _print_summary(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the optimized parse/aggregate pipeline.")
    parser.add_argument(
        "--scenario",
        choices=["small", "medium", "large", "all"],
        default="all",
        help="Benchmark one scenario or all built-in scenarios.",
    )
    parser.add_argument("--cpu-cores", type=int, default=max(1, min(8, (os.cpu_count() or 4))), help="Worker ceiling.")
    parser.add_argument("--chunk-size-mb", type=int, default=16, help="Chunk size for streaming parse.")
    parser.add_argument("--db-batch-size", type=int, default=5000, help="SQLite insert batch size.")
    parser.add_argument("--max-workers", type=int, default=8, help="Max process workers.")
    parser.add_argument("--file-level-workers", type=int, default=4, help="File-level parallel workers.")
    parser.add_argument("--max-chunks-per-file", type=int, default=64, help="Chunk cap per input file.")
    parser.add_argument(
        "--compare-serial",
        action="store_true",
        help="Run a serial baseline first, then run the optimized configuration and print both.",
    )
    args = parser.parse_args()

    base_settings = get_settings()
    optimized_settings = base_settings.model_copy(
        update={
            "enable_process_pool": True,
            "enable_multiprocess_parse": True,
            "enable_streaming_parse": True,
            "max_workers": max(1, int(args.max_workers)),
            "file_level_workers": max(1, int(args.file_level_workers)),
            "streaming_parse_chunk_bytes": max(1, int(args.chunk_size_mb)) * 1024 * 1024,
            "max_parse_chunks_per_file": max(1, int(args.max_chunks_per_file)),
            "db_batch_size": max(100, int(args.db_batch_size)),
        }
    )
    baseline_settings = optimized_settings.model_copy(
        update={
            "enable_process_pool": False,
            "enable_multiprocess_parse": False,
            "enable_streaming_parse": False,
            "max_workers": 1,
            "file_level_workers": 1,
        }
    )

    scenario_names = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    rows: list[dict[str, Any]] = []
    for name in scenario_names:
        scenario = SCENARIOS[name]
        baseline = None
        if args.compare_serial:
            baseline = _run_single_benchmark(
                name,
                scenario,
                compare_label="baseline_serial",
                settings=baseline_settings,
                cpu_cores=1,
            )
            rows.append(baseline)

        optimized = _run_single_benchmark(
            name,
            scenario,
            compare_label="optimized",
            settings=optimized_settings,
            cpu_cores=max(1, int(args.cpu_cores)),
        )
        rows.append(optimized)

        if baseline is not None:
            rows.append(
                {
                    "scenario": name,
                    "mode": "comparison",
                    "comparison": _format_compare(baseline, optimized),
                }
            )

    _print_summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
