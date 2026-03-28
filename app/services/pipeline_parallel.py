from __future__ import annotations

import math
import traceback
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import orjson

from app.normalizers.event_normalizer import normalize_record
from app.parsers.registry import ParserRegistry
from app.utils.files import detect_encoding


@dataclass(slots=True)
class PrescanFileResult:
    path: str
    file_name: str
    size_bytes: int
    suffix: str
    encoding: str
    parser_name: str
    supported: bool
    skip_reason: str | None = None


@dataclass(slots=True)
class ParseWorkerInput:
    path: str
    output_path: str
    parser_name_hint: str | None = None


@dataclass(slots=True)
class ParseWorkerResult:
    path: str
    output_path: str
    parser_name: str
    event_count: int
    ok: bool
    error: str | None = None
    traceback_text: str | None = None
    elapsed_seconds: float | None = None


PIPELINE_STAGE_PLAN: list[dict] = [
    {"stage": "discover", "mode": "serial", "reason": "目录扫描、去重与压缩包展开需要集中控制，避免临时目录冲突。"},
    {"stage": "prescan", "mode": "thread", "reason": "文件头读取、编码识别、parser 评分以 I/O 为主，适合线程池。"},
    {"stage": "parse_normalize", "mode": "process", "reason": "单文件解析、规则匹配、标准事件生成属于 CPU 密集阶段，适合多进程。"},
    {"stage": "aggregate", "mode": "serial", "reason": "跨文件关联、最终聚合、SQLite 写入统一放到主进程，保证一致性。"},
]


def prescan_file(path_str: str) -> dict:
    path = Path(path_str)
    try:
        encoding = detect_encoding(path)
    except Exception:
        encoding = "utf-8"

    try:
        registry = ParserRegistry()
        parser = registry.choose(path)
        parser_name = parser.name
        supported = True
        skip_reason = None
    except Exception as exc:
        parser_name = "unknown"
        supported = False
        skip_reason = str(exc)

    return asdict(
        PrescanFileResult(
            path=str(path),
            file_name=path.name,
            size_bytes=path.stat().st_size if path.exists() else 0,
            suffix=path.suffix.lower(),
            encoding=encoding,
            parser_name=parser_name,
            supported=supported,
            skip_reason=skip_reason,
        )
    )


def parse_file_to_jsonl(payload: dict) -> dict:
    import time

    ctx = ParseWorkerInput(**payload)
    path = Path(ctx.path)
    output_path = Path(ctx.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    try:
        registry = ParserRegistry()
        parser_name, generator = registry.parse_file(path)
        count = 0
        with output_path.open("wb") as fw:
            for record in generator:
                event = normalize_record(record).model_dump()
                fw.write(orjson.dumps(event))
                fw.write(b"\n")
                count += 1
        return asdict(
            ParseWorkerResult(
                path=str(path),
                output_path=str(output_path),
                parser_name=parser_name,
                event_count=count,
                ok=True,
                elapsed_seconds=round(time.perf_counter() - started, 4),
            )
        )
    except Exception as exc:
        return asdict(
            ParseWorkerResult(
                path=str(path),
                output_path=str(output_path),
                parser_name=ctx.parser_name_hint or "unknown",
                event_count=0,
                ok=False,
                error=str(exc),
                traceback_text=traceback.format_exc(limit=8),
                elapsed_seconds=round(time.perf_counter() - started, 4),
            )
        )


def iter_batches(items: list, batch_size: int) -> Iterable[list]:
    batch_size = max(1, int(batch_size))
    for idx in range(0, len(items), batch_size):
        yield items[idx : idx + batch_size]


def build_worker_output_path(intermediate_dir: Path, file_path: Path) -> Path:
    safe_stem = file_path.stem[:80] if file_path.stem else "file"
    return intermediate_dir / f"{safe_stem}_{uuid.uuid4().hex}.jsonl"


def resolve_parallel_workers(requested_cpu_cores: int | None, available_cpu_count: int, configured_max: int) -> int:
    requested = int(requested_cpu_cores or configured_max or 1)
    requested = max(1, requested)
    return max(1, min(requested, max(1, available_cpu_count), max(1, configured_max)))


def compute_optimal_parse_chunks(total_files: int, workers: int, configured_batch_size: int) -> int:
    """
    尽量让每个 worker 持续有活干，但避免提交过碎任务造成调度开销过高。
    """
    if total_files <= 0:
        return 1
    workers = max(1, workers)
    target = max(workers * 2, configured_batch_size)
    return max(1, min(total_files, target))
