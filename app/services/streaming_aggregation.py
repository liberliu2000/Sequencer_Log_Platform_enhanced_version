from __future__ import annotations

import gc
import heapq
import os
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import orjson
from sqlalchemy import and_, bindparam, delete, func, insert, or_, select, update
from sqlalchemy.orm import Session

from app.correlators.pairing import (
    _derive_duration_ms,
    _heartbeat_bounds,
    _is_pairable,
    _mark_heartbeat_progress,
    build_group_key,
    is_running_status_message,
    get_step_threshold_ms,
    normalize_step_key,
)
from app.detectors.error_detection import normalize_error_signature
from app.models.db_models import ErrorClusterModel, NormalizedEventModel, ParameterResultModel, StepSummaryModel
from app.schemas.common import ParameterResult
from app.services.cycle_inference import CURRENT_CYCLE_HINTS, NEXT_CYCLE_HINTS
from app.services.side_registry import TaskSideRegistry
from app.services.cycle_service import (
    collapse_cycle_time_results,
    _definition_values,
    _event_time_text,
    _extract_cycle_from_match,
    _extract_float_from_groups,
    _extract_slide_from_match,
    _extract_slide_name,
    _mk_result,
    _safe_seconds,
)
from app.services.parameter_definitions import DIRECT_DURATION_RULES, PAIRING_RULES, ROW_SCAN_METRIC_STAGES
from app.utils.side_inference import ScopeInference, infer_scope_from_texts, infer_side_group, prefer_specific_side
from app.utils.rules import load_yaml

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    psutil = None

try:
    import resource  # type: ignore
except Exception:  # pragma: no cover - Windows fallback
    resource = None


ProgressCallback = Callable[[str, int, str | None], None]

EVENT_INSERT_FIELDS = tuple(column.name for column in NormalizedEventModel.__table__.columns if column.name != "id")
STEP_INSERT_FIELDS = tuple(column.name for column in StepSummaryModel.__table__.columns if column.name != "id")
CLUSTER_INSERT_FIELDS = tuple(column.name for column in ErrorClusterModel.__table__.columns if column.name != "id")
PARAMETER_RESULT_INSERT_FIELDS = tuple(column.name for column in ParameterResultModel.__table__.columns if column.name != "id")


@dataclass(slots=True)
class MutableEvent:
    source_file: str
    parser_name: str
    original_time_text: str | None = None
    parsed_datetime: datetime | None = None
    epoch_ms: int | None = None
    formatted_ms: str | None = None
    level: str = "INFO"
    component: str | None = None
    module: str | None = None
    thread: str | None = None
    method_name: str | None = None
    class_name: str | None = None
    source_path: str | None = None
    line_no: int | None = None
    message: str = ""
    raw_text: str = ""
    cycle_no: int | None = None
    sub_step: str | None = None
    instrument_scope: str | None = None
    side_scope: str | None = None
    side_group: str | None = None
    chip_name: str | None = None
    chip_position: str | None = None
    chuck_no: str | None = None
    slot_no: str | None = None
    stage_key: str | None = None
    stage_name: str | None = None
    board_name: str | None = None
    event_kind: str | None = None
    direction: str | None = None
    duration_ms: float | None = None
    status: str | None = None
    error_code: str | None = None
    exception_type: str | None = None
    normalized_signature: str | None = None
    error_family: str | None = None
    severity: str | None = None
    cycle_inferred: bool = False
    cycle_infer_method: str | None = None
    cycle_infer_confidence: str | None = None
    cycle_infer_reason: str | None = None
    side_confidence: float | None = None
    side_evidence: dict[str, Any] = field(default_factory=dict)
    extra_json: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnchorPoint:
    position: int
    cycle_no: int
    epoch_ms: int | None


@dataclass(slots=True)
class CycleInferenceContext:
    anchors: list[AnchorPoint]
    anchor_positions: list[int]
    component_cycle_votes: dict[tuple[str | None, str | None], Counter]
    total_events: int
    side_registry: TaskSideRegistry


@dataclass(slots=True)
class MemoryGuardState:
    merge_insert_batch: int
    update_batch: int
    step_insert_batch: int
    cluster_insert_batch: int
    trigger_count: int = 0
    stage_hits: dict[str, int] = field(default_factory=dict)
    last_snapshot: dict[str, Any] = field(default_factory=dict)
    last_reasons: list[str] = field(default_factory=list)


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _coerce_extra_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            loaded = orjson.loads(value)
        except orjson.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    text = str(value).strip()
    if not text:
        return {}
    try:
        loaded = orjson.loads(text)
    except orjson.JSONDecodeError:
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def _json_text(value: dict[str, Any] | None) -> str:
    return orjson.dumps(value or {}).decode("utf-8")


def _round_mb(value: int | float | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 1024 / 1024, 1)
    except Exception:
        return None


def _apply_cycle_mark(
    event: MutableEvent,
    inferred: bool,
    method: str,
    confidence: str,
    *,
    reason: str | None = None,
    cycle_no: int | None = None,
) -> None:
    extra = dict(event.extra_json or {})
    extra["cycle_inferred"] = inferred
    extra["cycle_infer_method"] = method
    extra["cycle_infer_confidence"] = confidence
    event.cycle_inferred = inferred
    event.cycle_infer_method = method
    event.cycle_infer_confidence = confidence
    event.cycle_infer_reason = reason
    if reason:
        extra["cycle_infer_reason"] = reason
    if cycle_no is not None:
        event.cycle_no = cycle_no
    event.extra_json = extra


class StreamingAggregationCoordinator:
    def __init__(self, db: Session, task_id: int, settings) -> None:
        self.db = db
        self.task_id = task_id
        self.settings = settings
        self.thresholds = load_yaml(settings.thresholds_path)
        self.scan_batch_size = max(200, int(settings.metrics_batch_size) * 4)
        event_batch = max(500, int(getattr(settings, "db_batch_size", settings.metrics_batch_size)))
        self.guard = MemoryGuardState(
            merge_insert_batch=event_batch,
            update_batch=max(250, event_batch // 2),
            step_insert_batch=event_batch,
            cluster_insert_batch=max(200, event_batch // 2),
        )
        self._intermediate_results: list[dict[str, Any]] = []

    def clear_existing_outputs(self) -> None:
        self.db.execute(delete(ErrorClusterModel).where(ErrorClusterModel.task_id == self.task_id))
        self.db.execute(delete(ParameterResultModel).where(ParameterResultModel.task_id == self.task_id))
        self.db.execute(delete(StepSummaryModel).where(StepSummaryModel.task_id == self.task_id))
        self.db.execute(delete(NormalizedEventModel).where(NormalizedEventModel.task_id == self.task_id))
        self.db.commit()
        self._intermediate_results = []

    def merge_intermediate_results(
        self,
        worker_results: list[dict],
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        ordered_results = sorted(
            worker_results,
            key=lambda item: (
                str(item.get("path") or ""),
                int(item.get("chunk_index") or 0),
                str(item.get("output_path") or ""),
            ),
        )
        total_files = max(len(ordered_results), 1)
        processed_files = 0
        total_events = 0
        total_bytes = 0
        started = time.perf_counter()

        self._intermediate_results = ordered_results

        for item in ordered_results:
            output_path = Path(str(item.get("output_path") or ""))
            if output_path.exists():
                total_bytes += int(output_path.stat().st_size)
                if item.get("event_count") is not None:
                    total_events += int(item.get("event_count") or 0)
                else:
                    with output_path.open("rb") as handle:
                        total_events += sum(1 for line in handle if line.strip())

            processed_files += 1
            if progress_callback:
                progress = 68 + int(processed_files / total_files * 6)
                progress_callback(
                    f"registering_parse_outputs {processed_files}/{len(ordered_results)}",
                    min(74, progress),
                    f"registered {processed_files} intermediate shard(s) for ordered streaming merge",
                )
            self._apply_memory_guard("merge", collect=False)

        return {
            "total_events": total_events,
            "processed_files": processed_files,
            "stream_count": len(ordered_results),
            "intermediate_bytes": total_bytes,
            "elapsed_seconds": round(time.perf_counter() - started, 4),
            "memory_guard": self.memory_guard_report(),
        }

        total_files = max(len(worker_results), 1)
        processed_files = 0
        total_events = 0
        insert_buffer: list[dict[str, Any]] = []
        started = time.perf_counter()

        for item in worker_results:
            output_path = Path(str(item.get("output_path") or ""))
            if output_path.exists():
                with output_path.open("rb") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        payload = orjson.loads(line)
                        insert_buffer.append(self._prepare_event_insert(payload))
                        total_events += 1
                        if len(insert_buffer) >= self.guard.merge_insert_batch:
                            self._flush_event_inserts(insert_buffer)
                            insert_buffer.clear()
                            self._apply_memory_guard("merge")
                output_path.unlink(missing_ok=True)

            processed_files += 1
            if progress_callback:
                progress = 68 + int(processed_files / total_files * 6)
                progress_callback(
                    f"主进程汇总解析结果 {processed_files}/{len(worker_results)}",
                    min(74, progress),
                    f"已流式合并 {processed_files} 个中间结果文件",
                )

        if insert_buffer:
            self._flush_event_inserts(insert_buffer)
            insert_buffer.clear()
            self._apply_memory_guard("merge")

        return {
            "total_events": total_events,
            "processed_files": processed_files,
            "elapsed_seconds": round(time.perf_counter() - started, 4),
            "memory_guard": self.memory_guard_report(),
        }

    def build_cycle_context(
        self,
        *,
        total_events: int,
        progress_callback: ProgressCallback | None = None,
    ) -> CycleInferenceContext:
        anchors: list[AnchorPoint] = []
        component_cycle_votes: dict[tuple[str | None, str | None], Counter] = defaultdict(Counter)
        side_registry = TaskSideRegistry()
        processed = 0

        for payload in self._iter_intermediate_event_payloads():
            cycle_no = payload.get("cycle_no")
            if cycle_no is not None:
                anchors.append(
                    AnchorPoint(
                        position=processed,
                        cycle_no=int(cycle_no),
                        epoch_ms=self._to_int(payload.get("epoch_ms")),
                    )
                )
                component_cycle_votes[(payload.get("component"), payload.get("sub_step"))][int(cycle_no)] += 1

            side_registry.observe_event(
                source_file=str(payload.get("source_file") or ""),
                message=str(payload.get("message") or ""),
                raw_text=str(payload.get("raw_text") or payload.get("message") or ""),
                chip_name=payload.get("chip_name"),
                stage_name=payload.get("stage_name"),
                extra=_coerce_extra_json(payload.get("extra_json")),
            )
            processed += 1

            if processed % self.scan_batch_size == 0:
                if progress_callback and total_events > 0:
                    percent = 76 + int(processed / total_events * 4)
                    progress_callback(
                        f"building_cycle_context {min(processed, total_events)}/{total_events}",
                        min(80, percent),
                        "scanning ordered events to build cycle anchors and side registry",
                    )
                self._apply_memory_guard("cycle_context", collect=False)

        if progress_callback and total_events > 0:
            progress_callback(
                f"building_cycle_context {min(processed, total_events)}/{total_events}",
                80,
                "cycle anchor scan completed",
            )

        return CycleInferenceContext(
            anchors=anchors,
            anchor_positions=[anchor.position for anchor in anchors],
            component_cycle_votes=component_cycle_votes,
            total_events=processed,
            side_registry=side_registry,
        )

        anchors: list[AnchorPoint] = []
        component_cycle_votes: dict[tuple[str | None, str | None], Counter] = defaultdict(Counter)
        side_registry = TaskSideRegistry()
        processed = 0

        columns = (
            NormalizedEventModel.id,
            NormalizedEventModel.epoch_ms,
            NormalizedEventModel.source_file,
            NormalizedEventModel.message,
            NormalizedEventModel.raw_text,
            NormalizedEventModel.cycle_no,
            NormalizedEventModel.component,
            NormalizedEventModel.chip_name,
            NormalizedEventModel.stage_name,
            NormalizedEventModel.extra_json,
            NormalizedEventModel.sub_step,
        )

        for rows in self._iter_event_batches(columns=columns, limit=self.scan_batch_size):
            for row in rows:
                cycle_no = row["cycle_no"]
                if cycle_no is not None:
                    anchors.append(
                        AnchorPoint(
                            position=processed,
                            cycle_no=int(cycle_no),
                            epoch_ms=row["epoch_ms"],
                        )
                    )
                    component_cycle_votes[(row["component"], row["sub_step"])][int(cycle_no)] += 1
                side_registry.observe_event(
                    source_file=row["source_file"],
                    message=row["message"],
                    raw_text=row["raw_text"],
                    chip_name=row["chip_name"],
                    stage_name=row["stage_name"],
                    extra=_coerce_extra_json(row["extra_json"]),
                )
                processed += 1

            if progress_callback and total_events > 0:
                percent = 76 + int(processed / total_events * 4)
                progress_callback(
                    f"cycle 推断上下文构建 {min(processed, total_events)}/{total_events}",
                    min(80, percent),
                    "正在扫描已落库事件并建立 cycle 锚点索引",
                )
            self._apply_memory_guard("cycle_context", collect=False)

        return CycleInferenceContext(
            anchors=anchors,
            anchor_positions=[anchor.position for anchor in anchors],
            component_cycle_votes=component_cycle_votes,
            total_events=processed,
            side_registry=side_registry,
        )

    def postprocess_and_aggregate(
        self,
        context: CycleInferenceContext,
        *,
        total_events: int,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        event_buffer: list[dict[str, Any]] = []
        step_buffer: list[dict[str, Any]] = []
        pairing_state: dict[tuple[str | None, int | None, str | None, str | None], dict[str, list[MutableEvent]]] = defaultdict(
            lambda: defaultdict(list)
        )
        metric_state: dict[tuple[int | None, str | None, str | None, str], dict[str, Any]] = defaultdict(
            lambda: {"sum_duration_ms": 0.0, "row_count": 0, "exemplar": None, "raw_duration_ms_list": []}
        )
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]] = defaultdict(
            lambda: {"min_start": None, "max_end": None, "duration_sum": 0.0, "has_nonzero_duration": False}
        )
        pairing_open_maps = {rule.parameter_name: defaultdict(deque) for rule in PAIRING_RULES}
        direct_duration_results: list[ParameterResult] = []
        pairing_results: list[ParameterResult] = []
        cycle_anchor_events: list[MutableEvent] = []
        error_counter: Counter[str] = Counter()
        error_bounds: dict[str, dict[str, int | None]] = {}
        error_representatives: dict[str, dict[str, Any]] = {}

        step_summary_count = 0
        total_errors = 0
        processed_rows = 0
        event_insert_seconds = 0.0
        step_insert_seconds = 0.0
        next_anchor_idx = 0
        started = time.perf_counter()

        try:
            for payload in self._iter_intermediate_event_payloads():
                event = self._row_to_event(payload)
                self._resolve_side_scope(event, context.side_registry)
                next_anchor_idx = self._infer_cycle(event, processed_rows, context, next_anchor_idx)
                signature, family, severity = normalize_error_signature(event)
                event.normalized_signature = signature
                event.error_family = family
                event.severity = severity

                event_buffer.append(self._event_to_insert_row(event))

                total_errors += self._collect_error_cluster_state(
                    event,
                    counter=error_counter,
                    bounds=error_bounds,
                    representatives=error_representatives,
                )
                step_summary_count += self._consume_pair_step(
                    event,
                    pairing_state=pairing_state,
                    step_buffer=step_buffer,
                    cycle_summary_stats=cycle_summary_stats,
                )
                self._collect_direct_duration_result(event, direct_duration_results)
                self._consume_pairing_result(event, pairing_open_maps, pairing_results)
                self._collect_metric_state(event, metric_state)
                if event.epoch_ms is not None and "current imaging cycle" in (event.message or "").lower():
                    cycle_anchor_events.append(event)

                processed_rows += 1

                if len(event_buffer) >= self.guard.merge_insert_batch:
                    t0 = time.perf_counter()
                    self._flush_event_inserts(event_buffer)
                    event_insert_seconds += time.perf_counter() - t0
                    self._apply_memory_guard("event_insert")

                if len(step_buffer) >= self.guard.step_insert_batch:
                    t0 = time.perf_counter()
                    self._flush_step_buffer(step_buffer)
                    step_insert_seconds += time.perf_counter() - t0
                    self._apply_memory_guard("step_insert")

                if processed_rows % self.scan_batch_size == 0 and progress_callback and total_events > 0:
                    percent = 82 + int(processed_rows / total_events * 10)
                    progress_callback(
                        f"streaming_postprocess_and_aggregation {min(processed_rows, total_events)}/{total_events}",
                        min(92, percent),
                        "streaming events through cycle inference, aggregation, and batched SQLite inserts",
                    )

            if event_buffer:
                t0 = time.perf_counter()
                self._flush_event_inserts(event_buffer)
                event_insert_seconds += time.perf_counter() - t0

            step_summary_count += self._flush_open_pair_steps(
                pairing_state=pairing_state,
                step_buffer=step_buffer,
                cycle_summary_stats=cycle_summary_stats,
            )
            metric_results, metric_step_count = self._finalize_metric_results(
                metric_state=metric_state,
                step_buffer=step_buffer,
                cycle_summary_stats=cycle_summary_stats,
            )
            step_summary_count += metric_step_count
            if step_buffer:
                t0 = time.perf_counter()
                self._flush_step_buffer(step_buffer)
                step_insert_seconds += time.perf_counter() - t0

            parameter_results = self._finalize_parameter_results(
                cycle_anchor_events=cycle_anchor_events,
                direct_duration_results=direct_duration_results,
                pairing_results=pairing_results,
                metric_results=metric_results,
                cycle_summary_stats=cycle_summary_stats,
            )
            parameter_step_count = self._append_parameter_step_rows(parameter_results)
            step_summary_count += parameter_step_count
            t0 = time.perf_counter()
            parameter_result_count = self._persist_parameter_results(parameter_results)
            parameter_insert_seconds = time.perf_counter() - t0
            del parameter_results
            gc.collect()

            cluster_rows = self._build_error_cluster_rows(error_counter, error_bounds, error_representatives, limit=200)
            cluster_insert_seconds = 0.0
            if cluster_rows:
                t0 = time.perf_counter()
                self.db.execute(insert(ErrorClusterModel), cluster_rows)
                self.db.commit()
                cluster_insert_seconds = time.perf_counter() - t0

            if progress_callback and total_events > 0:
                progress_callback(
                    f"streaming_postprocess_and_aggregation {min(processed_rows, total_events)}/{total_events}",
                    92,
                    "postprocess complete, persisted final events and aggregates",
                )

            return {
                "total_errors": total_errors,
                "step_summary_count": step_summary_count,
                "parameter_result_count": parameter_result_count,
                "cluster_count": len(cluster_rows),
                "timings": {
                    "stream_postprocess_seconds": round(time.perf_counter() - started, 4),
                    "db_insert_events_seconds": round(event_insert_seconds, 4),
                    "db_write_steps_seconds": round(step_insert_seconds, 4),
                    "db_write_parameter_results_seconds": round(parameter_insert_seconds, 4),
                    "db_write_clusters_seconds": round(cluster_insert_seconds, 4),
                },
                "memory_guard": self.memory_guard_report(),
            }
        finally:
            self._cleanup_intermediate_outputs()

        update_buffer: list[dict[str, Any]] = []
        step_buffer: list[dict[str, Any]] = []
        pairing_state: dict[tuple[str | None, int | None, str | None, str | None], dict[str, list[MutableEvent]]] = defaultdict(
            lambda: defaultdict(list)
        )
        metric_state: dict[tuple[int | None, str | None, str | None, str], dict[str, Any]] = defaultdict(
            lambda: {"sum_duration_ms": 0.0, "row_count": 0, "exemplar": None, "raw_duration_ms_list": []}
        )
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]] = defaultdict(
            lambda: {"min_start": None, "max_end": None, "duration_sum": 0.0, "has_nonzero_duration": False}
        )
        pairing_open_maps = {rule.parameter_name: defaultdict(deque) for rule in PAIRING_RULES}
        direct_duration_results: list[ParameterResult] = []
        pairing_results: list[ParameterResult] = []
        cycle_anchor_events: list[MutableEvent] = []
        error_counter: Counter[str] = Counter()
        error_bounds: dict[str, dict[str, int | None]] = {}
        error_representatives: dict[str, dict[str, Any]] = {}

        step_summary_count = 0
        total_errors = 0
        processed_rows = 0
        update_seconds = 0.0
        step_insert_seconds = 0.0
        next_anchor_idx = 0
        columns = (
            NormalizedEventModel.id,
            NormalizedEventModel.source_file,
            NormalizedEventModel.parser_name,
            NormalizedEventModel.original_time_text,
            NormalizedEventModel.parsed_datetime,
            NormalizedEventModel.epoch_ms,
            NormalizedEventModel.formatted_ms,
            NormalizedEventModel.level,
            NormalizedEventModel.component,
            NormalizedEventModel.module,
            NormalizedEventModel.thread,
            NormalizedEventModel.method_name,
            NormalizedEventModel.class_name,
            NormalizedEventModel.source_path,
            NormalizedEventModel.line_no,
            NormalizedEventModel.message,
            NormalizedEventModel.raw_text,
            NormalizedEventModel.cycle_no,
            NormalizedEventModel.sub_step,
            NormalizedEventModel.instrument_scope,
            NormalizedEventModel.side_scope,
            NormalizedEventModel.side_group,
            NormalizedEventModel.chip_name,
            NormalizedEventModel.chip_position,
            NormalizedEventModel.chuck_no,
            NormalizedEventModel.slot_no,
            NormalizedEventModel.stage_key,
            NormalizedEventModel.stage_name,
            NormalizedEventModel.board_name,
            NormalizedEventModel.event_kind,
            NormalizedEventModel.direction,
            NormalizedEventModel.duration_ms,
            NormalizedEventModel.status,
            NormalizedEventModel.error_code,
            NormalizedEventModel.exception_type,
            NormalizedEventModel.side_confidence,
            NormalizedEventModel.side_evidence,
            NormalizedEventModel.extra_json,
        )
        started = time.perf_counter()

        for rows in self._iter_event_batches(columns=columns, limit=self.scan_batch_size):
            for row in rows:
                event = self._row_to_event(row)
                self._resolve_side_scope(event, context.side_registry)
                next_anchor_idx = self._infer_cycle(event, processed_rows, context, next_anchor_idx)
                signature, family, severity = normalize_error_signature(event)
                event.normalized_signature = signature
                event.error_family = family
                event.severity = severity

                update_buffer.append(
                    {
                        "_row_id": int(row["id"]),
                        "cycle_no": event.cycle_no,
                        "instrument_scope": event.instrument_scope,
                        "side_scope": event.side_scope,
                        "side_group": event.side_group,
                        "chip_name": event.chip_name,
                        "chip_position": event.chip_position,
                        "chuck_no": event.chuck_no,
                        "slot_no": event.slot_no,
                        "stage_key": event.stage_key,
                        "normalized_signature": event.normalized_signature,
                        "error_family": event.error_family,
                        "severity": event.severity,
                        "side_confidence": event.side_confidence,
                        "side_evidence": _json_text(event.side_evidence),
                        "extra_json": _json_text(event.extra_json),
                    }
                )

                total_errors += self._collect_error_cluster_state(
                    event,
                    counter=error_counter,
                    bounds=error_bounds,
                    representatives=error_representatives,
                )
                step_summary_count += self._consume_pair_step(
                    event,
                    pairing_state=pairing_state,
                    step_buffer=step_buffer,
                    cycle_summary_stats=cycle_summary_stats,
                )
                self._collect_direct_duration_result(event, direct_duration_results)
                self._consume_pairing_result(event, pairing_open_maps, pairing_results)
                self._collect_metric_state(event, metric_state)
                if event.epoch_ms is not None and "current imaging cycle" in (event.message or "").lower():
                    cycle_anchor_events.append(event)

                processed_rows += 1

                if len(update_buffer) >= self.guard.update_batch:
                    t0 = time.perf_counter()
                    self.db.execute(self._event_update_stmt, update_buffer)
                    self.db.commit()
                    update_seconds += time.perf_counter() - t0
                    update_buffer.clear()
                    self._apply_memory_guard("event_update")

                if len(step_buffer) >= self.guard.step_insert_batch:
                    t0 = time.perf_counter()
                    self._flush_step_buffer(step_buffer)
                    step_insert_seconds += time.perf_counter() - t0
                    self._apply_memory_guard("step_insert")

            if progress_callback and total_events > 0:
                percent = 82 + int(processed_rows / total_events * 10)
                progress_callback(
                    f"流式后处理与聚合 {min(processed_rows, total_events)}/{total_events}",
                    min(92, percent),
                    "正在分批更新事件、汇总 step/参数统计并准备错误簇",
                )

        if update_buffer:
            t0 = time.perf_counter()
            self.db.execute(self._event_update_stmt, update_buffer)
            self.db.commit()
            update_seconds += time.perf_counter() - t0
            update_buffer.clear()

        step_summary_count += self._flush_open_pair_steps(
            pairing_state=pairing_state,
            step_buffer=step_buffer,
            cycle_summary_stats=cycle_summary_stats,
        )
        metric_results, metric_step_count = self._finalize_metric_results(
            metric_state=metric_state,
            step_buffer=step_buffer,
            cycle_summary_stats=cycle_summary_stats,
        )
        step_summary_count += metric_step_count
        if step_buffer:
            t0 = time.perf_counter()
            self._flush_step_buffer(step_buffer)
            step_insert_seconds += time.perf_counter() - t0

        parameter_results = self._finalize_parameter_results(
            cycle_anchor_events=cycle_anchor_events,
            direct_duration_results=direct_duration_results,
            pairing_results=pairing_results,
            metric_results=metric_results,
            cycle_summary_stats=cycle_summary_stats,
        )
        parameter_step_count = self._append_parameter_step_rows(parameter_results)
        step_summary_count += parameter_step_count
        t0 = time.perf_counter()
        parameter_result_count = self._persist_parameter_results(parameter_results)
        parameter_insert_seconds = time.perf_counter() - t0
        del parameter_results
        gc.collect()

        cluster_rows = self._build_error_cluster_rows(error_counter, error_bounds, error_representatives, limit=200)
        cluster_insert_seconds = 0.0
        if cluster_rows:
            t0 = time.perf_counter()
            self.db.execute(insert(ErrorClusterModel), cluster_rows)
            self.db.commit()
            cluster_insert_seconds = time.perf_counter() - t0

        gc.collect()
        return {
            "total_errors": total_errors,
            "step_summary_count": step_summary_count,
            "parameter_result_count": parameter_result_count,
            "cluster_count": len(cluster_rows),
            "timings": {
                "stream_postprocess_seconds": round(time.perf_counter() - started, 4),
                "db_update_events_seconds": round(update_seconds, 4),
                "db_write_steps_seconds": round(step_insert_seconds, 4),
                "db_write_parameter_results_seconds": round(parameter_insert_seconds, 4),
                "db_write_clusters_seconds": round(cluster_insert_seconds, 4),
            },
            "memory_guard": self.memory_guard_report(),
        }

    def memory_guard_report(self) -> dict[str, Any]:
        return {
            "trigger_count": self.guard.trigger_count,
            "stage_hits": dict(self.guard.stage_hits),
            "current_batches": {
                "merge_insert_batch": self.guard.merge_insert_batch,
                "update_batch": self.guard.update_batch,
                "step_insert_batch": self.guard.step_insert_batch,
                "cluster_insert_batch": self.guard.cluster_insert_batch,
            },
            "last_snapshot": dict(self.guard.last_snapshot),
            "last_reasons": list(self.guard.last_reasons),
        }

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except Exception:
            return None

    def _event_sort_key(self, payload: dict[str, Any], stream_index: int, record_index: int) -> tuple[Any, ...]:
        return (
            self._to_int(payload.get("epoch_ms")) or 0,
            str(payload.get("source_file") or ""),
            str(payload.get("message") or ""),
            self._to_int(payload.get("line_no")) or -1,
            stream_index,
            record_index,
        )

    def _push_intermediate_payload(
        self,
        heap: list[tuple[tuple[Any, ...], int, int, dict[str, Any]]],
        handles: list[Any],
        record_indexes: list[int],
        stream_index: int,
    ) -> bool:
        handle = handles[stream_index]
        while True:
            line = handle.readline()
            if not line:
                return False
            if not line.strip():
                continue
            payload = orjson.loads(line)
            record_index = record_indexes[stream_index]
            record_indexes[stream_index] += 1
            heapq.heappush(
                heap,
                (
                    self._event_sort_key(payload, stream_index, record_index),
                    stream_index,
                    record_index,
                    payload,
                ),
            )
            return True

    def _iter_intermediate_event_payloads(self) -> Iterator[dict[str, Any]]:
        if not self._intermediate_results:
            return

        heap: list[tuple[tuple[Any, ...], int, int, dict[str, Any]]] = []
        handles: list[Any] = []
        record_indexes: list[int] = []
        try:
            for stream_index, item in enumerate(self._intermediate_results):
                output_path = Path(str(item.get("output_path") or ""))
                if not output_path.exists():
                    continue
                handles.append(output_path.open("rb"))
                record_indexes.append(0)
                self._push_intermediate_payload(heap, handles, record_indexes, len(handles) - 1)

            while heap:
                _, stream_index, _record_index, payload = heapq.heappop(heap)
                yield payload
                self._push_intermediate_payload(heap, handles, record_indexes, stream_index)
        finally:
            for handle in handles:
                try:
                    handle.close()
                except Exception:
                    pass

    def _cleanup_intermediate_outputs(self) -> None:
        for item in self._intermediate_results:
            try:
                Path(str(item.get("output_path") or "")).unlink(missing_ok=True)
            except Exception:
                continue
        self._intermediate_results = []

    def _event_to_insert_row(self, event: MutableEvent) -> dict[str, Any]:
        row = {field: getattr(event, field, None) for field in EVENT_INSERT_FIELDS if field != "task_id"}
        row["task_id"] = self.task_id
        row["parsed_datetime"] = _coerce_datetime(row.get("parsed_datetime"))
        row["side_evidence"] = _json_text(event.side_evidence)
        row["extra_json"] = _json_text(event.extra_json)
        return row

    def _prepare_event_insert(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {field: payload.get(field) for field in EVENT_INSERT_FIELDS if field != "task_id"}
        row["task_id"] = self.task_id
        row["parsed_datetime"] = _coerce_datetime(payload.get("parsed_datetime"))
        row["side_evidence"] = _json_text(_coerce_extra_json(payload.get("side_evidence")))
        row["extra_json"] = _json_text(_coerce_extra_json(payload.get("extra_json")))
        return row

    def _flush_event_inserts(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.db.execute(insert(NormalizedEventModel), rows)
        self.db.commit()
        rows.clear()

    def _flush_step_buffer(self, step_buffer: list[dict[str, Any]]) -> None:
        if not step_buffer:
            return
        self.db.execute(insert(StepSummaryModel), step_buffer)
        self.db.commit()
        step_buffer.clear()

    def _parameter_result_to_row(self, result: ParameterResult) -> dict[str, Any]:
        row = {field: None for field in PARAMETER_RESULT_INSERT_FIELDS if field != "task_id"}
        row.update(
            {
                "parameter_name": result.parameter_name,
                "parameter_display_name": result.parameter_display_name,
                "cycle_no": result.cycle,
                "slide": result.slide,
                "instrument_scope": result.instrument_scope,
                "side_scope": result.side_scope,
                "side_group": result.side_group,
                "chip_name": result.chip_name,
                "chip_position": result.chip_position,
                "chuck_no": result.chuck_no,
                "slot_no": result.slot_no,
                "stage_key": result.stage_key,
                "duration_seconds": result.duration_seconds,
                "duration_ms": result.duration_ms,
                "start_time_text": result.start_time,
                "end_time_text": result.end_time,
                "start_message": result.start_message,
                "end_message": result.end_message,
                "source_file": result.source_file,
                "source_type": result.source_type,
                "threshold": result.threshold,
                "expected": result.expected,
                "is_exceed": result.is_exceed,
                "component": result.component,
                "start_event_id": result.start_event_id,
                "end_event_id": result.end_event_id,
                "side_confidence": result.side_confidence,
                "side_evidence": _json_text(result.side_evidence),
                "extra_json": _json_text(result.extra),
            }
        )
        row["task_id"] = self.task_id
        return row

    def _persist_parameter_results(self, parameter_results: list[ParameterResult]) -> int:
        if not parameter_results:
            return 0
        pending: list[dict[str, Any]] = []
        count = 0
        for result in parameter_results:
            pending.append(self._parameter_result_to_row(result))
            count += 1
            if len(pending) >= self.guard.step_insert_batch:
                self.db.execute(insert(ParameterResultModel), pending)
                self.db.commit()
                pending.clear()
                self._apply_memory_guard("parameter_result_insert")
        if pending:
            self.db.execute(insert(ParameterResultModel), pending)
            self.db.commit()
        return count

    def _append_parameter_step_rows(self, parameter_results: list[ParameterResult]) -> int:
        pending: list[dict[str, Any]] = []
        count = 0
        for result in parameter_results:
            if result.parameter_name == "row_scan_metric_avg":
                continue
            threshold_ms = (result.threshold * 1000.0) if result.threshold is not None else None
            pending.append(
                {
                    "task_id": self.task_id,
                    "cycle_no": result.cycle,
                    "parameter_name": result.parameter_name,
                    "sub_step": result.parameter_display_name,
                    "component": result.component,
                    "instrument_scope": result.instrument_scope,
                    "side_scope": result.side_scope,
                    "side_group": result.side_group,
                    "chip_name": result.chip_name,
                    "chip_position": result.chip_position,
                    "chuck_no": result.chuck_no,
                    "slot_no": result.slot_no,
                    "stage_key": result.stage_key,
                    "start_epoch_ms": None,
                    "end_epoch_ms": None,
                    "duration_ms": result.duration_ms,
                    "threshold_ms": threshold_ms,
                    "is_over_threshold": result.is_exceed,
                    "start_time_text": result.start_time,
                    "end_time_text": result.end_time,
                    "side_confidence": result.side_confidence,
                    "side_evidence": _json_text(result.side_evidence),
                }
            )
            count += 1
            if len(pending) >= self.guard.step_insert_batch:
                self._flush_step_buffer(pending)
                self._apply_memory_guard("parameter_step_insert")

        if pending:
            self._flush_step_buffer(pending)
        return count

    def _iter_event_batches(self, *, columns: tuple[Any, ...], limit: int) -> Any:
        last_key: tuple[int, str, str, int] | None = None
        sort_epoch = func.coalesce(NormalizedEventModel.epoch_ms, 0)

        while True:
            stmt = (
                select(*columns, sort_epoch.label("sort_epoch"))
                .where(NormalizedEventModel.task_id == self.task_id)
                .order_by(
                    sort_epoch.asc(),
                    NormalizedEventModel.source_file.asc(),
                    NormalizedEventModel.message.asc(),
                    NormalizedEventModel.id.asc(),
                )
                .limit(limit)
            )
            if last_key is not None:
                last_epoch, last_source_file, last_message, last_id = last_key
                stmt = stmt.where(
                    or_(
                        sort_epoch > last_epoch,
                        and_(
                            sort_epoch == last_epoch,
                            NormalizedEventModel.source_file > last_source_file,
                        ),
                        and_(
                            sort_epoch == last_epoch,
                            NormalizedEventModel.source_file == last_source_file,
                            NormalizedEventModel.message > last_message,
                        ),
                        and_(
                            sort_epoch == last_epoch,
                            NormalizedEventModel.source_file == last_source_file,
                            NormalizedEventModel.message == last_message,
                            NormalizedEventModel.id > last_id,
                        ),
                    )
                )

            rows = self.db.execute(stmt).mappings().all()
            if not rows:
                break

            yield rows
            tail = rows[-1]
            last_key = (
                int(tail["sort_epoch"]),
                str(tail["source_file"]),
                str(tail["message"]),
                int(tail["id"]),
            )

    def _memory_snapshot(self) -> dict[str, Any]:
        system_percent = None
        available_mb = None
        process_rss_mb = None
        cpu_percent = None

        if psutil is not None:
            try:
                cpu_percent = round(float(psutil.cpu_percent(interval=0.05)), 1)
                vm = psutil.virtual_memory()
                system_percent = round(float(vm.percent), 1)
                available_mb = _round_mb(vm.available)
                process_rss_mb = _round_mb(psutil.Process(os.getpid()).memory_info().rss)
            except Exception:
                pass

        if available_mb is None and Path("/proc/meminfo").exists():
            meminfo: dict[str, int] = {}
            try:
                for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                    if ":" not in line:
                        continue
                    key, raw_value = line.split(":", 1)
                    parts = raw_value.strip().split()
                    if not parts:
                        continue
                    meminfo[key] = int(parts[0])
            except Exception:
                meminfo = {}
            total = meminfo.get("MemTotal")
            available = meminfo.get("MemAvailable") or meminfo.get("MemFree")
            if total and available is not None:
                used = max(int(total) - int(available), 0)
                system_percent = round(used / total * 100, 1)
                available_mb = round(available / 1024, 1)

        if process_rss_mb is None and resource is not None:
            try:
                usage = resource.getrusage(resource.RUSAGE_SELF)
                rss = float(usage.ru_maxrss)
                if os.name == "posix" and "darwin" not in os.sys.platform:
                    rss *= 1024
                process_rss_mb = _round_mb(rss)
            except Exception:
                pass

        return {
            "cpu_percent": cpu_percent,
            "system_percent": system_percent,
            "available_mb": available_mb,
            "process_rss_mb": process_rss_mb,
        }

    def _apply_memory_guard(self, stage: str, *, collect: bool = True) -> bool:
        snapshot = self._memory_snapshot()
        reasons: list[str] = []
        limit_percent = max(0, min(int(self.settings.system_memory_soft_limit_percent), 98))
        reserve_mb = max(0, int(self.settings.system_memory_soft_reserve_mb))
        cpu_limit_percent = max(0, min(int(self.settings.system_cpu_soft_limit_percent), 100))
        cpu_percent = snapshot.get("cpu_percent")
        system_percent = snapshot.get("system_percent")
        available_mb = snapshot.get("available_mb")

        if limit_percent > 0 and system_percent is not None and float(system_percent) >= limit_percent:
            reasons.append(f"system_percent={system_percent} >= {limit_percent}")
        if reserve_mb > 0 and available_mb is not None and float(available_mb) <= reserve_mb:
            reasons.append(f"available_mb={available_mb} <= {reserve_mb}")
        if cpu_limit_percent > 0 and cpu_percent is not None and float(cpu_percent) >= cpu_limit_percent:
            reasons.append(f"cpu_percent={cpu_percent} >= {cpu_limit_percent}")

        if not reasons:
            return False

        self.guard.trigger_count += 1
        self.guard.stage_hits[stage] = self.guard.stage_hits.get(stage, 0) + 1
        self.guard.last_snapshot = snapshot
        self.guard.last_reasons = reasons
        self.guard.merge_insert_batch = max(100, self.guard.merge_insert_batch // 2)
        self.guard.update_batch = max(100, self.guard.update_batch // 2)
        self.guard.step_insert_batch = max(100, self.guard.step_insert_batch // 2)
        self.guard.cluster_insert_batch = max(100, self.guard.cluster_insert_batch // 2)

        if collect:
            gc.collect()
        wait_seconds = max(0.05, min(float(self.settings.system_memory_guard_wait_seconds), 0.5))
        time.sleep(wait_seconds)
        return True

    def _row_to_event(self, row: dict[str, Any]) -> MutableEvent:
        extra_json = _coerce_extra_json(row.get("extra_json"))
        return MutableEvent(
            source_file=str(row["source_file"]),
            parser_name=str(row["parser_name"]),
            original_time_text=row["original_time_text"],
            parsed_datetime=_coerce_datetime(row.get("parsed_datetime")),
            epoch_ms=row["epoch_ms"],
            formatted_ms=row["formatted_ms"],
            level=str(row["level"] or "INFO"),
            component=row["component"],
            module=row["module"],
            thread=row["thread"],
            method_name=row["method_name"],
            class_name=row["class_name"],
            source_path=row["source_path"],
            line_no=row["line_no"],
            message=str(row["message"]),
            raw_text=str(row["raw_text"] or row["message"]),
            cycle_no=row["cycle_no"],
            sub_step=row["sub_step"],
            instrument_scope=row.get("instrument_scope"),
            side_scope=row.get("side_scope"),
            side_group=row.get("side_group"),
            chip_name=row["chip_name"],
            chip_position=row.get("chip_position"),
            chuck_no=row.get("chuck_no"),
            slot_no=row.get("slot_no"),
            stage_key=row.get("stage_key"),
            stage_name=row["stage_name"],
            board_name=row["board_name"],
            event_kind=row["event_kind"],
            direction=row["direction"],
            duration_ms=row["duration_ms"],
            status=row["status"],
            error_code=row["error_code"],
            exception_type=row["exception_type"],
            cycle_inferred=bool(row.get("cycle_inferred") or extra_json.get("cycle_inferred")),
            cycle_infer_method=row.get("cycle_infer_method") or extra_json.get("cycle_infer_method"),
            cycle_infer_confidence=row.get("cycle_infer_confidence") or extra_json.get("cycle_infer_confidence"),
            cycle_infer_reason=row.get("cycle_infer_reason") or extra_json.get("cycle_infer_reason"),
            side_confidence=row.get("side_confidence"),
            side_evidence=_coerce_extra_json(row.get("side_evidence")),
            extra_json=extra_json,
        )

    def _resolve_side_scope(self, event: MutableEvent, registry: TaskSideRegistry) -> None:
        direct = infer_scope_from_texts(
            source_file=event.source_file,
            message=event.message,
            raw_text=event.raw_text,
            chip_name=event.chip_name,
            stage_name=event.stage_name or event.stage_key,
            extra=event.extra_json,
        )
        direct.instrument_scope = event.instrument_scope or direct.instrument_scope
        direct.side_scope = prefer_specific_side(direct.side_scope, event.side_scope) or event.side_scope or direct.side_scope
        direct.side_group = direct.side_group or event.side_group or infer_side_group(direct.side_scope or event.side_scope)
        direct.chip_name = direct.chip_name or event.chip_name
        direct.chip_position = direct.chip_position or event.chip_position
        direct.chuck_no = direct.chuck_no or event.chuck_no
        direct.slot_no = direct.slot_no or event.slot_no
        direct.stage_key = direct.stage_key or event.stage_key
        direct.side_confidence = max(float(direct.side_confidence or 0.0), float(event.side_confidence or 0.0)) or None
        direct.side_evidence = {**event.side_evidence, **direct.side_evidence}

        resolved = registry.resolve_inference(direct)
        event.instrument_scope = resolved.instrument_scope
        event.side_scope = resolved.side_scope
        event.side_group = resolved.side_group or infer_side_group(resolved.side_scope)
        event.chip_name = resolved.chip_name
        event.chip_position = resolved.chip_position
        event.chuck_no = resolved.chuck_no
        event.slot_no = resolved.slot_no
        event.stage_key = resolved.stage_key
        event.side_confidence = resolved.side_confidence
        event.side_evidence = dict(resolved.side_evidence or {})

    def _infer_cycle(
        self,
        event: MutableEvent,
        event_index: int,
        context: CycleInferenceContext,
        next_anchor_idx: int,
    ) -> int:
        anchors = context.anchors
        if not anchors:
            if event.cycle_no is None:
                _apply_cycle_mark(event, False, "insufficient_context", "low", reason="insufficient_context")
            return next_anchor_idx

        while next_anchor_idx < len(anchors) and anchors[next_anchor_idx].position < event_index:
            next_anchor_idx += 1

        if event.cycle_no is not None:
            _apply_cycle_mark(event, False, "existing", "high")
            return next_anchor_idx

        msg = (event.message or "").lower()
        prev_anchor = anchors[next_anchor_idx - 1] if next_anchor_idx > 0 else None
        next_anchor = anchors[next_anchor_idx] if next_anchor_idx < len(anchors) else None
        votes = context.component_cycle_votes.get((event.component, event.sub_step)) or context.component_cycle_votes.get(
            (event.component, None)
        )
        if votes:
            winner, count = votes.most_common(1)[0]
            total = sum(votes.values())
            if total >= 2 and count / total >= 0.7:
                _apply_cycle_mark(event, True, "component_cluster", "high", cycle_no=int(winner))
                return next_anchor_idx

        if prev_anchor and next_anchor:
            prev_cycle = prev_anchor.cycle_no
            next_cycle = next_anchor.cycle_no
            if prev_cycle == next_cycle:
                _apply_cycle_mark(event, True, "time_interval_same_cycle", "high", cycle_no=prev_cycle)
                return next_anchor_idx
            if any(token in msg for token in NEXT_CYCLE_HINTS):
                _apply_cycle_mark(event, True, "time_interval_next_cycle", "medium", cycle_no=next_cycle)
                return next_anchor_idx
            if any(token in msg for token in CURRENT_CYCLE_HINTS):
                _apply_cycle_mark(event, True, "time_interval_current_cycle", "medium", cycle_no=prev_cycle)
                return next_anchor_idx
            if event.epoch_ms is not None:
                prev_time = prev_anchor.epoch_ms if prev_anchor.epoch_ms is not None else event.epoch_ms
                next_time = next_anchor.epoch_ms if next_anchor.epoch_ms is not None else event.epoch_ms
                if abs(event.epoch_ms - prev_time) <= abs(next_time - event.epoch_ms):
                    _apply_cycle_mark(event, True, "time_nearest_anchor", "low", cycle_no=prev_cycle)
                else:
                    _apply_cycle_mark(event, True, "time_nearest_anchor", "low", cycle_no=next_cycle)
                return next_anchor_idx

        if prev_anchor and any(token in msg for token in CURRENT_CYCLE_HINTS):
            _apply_cycle_mark(event, True, "previous_anchor", "medium", cycle_no=prev_anchor.cycle_no)
            return next_anchor_idx
        if next_anchor and any(token in msg for token in NEXT_CYCLE_HINTS):
            _apply_cycle_mark(event, True, "next_anchor", "medium", cycle_no=next_anchor.cycle_no)
            return next_anchor_idx

        _apply_cycle_mark(event, False, "insufficient_context", "low", reason="insufficient_context")
        return next_anchor_idx

    def _collect_error_cluster_state(
        self,
        event: MutableEvent,
        *,
        counter: Counter[str],
        bounds: dict[str, dict[str, int | None]],
        representatives: dict[str, dict[str, Any]],
    ) -> int:
        signature = event.normalized_signature
        if not signature:
            return 0

        counter[signature] += 1
        if signature not in representatives:
            display_signature = None
            if isinstance(event.extra_json, dict):
                display_signature = event.extra_json.get("display_signature")
            representatives[signature] = {
                "error_family": event.error_family,
                "severity": event.severity,
                "display_signature": display_signature or event.message[:120],
                "exception_type": event.exception_type,
                "component": event.component,
            }

        state = bounds.setdefault(signature, {"first": None, "last": None})
        if event.epoch_ms is not None:
            if state["first"] is None or event.epoch_ms < int(state["first"]):
                state["first"] = int(event.epoch_ms)
            if state["last"] is None or event.epoch_ms > int(state["last"]):
                state["last"] = int(event.epoch_ms)
        return 1

    def _consume_pair_step(
        self,
        event: MutableEvent,
        *,
        pairing_state: dict[tuple[str | None, int | None, str | None, str | None], dict[str, list[MutableEvent]]],
        step_buffer: list[dict[str, Any]],
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]],
    ) -> int:
        if event.event_kind not in {"step", "action", "metric"}:
            return 0

        group_key = build_group_key(event)
        active = pairing_state[group_key]
        step_key = normalize_step_key(event.sub_step or event.message)
        if not step_key:
            return 0

        component, cycle_no, side_scope, chip_name = group_key
        if event.direction == "start":
            if is_running_status_message(event.message):
                candidates = active.get(step_key, [])
                heartbeat_target: MutableEvent | None = None
                if candidates:
                    for candidate in candidates:
                        if _is_pairable(candidate, event):
                            heartbeat_target = candidate
                            break
                    else:
                        active[step_key].append(event)
                        heartbeat_target = event
                else:
                    active[step_key].append(event)
                    heartbeat_target = event
                if heartbeat_target is not None:
                    _mark_heartbeat_progress(heartbeat_target, event)
                return 0
            active[step_key].append(event)
            return 0

        if event.direction == "end":
            start_event = None
            candidates = active.get(step_key, [])
            if candidates:
                for idx in range(len(candidates) - 1, -1, -1):
                    candidate = candidates[idx]
                    if _is_pairable(candidate, event):
                        start_event = candidates.pop(idx)
                        break
            if start_event is not None:
                duration_ms = _derive_duration_ms(start_event, event)
                return self._append_step_row(
                    step_buffer,
                    cycle_summary_stats,
                    cycle_no=cycle_no,
                    parameter_name=None,
                    sub_step=step_key,
                    component=component,
                    instrument_scope=event.instrument_scope or start_event.instrument_scope,
                    side_scope=side_scope or event.side_scope or start_event.side_scope,
                    side_group=event.side_group or start_event.side_group,
                    chip_name=chip_name or event.chip_name or start_event.chip_name,
                    chip_position=event.chip_position or start_event.chip_position,
                    chuck_no=event.chuck_no or start_event.chuck_no,
                    slot_no=event.slot_no or start_event.slot_no,
                    stage_key=event.stage_key or start_event.stage_key,
                    start_epoch_ms=start_event.epoch_ms,
                    end_epoch_ms=event.epoch_ms,
                    duration_ms=duration_ms,
                    threshold_ms=get_step_threshold_ms(self.thresholds, component, step_key),
                    is_over_threshold=bool(
                        duration_ms
                        and get_step_threshold_ms(self.thresholds, component, step_key)
                        and duration_ms > float(get_step_threshold_ms(self.thresholds, component, step_key) or 0)
                    ),
                    start_time_text=start_event.formatted_ms,
                    end_time_text=event.formatted_ms,
                    side_confidence=max(float(event.side_confidence or 0.0), float(start_event.side_confidence or 0.0)) or None,
                    side_evidence={**start_event.side_evidence, **event.side_evidence},
                )
            if event.duration_ms is not None and event.epoch_ms is not None:
                threshold_ms = get_step_threshold_ms(self.thresholds, component, step_key)
                return self._append_step_row(
                    step_buffer,
                    cycle_summary_stats,
                    cycle_no=cycle_no,
                    parameter_name=None,
                    sub_step=step_key,
                    component=component,
                    instrument_scope=event.instrument_scope,
                    side_scope=side_scope or event.side_scope,
                    side_group=event.side_group,
                    chip_name=chip_name or event.chip_name,
                    chip_position=event.chip_position,
                    chuck_no=event.chuck_no,
                    slot_no=event.slot_no,
                    stage_key=event.stage_key,
                    start_epoch_ms=int(event.epoch_ms - event.duration_ms),
                    end_epoch_ms=event.epoch_ms,
                    duration_ms=event.duration_ms,
                    threshold_ms=threshold_ms,
                    is_over_threshold=bool(event.duration_ms and threshold_ms and event.duration_ms > threshold_ms),
                    start_time_text=None,
                    end_time_text=event.formatted_ms,
                    side_confidence=event.side_confidence,
                    side_evidence=event.side_evidence,
                )
            return 0

        if event.duration_ms is not None:
            threshold_ms = get_step_threshold_ms(self.thresholds, component, step_key)
            return self._append_step_row(
                step_buffer,
                cycle_summary_stats,
                cycle_no=cycle_no,
                parameter_name=None,
                sub_step=step_key,
                component=component,
                instrument_scope=event.instrument_scope,
                side_scope=side_scope or event.side_scope,
                side_group=event.side_group,
                chip_name=chip_name or event.chip_name,
                chip_position=event.chip_position,
                chuck_no=event.chuck_no,
                slot_no=event.slot_no,
                stage_key=event.stage_key,
                start_epoch_ms=None,
                end_epoch_ms=event.epoch_ms,
                duration_ms=event.duration_ms,
                threshold_ms=threshold_ms,
                is_over_threshold=bool(event.duration_ms and threshold_ms and event.duration_ms > threshold_ms),
                start_time_text=None,
                end_time_text=event.formatted_ms,
                side_confidence=event.side_confidence,
                side_evidence=event.side_evidence,
            )
        return 0

    def _flush_open_pair_steps(
        self,
        *,
        pairing_state: dict[tuple[str | None, int | None, str | None, str | None], dict[str, list[MutableEvent]]],
        step_buffer: list[dict[str, Any]],
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]],
    ) -> int:
        emitted = 0
        for (component, cycle_no, side_scope, chip_name), active in pairing_state.items():
            for step_key, start_events in active.items():
                threshold_ms = get_step_threshold_ms(self.thresholds, component, step_key)
                for start_event in start_events:
                    heartbeat_end_ms, heartbeat_end_text = _heartbeat_bounds(start_event)
                    duration_ms = None
                    if start_event.epoch_ms is not None and heartbeat_end_ms is not None and heartbeat_end_ms >= start_event.epoch_ms:
                        duration_ms = float(heartbeat_end_ms - start_event.epoch_ms)
                    emitted += self._append_step_row(
                        step_buffer,
                        cycle_summary_stats,
                        cycle_no=cycle_no,
                        parameter_name=None,
                        sub_step=step_key,
                        component=component,
                        instrument_scope=start_event.instrument_scope,
                        side_scope=side_scope or start_event.side_scope,
                        side_group=start_event.side_group,
                        chip_name=chip_name or start_event.chip_name,
                        chip_position=start_event.chip_position,
                        chuck_no=start_event.chuck_no,
                        slot_no=start_event.slot_no,
                        stage_key=start_event.stage_key,
                        start_epoch_ms=start_event.epoch_ms,
                        end_epoch_ms=heartbeat_end_ms,
                        duration_ms=duration_ms,
                        threshold_ms=threshold_ms,
                        is_over_threshold=bool(duration_ms and threshold_ms and duration_ms > threshold_ms),
                        start_time_text=start_event.formatted_ms,
                        end_time_text=heartbeat_end_text,
                        side_confidence=start_event.side_confidence,
                        side_evidence=start_event.side_evidence,
                    )
                    if len(step_buffer) >= self.guard.step_insert_batch:
                        self._flush_step_buffer(step_buffer)
                        self._apply_memory_guard("open_pair_step_insert")
        return emitted

    def _append_step_row(
        self,
        step_buffer: list[dict[str, Any]],
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]],
        *,
        cycle_no: int | None,
        parameter_name: str | None,
        sub_step: str,
        component: str | None,
        instrument_scope: str | None,
        side_scope: str | None,
        side_group: str | None,
        chip_name: str | None,
        chip_position: str | None,
        chuck_no: str | None,
        slot_no: str | None,
        stage_key: str | None,
        start_epoch_ms: int | None,
        end_epoch_ms: int | None,
        duration_ms: float | None,
        threshold_ms: float | None,
        is_over_threshold: bool,
        start_time_text: str | None,
        end_time_text: str | None,
        side_confidence: float | None,
        side_evidence: dict[str, Any] | None,
    ) -> int:
        step_buffer.append(
            {
                "task_id": self.task_id,
                "cycle_no": cycle_no,
                "parameter_name": parameter_name,
                "sub_step": sub_step,
                "component": component,
                "instrument_scope": instrument_scope,
                "side_scope": side_scope,
                "side_group": side_group,
                "chip_name": chip_name,
                "chip_position": chip_position,
                "chuck_no": chuck_no,
                "slot_no": slot_no,
                "stage_key": stage_key,
                "start_epoch_ms": start_epoch_ms,
                "end_epoch_ms": end_epoch_ms,
                "duration_ms": duration_ms,
                "threshold_ms": threshold_ms,
                "is_over_threshold": is_over_threshold,
                "start_time_text": start_time_text,
                "end_time_text": end_time_text,
                "side_confidence": side_confidence,
                "side_evidence": _json_text(side_evidence),
            }
        )
        self._update_cycle_summary(
            cycle_summary_stats,
            cycle_no=cycle_no,
            side_scope=side_scope,
            chip_name=chip_name,
            start_epoch_ms=start_epoch_ms,
            end_epoch_ms=end_epoch_ms,
            duration_ms=duration_ms,
        )
        return 1

    def _update_cycle_summary(
        self,
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]],
        *,
        cycle_no: int | None,
        side_scope: str | None,
        chip_name: str | None,
        start_epoch_ms: int | None,
        end_epoch_ms: int | None,
        duration_ms: float | None,
    ) -> None:
        stats = cycle_summary_stats[(cycle_no, side_scope, chip_name)]
        if start_epoch_ms is not None:
            current_min = stats["min_start"]
            stats["min_start"] = start_epoch_ms if current_min is None else min(int(current_min), start_epoch_ms)
        if end_epoch_ms is not None:
            current_max = stats["max_end"]
            stats["max_end"] = end_epoch_ms if current_max is None else max(int(current_max), end_epoch_ms)
        if duration_ms:
            stats["has_nonzero_duration"] = True
            stats["duration_sum"] = float(stats["duration_sum"]) + float(duration_ms)

    def _collect_direct_duration_result(self, event: MutableEvent, results: list[ParameterResult]) -> None:
        if event.duration_ms is None:
            return
        message_text = f"{event.message or ''} {event.sub_step or ''}".lower()
        for rule in DIRECT_DURATION_RULES:
            if any(token in message_text for token in rule["matchers"]):
                results.append(
                    _mk_result(
                        rule["parameter_name"],
                        rule["display_name"],
                        event.cycle_no,
                        _extract_slide_name(event.message),
                        event.chip_name,
                        None,
                        event,
                        float(event.duration_ms),
                        event.source_file,
                        "log",
                        component=event.component,
                        instrument_scope=event.instrument_scope,
                        side_scope=event.side_scope,
                        side_group=event.side_group,
                        chip_position=event.chip_position,
                        chuck_no=event.chuck_no,
                        slot_no=event.slot_no,
                        stage_key=event.stage_key,
                        side_confidence=event.side_confidence,
                        side_evidence=event.side_evidence,
                    )
                )
                return

    def _consume_pairing_result(
        self,
        event: MutableEvent,
        pairing_open_maps: dict[str, dict[tuple[Any, ...], deque[MutableEvent]]],
        pairing_results: list[ParameterResult],
    ) -> None:
        message = event.message or ""
        for rule in PAIRING_RULES:
            start_match = rule.start_pattern.search(message)
            if start_match:
                if rule.is_temperature_rule():
                    target = _extract_float_from_groups(start_match.groups())
                    if target is None or abs(float(target) - float(rule.target_temp or 0)) > float(rule.target_temp_tolerance):
                        continue
                cycle = _extract_cycle_from_match(start_match.groups()) if rule.cycle_from_match else event.cycle_no
                slide = _extract_slide_from_match(start_match.groups()) if rule.slide_from_match else _extract_slide_name(message)
                key = (rule.parameter_name, cycle, (slide or "").upper(), event.side_scope or "", event.chip_name or "")
                pairing_open_maps[rule.parameter_name][key].append(event)
                continue

            end_match = rule.end_pattern.search(message)
            if not end_match:
                continue
            if rule.is_temperature_rule():
                target = _extract_float_from_groups(end_match.groups())
                if target is None or abs(float(target) - float(rule.target_temp or 0)) > float(rule.target_temp_tolerance):
                    continue
            cycle = _extract_cycle_from_match(end_match.groups()) if rule.cycle_from_match else event.cycle_no
            slide = _extract_slide_from_match(end_match.groups()) if rule.slide_from_match else _extract_slide_name(message)
            exact_key = (rule.parameter_name, cycle, (slide or "").upper(), event.side_scope or "", event.chip_name or "")
            fallback_key = (rule.parameter_name, cycle, (slide or "").upper(), event.side_scope or "", "")
            starts = None
            for candidate_key in (
                exact_key,
                fallback_key,
                (rule.parameter_name, cycle, (slide or "").upper(), "", event.chip_name or ""),
                (rule.parameter_name, cycle, (slide or "").upper(), "", ""),
            ):
                starts = pairing_open_maps[rule.parameter_name].get(candidate_key)
                if starts:
                    break
            if not starts:
                continue
            start_event = starts.popleft()
            if start_event.epoch_ms is None or event.epoch_ms is None:
                continue
            pairing_results.append(
                _mk_result(
                    rule.parameter_name,
                    rule.display_name,
                    cycle,
                    slide,
                    event.chip_name or start_event.chip_name,
                    start_event,
                    event,
                    float(event.epoch_ms - start_event.epoch_ms),
                    event.source_file,
                    rule.source_type,
                    component=event.component or start_event.component,
                    instrument_scope=event.instrument_scope or start_event.instrument_scope,
                    side_scope=event.side_scope or start_event.side_scope,
                    side_group=event.side_group or start_event.side_group,
                    chip_position=event.chip_position or start_event.chip_position,
                    chuck_no=event.chuck_no or start_event.chuck_no,
                    slot_no=event.slot_no or start_event.slot_no,
                    stage_key=event.stage_key or start_event.stage_key,
                    side_confidence=max(float(event.side_confidence or 0.0), float(start_event.side_confidence or 0.0)) or None,
                    side_evidence={**start_event.side_evidence, **event.side_evidence},
                    extra={"rule_notes": rule.notes},
                )
            )

    def _collect_metric_state(self, event: MutableEvent, metric_state: dict[tuple[int | None, str | None, str | None, str], dict[str, Any]]) -> None:
        if event.parser_name != "metrics_csv":
            return
        if not event.sub_step or not str(event.sub_step).startswith("imaging::"):
            return
        metric_name = str(event.sub_step).split("::", 1)[-1]
        normalized_metric = "scanTotalTime" if metric_name == "ScanTotalTime" else metric_name
        if normalized_metric not in ROW_SCAN_METRIC_STAGES:
            return
        if event.duration_ms is None:
            return

        stats = metric_state[(event.cycle_no, event.side_scope, event.chip_name, normalized_metric)]
        stats["sum_duration_ms"] = float(stats["sum_duration_ms"]) + float(event.duration_ms)
        stats["row_count"] = int(stats["row_count"]) + 1
        if stats["exemplar"] is None:
            stats["exemplar"] = event
        if len(stats["raw_duration_ms_list"]) < 20:
            stats["raw_duration_ms_list"].append(float(event.duration_ms))

    def _finalize_metric_results(
        self,
        *,
        metric_state: dict[tuple[int | None, str | None, str | None, str], dict[str, Any]],
        step_buffer: list[dict[str, Any]],
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]],
    ) -> tuple[list[ParameterResult], int]:
        metric_results: list[ParameterResult] = []
        threshold, expected = _definition_values("row_scan_metric_avg")
        emitted_steps = 0

        for (cycle_no, side_scope, chip_name, metric_name), stats in metric_state.items():
            row_count = int(stats["row_count"])
            exemplar = stats["exemplar"]
            if row_count <= 0 or exemplar is None:
                continue
            avg_ms = float(stats["sum_duration_ms"]) / row_count
            result = ParameterResult(
                parameter_name="row_scan_metric_avg",
                parameter_display_name=f"row scan metric avg::{metric_name}",
                cycle=cycle_no,
                slide=None,
                instrument_scope=exemplar.instrument_scope,
                side_scope=side_scope or exemplar.side_scope,
                side_group=exemplar.side_group,
                chip_name=chip_name,
                chip_position=exemplar.chip_position,
                chuck_no=exemplar.chuck_no,
                slot_no=exemplar.slot_no,
                stage_key=exemplar.stage_key,
                duration_seconds=_safe_seconds(avg_ms),
                duration_ms=avg_ms,
                start_time=_event_time_text(exemplar),
                end_time=_event_time_text(exemplar),
                start_message=exemplar.message,
                end_message=exemplar.message,
                source_file=exemplar.source_file,
                source_type="metrics",
                threshold=threshold,
                expected=expected,
                is_exceed=False,
                component=exemplar.component,
                side_confidence=exemplar.side_confidence,
                side_evidence=dict(exemplar.side_evidence or {}),
                extra={
                    "metric_stage": metric_name,
                    "row_count": row_count,
                    "raw_duration_ms_list": list(stats["raw_duration_ms_list"]),
                },
            )
            metric_results.append(result)
            emitted_steps += self._append_step_row(
                step_buffer,
                cycle_summary_stats,
                cycle_no=result.cycle,
                parameter_name=result.parameter_name,
                sub_step=result.extra.get("metric_stage") or result.parameter_display_name,
                component=result.component,
                instrument_scope=result.instrument_scope,
                side_scope=result.side_scope,
                side_group=result.side_group,
                chip_name=result.chip_name,
                chip_position=result.chip_position,
                chuck_no=result.chuck_no,
                slot_no=result.slot_no,
                stage_key=result.stage_key,
                start_epoch_ms=None,
                end_epoch_ms=None,
                duration_ms=result.duration_ms,
                threshold_ms=(result.threshold * 1000.0) if result.threshold is not None else None,
                is_over_threshold=result.is_exceed,
                start_time_text=result.start_time,
                end_time_text=result.end_time,
                side_confidence=result.side_confidence,
                side_evidence=result.side_evidence,
            )
            if len(step_buffer) >= self.guard.step_insert_batch:
                self._flush_step_buffer(step_buffer)
                self._apply_memory_guard("metric_step_insert")

        return metric_results, emitted_steps

    def _finalize_parameter_results(
        self,
        *,
        cycle_anchor_events: list[MutableEvent],
        direct_duration_results: list[ParameterResult],
        pairing_results: list[ParameterResult],
        metric_results: list[ParameterResult],
        cycle_summary_stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]],
    ) -> list[ParameterResult]:
        cycle_time_results: list[ParameterResult] = []
        if len(cycle_anchor_events) >= 2:
            for idx in range(len(cycle_anchor_events) - 1):
                current_event = cycle_anchor_events[idx]
                next_event = cycle_anchor_events[idx + 1]
                if current_event.epoch_ms is None or next_event.epoch_ms is None:
                    continue
                cycle_time_results.append(
                    _mk_result(
                        "cycle_time",
                        "cycle time",
                        current_event.cycle_no,
                        None,
                        current_event.chip_name or next_event.chip_name,
                        current_event,
                        next_event,
                        float(next_event.epoch_ms - current_event.epoch_ms),
                        current_event.source_file,
                        "derived",
                        component="Workflow",
                        instrument_scope=current_event.instrument_scope or next_event.instrument_scope,
                        side_scope=current_event.side_scope or next_event.side_scope,
                        side_group=current_event.side_group or next_event.side_group,
                        chip_position=current_event.chip_position or next_event.chip_position,
                        chuck_no=current_event.chuck_no or next_event.chuck_no,
                        slot_no=current_event.slot_no or next_event.slot_no,
                        stage_key=current_event.stage_key or next_event.stage_key,
                        side_confidence=max(float(current_event.side_confidence or 0.0), float(next_event.side_confidence or 0.0)) or None,
                        side_evidence={**current_event.side_evidence, **next_event.side_evidence},
                        extra={"method": "current_imaging_cycle_anchor"},
                    )
                )
        else:
            threshold, expected = _definition_values("cycle_time")
            sorted_stats = sorted(
                cycle_summary_stats.items(),
                key=lambda item: (
                    item[0][0] if item[0][0] is not None else -1,
                    item[0][1] or "",
                    item[0][2] or "",
                ),
            )
            for (cycle_no, side_scope, chip_name), stats in sorted_stats:
                min_start = stats["min_start"]
                max_end = stats["max_end"]
                total_ms = None
                if min_start is not None and max_end is not None:
                    total_ms = float(int(max_end) - int(min_start))
                elif bool(stats["has_nonzero_duration"]):
                    total_ms = float(stats["duration_sum"])
                duration_seconds = _safe_seconds(total_ms)
                cycle_time_results.append(
                    ParameterResult(
                        parameter_name="cycle_time",
                        parameter_display_name="cycle time",
                        cycle=cycle_no,
                        slide=None,
                        instrument_scope="Whole Instrument",
                        side_scope=side_scope,
                        side_group=infer_side_group(side_scope),
                        chip_name=chip_name,
                        duration_seconds=duration_seconds,
                        duration_ms=total_ms,
                        start_time=None,
                        end_time=None,
                        start_message=None,
                        end_message=None,
                        source_file=None,
                        source_type="derived",
                        threshold=threshold,
                        expected=expected,
                        is_exceed=bool(duration_seconds is not None and threshold is not None and duration_seconds > threshold),
                        component="Workflow",
                        side_confidence=0.95 if side_scope else None,
                        side_evidence={"method": "step_summary_fallback", "side_scope": side_scope} if side_scope else {"method": "step_summary_fallback"},
                        extra={
                            "started_at_epoch_ms": min_start,
                            "ended_at_epoch_ms": max_end,
                            "method": "step_summary_fallback",
                        },
                    )
                )

        cycle_time_results = collapse_cycle_time_results(cycle_time_results)
        results = cycle_time_results + direct_duration_results + pairing_results + metric_results
        results.sort(
            key=lambda item: (
                item.cycle if item.cycle is not None else -1,
                item.parameter_name,
                item.slide or "",
                item.start_time or "",
            )
        )
        return results

    def _build_error_cluster_rows(
        self,
        counter: Counter[str],
        bounds: dict[str, dict[str, int | None]],
        representatives: dict[str, dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for signature, count in counter.most_common(limit):
            representative = representatives[signature]
            boundary = bounds.get(signature, {})
            rows.append(
                {
                    "task_id": self.task_id,
                    "normalized_signature": signature,
                    "error_family": representative.get("error_family"),
                    "severity": representative.get("severity"),
                    "representative_message": representative.get("display_signature"),
                    "representative_exception": representative.get("exception_type"),
                    "component": representative.get("component"),
                    "count": count,
                    "first_seen_epoch_ms": boundary.get("first"),
                    "last_seen_epoch_ms": boundary.get("last"),
                }
            )
        return rows
