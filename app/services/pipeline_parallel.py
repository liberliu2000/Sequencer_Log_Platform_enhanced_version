from __future__ import annotations

import traceback
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import orjson

from app.normalizers.event_normalizer import normalize_record_fast
from app.parsers.registry import ParserRegistry
from app.utils.files import detect_encoding


CHUNKABLE_PARSERS = {"service_log"}


@dataclass(slots=True)
class PrescanFileResult:
    path: str
    file_name: str
    size_bytes: int
    suffix: str
    encoding: str
    parser_name: str
    supported: bool
    chunk_capable: bool
    skip_reason: str | None = None


@dataclass(slots=True)
class ParseWorkerInput:
    path: str
    output_path: str
    parser_name_hint: str | None = None
    encoding_hint: str | None = None
    chunk_start: int | None = None
    chunk_end: int | None = None
    chunk_index: int = 0


@dataclass(slots=True)
class ParseWorkerResult:
    path: str
    output_path: str
    parser_name: str
    event_count: int
    ok: bool
    chunk_index: int = 0
    chunk_start: int | None = None
    chunk_end: int | None = None
    bytes_processed: int = 0
    error: str | None = None
    traceback_text: str | None = None
    elapsed_seconds: float | None = None


PIPELINE_STAGE_PLAN: list[dict] = [
    {"stage": "discover", "mode": "serial", "reason": "archive expansion and workspace preparation remain centralized"},
    {"stage": "prescan", "mode": "thread", "reason": "lightweight I/O and parser scoring scale well with threads"},
    {"stage": "parse_normalize", "mode": "process", "reason": "regex, time parsing, and normalization are CPU-heavy"},
    {"stage": "aggregate", "mode": "serial", "reason": "SQLite stays single-writer while the main process streams and batches writes"},
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
        chunk_capable = bool(getattr(parser, "supports_parallel_chunks", False))
        skip_reason = None
    except Exception as exc:
        parser_name = "unknown"
        supported = False
        chunk_capable = False
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
            chunk_capable=chunk_capable and parser_name in CHUNKABLE_PARSERS,
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
    bytes_processed = 0

    try:
        registry = ParserRegistry()
        parser_name, generator = registry.parse_file(
            path,
            parser_name_hint=ctx.parser_name_hint,
            encoding_hint=ctx.encoding_hint,
            chunk_start=ctx.chunk_start,
            chunk_end=ctx.chunk_end,
        )
        count = 0
        with output_path.open("wb") as fw:
            for record in generator:
                event = normalize_record_fast(record)
                raw = orjson.dumps(event)
                fw.write(raw)
                fw.write(b"\n")
                bytes_processed += len(raw) + 1
                count += 1
        return asdict(
            ParseWorkerResult(
                path=str(path),
                output_path=str(output_path),
                parser_name=parser_name,
                event_count=count,
                ok=True,
                chunk_index=ctx.chunk_index,
                chunk_start=ctx.chunk_start,
                chunk_end=ctx.chunk_end,
                bytes_processed=bytes_processed,
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
                chunk_index=ctx.chunk_index,
                chunk_start=ctx.chunk_start,
                chunk_end=ctx.chunk_end,
                bytes_processed=bytes_processed,
                error=str(exc),
                traceback_text=traceback.format_exc(limit=8),
                elapsed_seconds=round(time.perf_counter() - started, 4),
            )
        )


def iter_batches(items: list, batch_size: int) -> Iterable[list]:
    batch_size = max(1, int(batch_size))
    for idx in range(0, len(items), batch_size):
        yield items[idx : idx + batch_size]


def build_worker_output_path(intermediate_dir: Path, file_path: Path, *, chunk_index: int = 0) -> Path:
    safe_stem = file_path.stem[:80] if file_path.stem else "file"
    suffix = f"_part{chunk_index:05d}" if chunk_index > 0 else ""
    return intermediate_dir / f"{safe_stem}{suffix}_{uuid.uuid4().hex}.jsonl"


def build_parse_dispatch_items(
    prescanned_files: list[dict],
    *,
    streaming_enabled: bool,
    chunk_bytes: int,
    max_chunks_per_file: int,
) -> list[dict]:
    items: list[dict] = []
    chunk_bytes = max(1, int(chunk_bytes or 1))
    max_chunks_per_file = max(1, int(max_chunks_per_file or 1))

    for file_order, item in enumerate(prescanned_files):
        size_bytes = max(0, int(item.get("size_bytes") or 0))
        chunk_capable = bool(item.get("chunk_capable"))
        if streaming_enabled and chunk_capable and size_bytes > chunk_bytes:
            chunk_count = min(max_chunks_per_file, max(2, (size_bytes + chunk_bytes - 1) // chunk_bytes))
            boundaries = [int(round(size_bytes * idx / chunk_count)) for idx in range(chunk_count + 1)]
            for chunk_index in range(chunk_count):
                start = boundaries[chunk_index]
                end = boundaries[chunk_index + 1]
                items.append(
                    {
                        **item,
                        "dispatch_order": file_order,
                        "chunk_index": chunk_index,
                        "chunk_start": start,
                        "chunk_end": end,
                        "size_bytes": max(1, end - start),
                        "dispatch_kind": "chunk",
                    }
                )
        else:
            items.append(
                {
                    **item,
                    "dispatch_order": file_order,
                    "chunk_index": 0,
                    "chunk_start": None,
                    "chunk_end": None,
                    "dispatch_kind": "file",
                }
            )
    return items


def parse_item_weight(item: dict) -> int:
    try:
        size_bytes = int(item.get("size_bytes") or 0)
    except (AttributeError, TypeError, ValueError):
        size_bytes = 0
    return max(1, size_bytes)


def prioritize_parse_dispatch(items: list[dict]) -> list[dict]:
    """
    Dispatch larger work units first to reduce tail latency at the end of the parse stage.
    """

    return sorted(
        items,
        key=lambda item: (
            -parse_item_weight(item),
            str(item.get("path") or ""),
            int(item.get("chunk_index") or 0),
        ),
    )


def compute_weighted_progress(
    completed_weight: int,
    total_weight: int,
    start_percent: int,
    span_percent: int,
) -> int:
    if total_weight <= 0:
        return max(0, min(100, int(start_percent)))
    ratio = min(max(completed_weight / total_weight, 0.0), 1.0)
    return max(0, min(100, int(start_percent) + int(ratio * int(span_percent))))


def resolve_parallel_workers(requested_cpu_cores: int | None, available_cpu_count: int, configured_max: int) -> int:
    requested = int(requested_cpu_cores or configured_max or 1)
    requested = max(1, requested)
    return max(1, min(requested, max(1, available_cpu_count), max(1, configured_max)))


def compute_optimal_parse_chunks(total_files: int, workers: int, configured_batch_size: int) -> int:
    if total_files <= 0:
        return 1
    workers = max(1, workers)
    prefetch_floor = workers * 2
    prefetch_cap = max(prefetch_floor, workers * 4)
    requested = max(1, int(configured_batch_size or prefetch_floor))
    target = min(max(prefetch_floor, requested), prefetch_cap)
    return max(1, min(total_files, target))
