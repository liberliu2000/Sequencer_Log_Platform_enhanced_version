from __future__ import annotations

import gc
import json
import mimetypes
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.llm.context import ContextConfig, compress_records
from app.models.db_models import ErrorClusterModel, LLMAnalysisResultModel, NormalizedEventModel, ParameterResultModel, StepSummaryModel, TaskAuditLogModel, UploadTaskModel
from app.repositories.task_repository import TaskRepository
from app.schemas.common import NormalizedEvent, ParameterResult, StepSummary
from app.services.cycle_service import _definition_values, _event_time_text, _safe_seconds
from app.services.parameter_definitions import PARAMETER_DEFINITIONS, PAIRING_RULES
from app.services.perf_cache import TTLCache
from app.services.performance_service import PerformanceService
from app.services.streaming_aggregation import StreamingAggregationCoordinator
from app.utils.error_family import get_error_family_metadata
from app.utils.timeparse import format_seconds

_SETTINGS = get_settings()
_QUERY_CACHE = TTLCache(max_entries=_SETTINGS.service_cache_max_entries, ttl_seconds=_SETTINGS.service_cache_ttl_seconds)


class QueryService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.performance = PerformanceService()

    def get_task_or_raise(self, task_uuid: str) -> UploadTaskModel:
        task = self.db.scalar(select(UploadTaskModel).where(UploadTaskModel.task_uuid == task_uuid))
        if not task:
            raise ValueError("任务不存在")
        return task

    def _cache_key(self, task_id: int, name: str, **params: Any) -> str:
        task = self.db.get(UploadTaskModel, task_id)
        stamp = getattr(task, "updated_at", None)
        stamp_text = stamp.isoformat() if isinstance(stamp, datetime) else str(stamp or "")
        extras = "|".join(f"{k}={params[k]}" for k in sorted(params))
        return f"task:{task_id}:{stamp_text}:{name}:{extras}"

    def _cached(self, key: str, factory: Callable[[], Any]) -> Any:
        if not self.settings.enable_service_cache:
            return factory()
        cached = _QUERY_CACHE.get(key)
        if cached is not None:
            return cached
        value = factory()
        _QUERY_CACHE.set(key, value)
        return value

    @staticmethod
    def _row_value(row: Any, field: str) -> Any:
        if isinstance(row, dict):
            return row.get(field)
        getter = getattr(row, "get", None)
        if callable(getter):
            try:
                return getter(field)
            except Exception:
                pass
        mapping = getattr(row, "_mapping", None)
        if mapping is not None:
            return mapping.get(field)
        return getattr(row, field, None)

    def _event_extra(self, ev: Any) -> dict[str, Any]:
        if isinstance(ev, dict):
            raw = ev.get("extra_json", ev)
        elif isinstance(ev, str):
            raw = ev
        else:
            raw = self._row_value(ev, "extra_json")
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _llm_extra(self, raw: Any) -> Any:
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return raw

    def _error_family_fields(self, family: str | None) -> dict[str, Any]:
        meta = get_error_family_metadata(family)
        return {
            "error_family": family,
            "error_family_display": meta["label"],
            "error_family_description": meta["description"],
        }

    def _epoch_to_seconds(self, epoch_ms: int | None) -> str | None:
        if epoch_ms is None:
            return None
        return datetime.fromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")

    def _convert_duration(self, ms: float | None, unit: str) -> float | None:
        if ms is None:
            return None
        if unit == "ms":
            return round(float(ms), 3)
        if unit == "s":
            return round(float(ms) / 1000.0, 6)
        if unit == "min":
            return round(float(ms) / 60000.0, 6)
        if unit == "h":
            return round(float(ms) / 3600000.0, 6)
        return round(float(ms), 3)

    def _dict_to_step(self, row: dict[str, Any]) -> StepSummary:
        return StepSummary(
            cycle_no=row.get("cycle_no"),
            parameter_name=row.get("parameter_name"),
            sub_step=str(row.get("sub_step") or ""),
            component=row.get("component"),
            chip_name=row.get("chip_name"),
            start_epoch_ms=row.get("start_epoch_ms"),
            end_epoch_ms=row.get("end_epoch_ms"),
            duration_ms=row.get("duration_ms"),
            threshold_ms=row.get("threshold_ms"),
            is_over_threshold=bool(row.get("is_over_threshold")),
            start_time_text=row.get("start_time_text"),
            end_time_text=row.get("end_time_text"),
        )

    def _orm_event_to_schema(self, ev: Any) -> NormalizedEvent:
        return NormalizedEvent(
            source_file=self._row_value(ev, "source_file"),
            parser_name=self._row_value(ev, "parser_name"),
            original_time_text=self._row_value(ev, "original_time_text"),
            parsed_datetime=self._row_value(ev, "parsed_datetime"),
            epoch_ms=self._row_value(ev, "epoch_ms"),
            formatted_ms=self._row_value(ev, "formatted_ms"),
            level=self._row_value(ev, "level") or "INFO",
            component=self._row_value(ev, "component"),
            module=self._row_value(ev, "module"),
            thread=self._row_value(ev, "thread"),
            method_name=self._row_value(ev, "method_name"),
            class_name=self._row_value(ev, "class_name"),
            source_path=self._row_value(ev, "source_path"),
            line_no=self._row_value(ev, "line_no"),
            message=self._row_value(ev, "message") or "",
            raw_text=self._row_value(ev, "raw_text") or "",
            cycle_no=self._row_value(ev, "cycle_no"),
            sub_step=self._row_value(ev, "sub_step"),
            chip_name=self._row_value(ev, "chip_name"),
            stage_name=self._row_value(ev, "stage_name"),
            board_name=self._row_value(ev, "board_name"),
            event_kind=self._row_value(ev, "event_kind"),
            direction=self._row_value(ev, "direction"),
            duration_ms=self._row_value(ev, "duration_ms"),
            status=self._row_value(ev, "status"),
            error_code=self._row_value(ev, "error_code"),
            exception_type=self._row_value(ev, "exception_type"),
            normalized_signature=self._row_value(ev, "normalized_signature"),
            error_family=self._row_value(ev, "error_family"),
            severity=self._row_value(ev, "severity"),
            cycle_inferred=bool(self._row_value(ev, "cycle_inferred")),
            cycle_infer_method=self._row_value(ev, "cycle_infer_method"),
            cycle_infer_confidence=self._row_value(ev, "cycle_infer_confidence"),
            cycle_infer_reason=self._row_value(ev, "cycle_infer_reason"),
            extra_json=self._event_extra(ev),
        )

    def _load_all_event_schemas(self, task_id: int) -> list[NormalizedEvent]:
        key = self._cache_key(task_id, "all_event_schemas")
        def factory():
            stmt = (
                select(*NormalizedEventModel.__table__.c)
                .where(NormalizedEventModel.task_id == task_id)
                .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
            )
            return [self._orm_event_to_schema(row) for row in self.db.execute(stmt).mappings()]
        return self._cached(key, factory)

    def list_events(self, task_id: int, component: str | None = None, level: str | None = None, cycle_no: int | None = None, chip_name: str | None = None, search: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        stmt = select(
            NormalizedEventModel.id,
            NormalizedEventModel.formatted_ms,
            NormalizedEventModel.parsed_datetime,
            NormalizedEventModel.level,
            NormalizedEventModel.component,
            NormalizedEventModel.module,
            NormalizedEventModel.cycle_no,
            NormalizedEventModel.sub_step,
            NormalizedEventModel.chip_name,
            NormalizedEventModel.method_name,
            NormalizedEventModel.exception_type,
            NormalizedEventModel.error_code,
            NormalizedEventModel.message,
            NormalizedEventModel.source_file,
            NormalizedEventModel.extra_json,
            NormalizedEventModel.cycle_inferred,
            NormalizedEventModel.cycle_infer_method,
            NormalizedEventModel.cycle_infer_confidence,
            NormalizedEventModel.cycle_infer_reason,
        ).where(NormalizedEventModel.task_id == task_id)
        count_stmt = select(func.count()).select_from(NormalizedEventModel).where(NormalizedEventModel.task_id == task_id)
        if component:
            stmt = stmt.where(NormalizedEventModel.component == component)
            count_stmt = count_stmt.where(NormalizedEventModel.component == component)
        if level:
            stmt = stmt.where(NormalizedEventModel.level == level.upper())
            count_stmt = count_stmt.where(NormalizedEventModel.level == level.upper())
        if cycle_no is not None:
            stmt = stmt.where(NormalizedEventModel.cycle_no == cycle_no)
            count_stmt = count_stmt.where(NormalizedEventModel.cycle_no == cycle_no)
        if chip_name:
            stmt = stmt.where(NormalizedEventModel.chip_name == chip_name)
            count_stmt = count_stmt.where(NormalizedEventModel.chip_name == chip_name)
        if search:
            stmt = stmt.where(NormalizedEventModel.message.contains(search))
            count_stmt = count_stmt.where(NormalizedEventModel.message.contains(search))
        total = int(self.db.scalar(count_stmt) or 0)
        stmt = stmt.order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc()).offset(max(0, offset)).limit(limit)
        rows = self.db.execute(stmt).mappings()
        output = []
        for r in rows:
            extra = self._event_extra(r)
            output.append({
                "id": r["id"],
                "time": r["formatted_ms"],
                "time_sec": format_seconds(r["parsed_datetime"]),
                "level": r["level"],
                "component": r["component"],
                "module": r["module"],
                "cycle_no": r["cycle_no"],
                "sub_step": r["sub_step"],
                "chip_name": r["chip_name"],
                "method_name": r["method_name"],
                "exception_type": r["exception_type"],
                "error_code": r["error_code"],
                "message": r["message"],
                "source_file": r["source_file"],
                "cycle_inferred": extra.get("cycle_inferred", r["cycle_inferred"]),
                "cycle_infer_method": extra.get("cycle_infer_method", r["cycle_infer_method"]),
                "cycle_infer_confidence": extra.get("cycle_infer_confidence", r["cycle_infer_confidence"]),
                "cycle_infer_reason": extra.get("cycle_infer_reason", r["cycle_infer_reason"]),
            })
        return {"items": output, "total": total, "offset": offset, "limit": limit}

    def list_cycles(self, task_id: int) -> list[int]:
        key = self._cache_key(task_id, "cycles")
        return self._cached(key, lambda: [int(r[0]) for r in self.db.execute(select(NormalizedEventModel.cycle_no).where(NormalizedEventModel.task_id == task_id, NormalizedEventModel.cycle_no.is_not(None)).distinct().order_by(NormalizedEventModel.cycle_no.asc())) if r[0] is not None])

    def get_dashboard(self, task_id: int) -> dict[str, Any]:
        key = self._cache_key(task_id, "dashboard")
        def factory():
            file_count = self.db.scalar(select(func.count(func.distinct(NormalizedEventModel.source_file))).where(NormalizedEventModel.task_id == task_id)) or 0
            total_events = self.db.scalar(select(func.count()).select_from(NormalizedEventModel).where(NormalizedEventModel.task_id == task_id)) or 0
            total_errors = self.db.scalar(select(func.count()).select_from(NormalizedEventModel).where(NormalizedEventModel.task_id == task_id, NormalizedEventModel.normalized_signature.is_not(None))) or 0
            unique_error_count = self.db.scalar(select(func.count(func.distinct(NormalizedEventModel.normalized_signature))).where(NormalizedEventModel.task_id == task_id, NormalizedEventModel.normalized_signature.is_not(None))) or 0
            top_errors = self.get_error_clusters(task_id, limit=10)["items"]
            components = list(self.db.execute(select(NormalizedEventModel.component, func.count()).where(NormalizedEventModel.task_id == task_id, NormalizedEventModel.normalized_signature.is_not(None)).group_by(NormalizedEventModel.component).order_by(func.count().desc())))
            return {
                "file_count": file_count,
                "total_events": total_events,
                "total_errors": total_errors,
                "unique_error_count": unique_error_count,
                "top_errors": top_errors,
                "component_distribution": [{"component": c or "未知", "count": n} for c, n in components],
            }
        return self._cached(key, factory)

    def get_step_summaries(self, task_id: int, cycle_no: int | None = None, parameter_name: str | None = None, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        stmt = select(
            StepSummaryModel.cycle_no,
            StepSummaryModel.parameter_name,
            StepSummaryModel.sub_step,
            StepSummaryModel.component,
            StepSummaryModel.chip_name,
            StepSummaryModel.start_epoch_ms,
            StepSummaryModel.end_epoch_ms,
            StepSummaryModel.duration_ms,
            StepSummaryModel.threshold_ms,
            StepSummaryModel.is_over_threshold,
            StepSummaryModel.start_time_text,
            StepSummaryModel.end_time_text,
        ).where(StepSummaryModel.task_id == task_id)
        count_stmt = select(func.count()).select_from(StepSummaryModel).where(StepSummaryModel.task_id == task_id)
        if cycle_no is not None:
            stmt = stmt.where(StepSummaryModel.cycle_no == cycle_no)
            count_stmt = count_stmt.where(StepSummaryModel.cycle_no == cycle_no)
        if parameter_name:
            stmt = stmt.where(StepSummaryModel.parameter_name == parameter_name)
            count_stmt = count_stmt.where(StepSummaryModel.parameter_name == parameter_name)
        total = int(self.db.scalar(count_stmt) or 0)
        stmt = stmt.order_by(StepSummaryModel.cycle_no.asc(), StepSummaryModel.start_epoch_ms.asc(), StepSummaryModel.sub_step.asc()).offset(max(0, offset)).limit(limit)
        rows = self.db.execute(stmt).mappings()
        items = [{
            "cycle_no": r["cycle_no"],
            "parameter_name": r["parameter_name"],
            "sub_step": r["sub_step"],
            "component": r["component"],
            "module": r["component"],
            "chip_name": r["chip_name"],
            "start_epoch_ms": r["start_epoch_ms"],
            "end_epoch_ms": r["end_epoch_ms"],
            "duration_ms": r["duration_ms"],
            "threshold_ms": r["threshold_ms"],
            "is_over_threshold": r["is_over_threshold"],
            "start_time_text": r["start_time_text"],
            "end_time_text": r["end_time_text"],
            "start_time_sec": self._epoch_to_seconds(r["start_epoch_ms"]),
            "end_time_sec": self._epoch_to_seconds(r["end_epoch_ms"]),
            "message": r["sub_step"],
            "source_file": None,
        } for r in rows]
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def get_cycle_summaries(self, task_id: int, unit: str = "ms") -> list[dict]:
        key = self._cache_key(task_id, "cycle_summaries", unit=unit)
        def factory():
            output = []
            stmt = (
                select(
                    StepSummaryModel.cycle_no.label("cycle_no"),
                    StepSummaryModel.chip_name.label("chip_name"),
                    func.min(StepSummaryModel.start_epoch_ms).label("started_at"),
                    func.max(StepSummaryModel.end_epoch_ms).label("ended_at"),
                    func.sum(StepSummaryModel.duration_ms).label("duration_sum"),
                    func.max(func.abs(func.coalesce(StepSummaryModel.duration_ms, 0))).label("max_abs_duration"),
                )
                .where(StepSummaryModel.task_id == task_id)
                .group_by(StepSummaryModel.cycle_no, StepSummaryModel.chip_name)
                .order_by(StepSummaryModel.cycle_no.asc(), StepSummaryModel.chip_name.asc())
            )
            for row in self.db.execute(stmt).mappings():
                started_at = row["started_at"]
                ended_at = row["ended_at"]
                total_duration_ms = None
                if started_at is not None and ended_at is not None:
                    total_duration_ms = float(ended_at - started_at)
                elif row["max_abs_duration"]:
                    total_duration_ms = float(row["duration_sum"] or 0.0)
                item = {
                    "cycle_no": row["cycle_no"],
                    "chip_name": row["chip_name"],
                    "total_duration_ms": total_duration_ms,
                    "started_at": started_at,
                    "ended_at": ended_at,
                }
                item["started_at_text"] = self._epoch_to_seconds(item.get("started_at"))
                item["ended_at_text"] = self._epoch_to_seconds(item.get("ended_at"))
                item["total_duration_value"] = self._convert_duration(item.get("total_duration_ms"), unit)
                item["duration_unit"] = unit
                output.append(item)
            return output
        return self._cached(key, factory)

    def get_parameter_definitions(self) -> list[dict[str, Any]]:
        return [d.__dict__ for d in PARAMETER_DEFINITIONS]

    def _parameter_result_row_to_dict(self, row: Any) -> dict[str, Any]:
        extra = self._llm_extra(self._row_value(row, "extra_json"))
        if not isinstance(extra, dict):
            extra = {}
        return {
            "parameter_name": self._row_value(row, "parameter_name"),
            "parameter_display_name": self._row_value(row, "parameter_display_name"),
            "cycle": self._row_value(row, "cycle_no"),
            "slide": self._row_value(row, "slide"),
            "chip_name": self._row_value(row, "chip_name"),
            "duration_seconds": self._row_value(row, "duration_seconds"),
            "duration_ms": self._row_value(row, "duration_ms"),
            "start_time": self._row_value(row, "start_time_text"),
            "end_time": self._row_value(row, "end_time_text"),
            "start_message": self._row_value(row, "start_message"),
            "end_message": self._row_value(row, "end_message"),
            "source_file": self._row_value(row, "source_file"),
            "source_type": self._row_value(row, "source_type"),
            "threshold": self._row_value(row, "threshold"),
            "expected": self._row_value(row, "expected"),
            "is_exceed": bool(self._row_value(row, "is_exceed")),
            "component": self._row_value(row, "component"),
            "start_event_id": self._row_value(row, "start_event_id"),
            "end_event_id": self._row_value(row, "end_event_id"),
            "extra": extra,
        }

    def _load_parameter_results_from_store(self, task_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(*ParameterResultModel.__table__.c)
            .where(ParameterResultModel.task_id == task_id)
            .order_by(
                ParameterResultModel.cycle_no.asc(),
                ParameterResultModel.parameter_name.asc(),
                ParameterResultModel.slide.asc(),
                ParameterResultModel.start_time_text.asc(),
                ParameterResultModel.id.asc(),
            )
        )
        return [self._parameter_result_row_to_dict(row) for row in self.db.execute(stmt).mappings()]

    def _load_cycle_summary_stats(self, task_id: int) -> dict[tuple[int | None, str | None], dict[str, Any]]:
        stats: dict[tuple[int | None, str | None], dict[str, Any]] = defaultdict(
            lambda: {
                "min_start": None,
                "max_end": None,
                "duration_sum": 0.0,
                "has_nonzero_duration": False,
            }
        )
        stmt = (
            select(
                StepSummaryModel.cycle_no.label("cycle_no"),
                StepSummaryModel.chip_name.label("chip_name"),
                func.min(StepSummaryModel.start_epoch_ms).label("min_start"),
                func.max(StepSummaryModel.end_epoch_ms).label("max_end"),
                func.sum(StepSummaryModel.duration_ms).label("duration_sum"),
                func.max(func.abs(func.coalesce(StepSummaryModel.duration_ms, 0))).label("max_abs_duration"),
            )
            .where(StepSummaryModel.task_id == task_id)
            .group_by(StepSummaryModel.cycle_no, StepSummaryModel.chip_name)
        )
        for row in self.db.execute(stmt).mappings():
            stats[(row["cycle_no"], row["chip_name"])] = {
                "min_start": row["min_start"],
                "max_end": row["max_end"],
                "duration_sum": float(row["duration_sum"] or 0.0),
                "has_nonzero_duration": bool(row["max_abs_duration"]),
            }
        return stats

    def _parameter_result_to_mapping(self, task_id: int, result: ParameterResult) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "parameter_name": result.parameter_name,
            "parameter_display_name": result.parameter_display_name,
            "cycle_no": result.cycle,
            "slide": result.slide,
            "chip_name": result.chip_name,
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
            "extra_json": json.dumps(result.extra or {}, ensure_ascii=False, default=str),
        }

    def _rebuild_parameter_results_from_events(self, task_id: int) -> list[dict[str, Any]]:
        coordinator = StreamingAggregationCoordinator(self.db, task_id, self.settings)
        pairing_open_maps = {rule.parameter_name: defaultdict(deque) for rule in PAIRING_RULES}
        direct_duration_results: list[ParameterResult] = []
        pairing_results: list[ParameterResult] = []
        metric_state: dict[tuple[int | None, str | None, str], dict[str, Any]] = defaultdict(
            lambda: {"sum_duration_ms": 0.0, "row_count": 0, "exemplar": None, "raw_duration_ms_list": []}
        )
        cycle_anchor_events = []
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
            NormalizedEventModel.cycle_no,
            NormalizedEventModel.sub_step,
            NormalizedEventModel.chip_name,
            NormalizedEventModel.stage_name,
            NormalizedEventModel.board_name,
            NormalizedEventModel.event_kind,
            NormalizedEventModel.direction,
            NormalizedEventModel.duration_ms,
            NormalizedEventModel.status,
            NormalizedEventModel.error_code,
            NormalizedEventModel.exception_type,
            NormalizedEventModel.extra_json,
        )

        for rows in coordinator._iter_event_batches(columns=columns, limit=coordinator.scan_batch_size):
            for row in rows:
                event = coordinator._row_to_event(row)
                coordinator._collect_direct_duration_result(event, direct_duration_results)
                coordinator._consume_pairing_result(event, pairing_open_maps, pairing_results)
                coordinator._collect_metric_state(event, metric_state)
                if event.epoch_ms is not None and "current imaging cycle" in (event.message or "").lower():
                    cycle_anchor_events.append(event)
            coordinator._apply_memory_guard("query_parameter_result_rebuild")
            gc.collect()

        metric_results: list[ParameterResult] = []
        threshold, expected = _definition_values("row_scan_metric_avg")
        for (cycle_no, chip_name, metric_name), stats in metric_state.items():
            row_count = int(stats["row_count"])
            exemplar = stats["exemplar"]
            if row_count <= 0 or exemplar is None:
                continue
            avg_ms = float(stats["sum_duration_ms"]) / row_count
            metric_results.append(
                ParameterResult(
                    parameter_name="row_scan_metric_avg",
                    parameter_display_name=f"row scan metric avg::{metric_name}",
                    cycle=cycle_no,
                    slide=None,
                    chip_name=chip_name,
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
                    start_event_id=getattr(exemplar, "id", None),
                    end_event_id=getattr(exemplar, "id", None),
                    extra={
                        "metric_stage": metric_name,
                        "row_count": row_count,
                        "raw_duration_ms_list": list(stats["raw_duration_ms_list"]),
                    },
                )
            )

        results = coordinator._finalize_parameter_results(
            cycle_anchor_events=cycle_anchor_events,
            direct_duration_results=direct_duration_results,
            pairing_results=pairing_results,
            metric_results=metric_results,
            cycle_summary_stats=self._load_cycle_summary_stats(task_id),
        )
        TaskRepository(self.db).replace_parameter_results(
            task_id,
            (self._parameter_result_to_mapping(task_id, result) for result in results),
            batch_size=max(200, int(self.settings.metrics_batch_size) * 4),
        )
        gc.collect()
        return [result.model_dump(mode="json") for result in results]

    def get_parameter_results(self, task_id: int) -> list[dict[str, Any]]:
        key = self._cache_key(task_id, "parameter_results")
        def factory():
            stored_rows = self._load_parameter_results_from_store(task_id)
            if stored_rows:
                return stored_rows

            task = self.db.get(UploadTaskModel, task_id)
            if task is not None and str(task.status or "").lower() not in {"completed", "failed", "error"}:
                return []
            return self._rebuild_parameter_results_from_events(task_id)
        return self._cached(key, factory)

    def get_parameter_series(self, task_id: int, parameter_name: str, unit: str = "s") -> list[dict[str, Any]]:
        rows = [r for r in self.get_parameter_results(task_id) if r["parameter_name"] == parameter_name]
        out = []
        for r in rows:
            duration_ms = r.get("duration_ms")
            threshold = r.get("threshold")
            expected = r.get("expected")
            out.append({
                **r,
                "duration_value": self._convert_duration(duration_ms, unit),
                "duration_unit": unit,
                "threshold_value": threshold if unit == "s" else self._convert_duration((threshold or 0) * 1000 if threshold is not None else None, unit),
                "expected_value": expected if unit == "s" else self._convert_duration((expected or 0) * 1000 if expected is not None else None, unit),
            })
        return out

    def get_row_scan_metric_stage_series(self, task_id: int, unit: str = "ms") -> list[dict[str, Any]]:
        rows = [r for r in self.get_parameter_results(task_id) if r["parameter_name"] == "row_scan_metric_avg"]
        out = []
        for r in rows:
            stage = r.get("extra", {}).get("metric_stage")
            out.append({
                "cycle": r.get("cycle"),
                "metric_stage": stage,
                "chip_name": r.get("chip_name"),
                "duration_ms": r.get("duration_ms"),
                "duration_seconds": r.get("duration_seconds"),
                "duration_value": self._convert_duration(r.get("duration_ms"), unit),
                "duration_unit": unit,
                "row_count": r.get("extra", {}).get("row_count"),
                "source_file": r.get("source_file"),
            })
        return sorted(out, key=lambda x: (x["metric_stage"] or "", x["cycle"] or -1))

    def _event_schema_to_llm_row(self, ev: NormalizedEvent) -> dict[str, Any]:
        return {
            "time": ev.formatted_ms or format_seconds(ev.parsed_datetime),
            "epoch_ms": ev.epoch_ms,
            "level": ev.level,
            "component": ev.component,
            "module": ev.module,
            "method_name": ev.method_name,
            "exception_type": ev.exception_type,
            "cycle_no": ev.cycle_no,
            "sub_step": ev.sub_step,
            "chip_name": ev.chip_name,
            "message": ev.message,
            "source_file": ev.source_file,
            "normalized_signature": ev.normalized_signature,
            **self._error_family_fields(ev.error_family),
            "severity": ev.severity,
            "status": ev.status,
        }

    def _build_signature_cluster(self, task_id: int, signature: str, matched_events: list[NormalizedEvent]) -> dict[str, Any]:
        cluster_row = self.db.scalar(
            select(ErrorClusterModel).where(
                ErrorClusterModel.task_id == task_id,
                ErrorClusterModel.normalized_signature == signature,
            )
        )
        representative = next((e for e in matched_events if e.message), matched_events[0] if matched_events else None)
        error_code = next((e.error_code for e in matched_events if e.error_code), None)
        if cluster_row:
            return {
                "normalized_signature": cluster_row.normalized_signature,
                "display_signature": cluster_row.representative_message,
                **self._error_family_fields(cluster_row.error_family),
                "severity": cluster_row.severity,
                "component": cluster_row.component,
                "count": cluster_row.count,
                "representative_message": cluster_row.representative_message,
                "representative_exception": cluster_row.representative_exception,
                "error_code": error_code,
                "first_seen_text": self._epoch_to_seconds(cluster_row.first_seen_epoch_ms),
                "last_seen_text": self._epoch_to_seconds(cluster_row.last_seen_epoch_ms),
            }

        first = matched_events[0] if matched_events else None
        last = matched_events[-1] if matched_events else None
        return {
            "normalized_signature": signature,
            "display_signature": representative.message if representative else signature,
            **self._error_family_fields(first.error_family if first else None),
            "severity": first.severity if first else None,
            "component": first.component if first else None,
            "count": len(matched_events),
            "representative_message": representative.message if representative else signature,
            "representative_exception": representative.exception_type if representative else None,
            "error_code": error_code,
            "first_seen_text": self._epoch_to_seconds(first.epoch_ms if first else None),
            "last_seen_text": self._epoch_to_seconds(last.epoch_ms if last else None),
        }

    def get_context_for_signature(self, task_id: int, signature: str, stage: str = "light", token_budget: int | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        if token_budget is None:
            if stage == "light":
                token_budget = self.settings.llm_context_stage1_token_budget
            elif stage == "medium":
                token_budget = int((self.settings.llm_context_stage1_token_budget + self.settings.llm_context_max_token_budget) / 2)
            else:
                token_budget = self.settings.llm_context_max_token_budget
        empty_summary = {
            "raw_line_count": 0,
            "compressed_line_count": 0,
            "raw_estimated_tokens": 0,
            "compressed_estimated_tokens": 0,
            "compression_ratio": 0.0,
            "token_compression_ratio": 0.0,
            "token_budget": token_budget,
        }

        if stage == "light":
            max_signature_rows = 40
            max_time_rows = 120
            max_component_rows = max(20, int(self.settings.llm_context_related_component_limit) * 2)
            max_cycle_rows = max(20, int(self.settings.llm_context_related_cycle_limit) * 2)
            max_chip_rows = 20
            max_candidate_rows = 220
        elif stage == "medium":
            max_signature_rows = 80
            max_time_rows = 240
            max_component_rows = max(30, int(self.settings.llm_context_related_component_limit) * 3)
            max_cycle_rows = max(30, int(self.settings.llm_context_related_cycle_limit) * 3)
            max_chip_rows = 40
            max_candidate_rows = 420
        else:
            max_signature_rows = 120
            max_time_rows = 360
            max_component_rows = max(40, int(self.settings.llm_context_related_component_limit) * 4)
            max_cycle_rows = max(40, int(self.settings.llm_context_related_cycle_limit) * 4)
            max_chip_rows = 60
            max_candidate_rows = 700

        matched_stmt = (
            select(NormalizedEventModel)
            .where(
                NormalizedEventModel.task_id == task_id,
                NormalizedEventModel.normalized_signature == signature,
            )
            .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
            .limit(max_signature_rows)
        )
        matched_rows = list(self.db.scalars(matched_stmt))
        if not matched_rows:
            return (
                {
                    "normalized_signature": signature,
                    "display_signature": signature,
                    **self._error_family_fields(None),
                    "severity": None,
                    "component": None,
                    "count": 0,
                    "representative_message": signature,
                    "representative_exception": None,
                    "first_seen_text": None,
                    "last_seen_text": None,
                },
                [],
                {"stage": stage, "context_summary": empty_summary},
            )

        matched_events = [self._orm_event_to_schema(r) for r in matched_rows]
        anchor_epochs = [e.epoch_ms for e in matched_events if e.epoch_ms is not None]
        min_epoch = min(anchor_epochs) if anchor_epochs else None
        max_epoch = max(anchor_epochs) if anchor_epochs else None
        anchor_components = {e.component for e in matched_events if e.component}
        anchor_cycles = {e.cycle_no for e in matched_events if e.cycle_no is not None}
        anchor_chip_names = {e.chip_name for e in matched_events if e.chip_name}

        candidate_rows: dict[int, NormalizedEventModel] = {r.id: r for r in matched_rows}
        time_window_ms = max(0, int(self.settings.llm_context_time_window_seconds) * 1000)

        def _append(stmt, hard_limit: int):
            for row in self.db.scalars(stmt.limit(hard_limit)):
                candidate_rows.setdefault(row.id, row)
                if len(candidate_rows) >= max_candidate_rows:
                    break

        if min_epoch is not None and max_epoch is not None and len(candidate_rows) < max_candidate_rows:
            time_stmt = (
                select(NormalizedEventModel)
                .where(
                    NormalizedEventModel.task_id == task_id,
                    NormalizedEventModel.epoch_ms.is_not(None),
                    NormalizedEventModel.epoch_ms >= (min_epoch - time_window_ms),
                    NormalizedEventModel.epoch_ms <= (max_epoch + time_window_ms),
                )
                .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
            )
            _append(time_stmt, max_time_rows)

        if anchor_components and len(candidate_rows) < max_candidate_rows:
            comp_stmt = (
                select(NormalizedEventModel)
                .where(
                    NormalizedEventModel.task_id == task_id,
                    NormalizedEventModel.component.in_(sorted(anchor_components)),
                )
                .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
            )
            _append(comp_stmt, max_component_rows)

        if anchor_cycles and len(candidate_rows) < max_candidate_rows:
            cycle_stmt = (
                select(NormalizedEventModel)
                .where(
                    NormalizedEventModel.task_id == task_id,
                    NormalizedEventModel.cycle_no.in_(sorted(anchor_cycles)),
                )
                .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
            )
            _append(cycle_stmt, max_cycle_rows)

        if anchor_chip_names and len(candidate_rows) < max_candidate_rows:
            chip_stmt = (
                select(NormalizedEventModel)
                .where(
                    NormalizedEventModel.task_id == task_id,
                    NormalizedEventModel.chip_name.in_(sorted(anchor_chip_names)),
                )
                .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
            )
            _append(chip_stmt, max_chip_rows)

        related_events = [self._orm_event_to_schema(r) for r in candidate_rows.values()]
        related_events.sort(key=lambda e: (e.epoch_ms is None, e.epoch_ms or 0, e.source_file, e.message))
        if len(related_events) > max_candidate_rows:
            related_events = related_events[:max_candidate_rows]
        raw_context_rows = [self._event_schema_to_llm_row(ev) for ev in related_events]

        config = ContextConfig(
            pre_lines=self.settings.llm_context_pre_lines,
            post_lines=self.settings.llm_context_post_lines,
            time_window_seconds=self.settings.llm_context_time_window_seconds,
            related_component_limit=self.settings.llm_context_related_component_limit,
            related_cycle_limit=self.settings.llm_context_related_cycle_limit,
            max_stack_frames=self.settings.llm_context_max_stack_frames,
            max_token_budget=self.settings.llm_context_max_token_budget,
            stage1_token_budget=self.settings.llm_context_stage1_token_budget,
        )
        compressed_rows, summary = compress_records(raw_context_rows, config, token_budget=token_budget)
        cluster = self._build_signature_cluster(task_id, signature, matched_events)
        stats = {
            "stage": stage,
            "signature": signature,
            "matched_event_count": len(matched_events),
            "anchor_components": sorted(anchor_components),
            "anchor_cycles": sorted(anchor_cycles),
            "anchor_chip_names": sorted(anchor_chip_names),
            "candidate_row_count": len(raw_context_rows),
            "context_summary": summary,
        }
        return cluster, compressed_rows, stats

    def get_cluster_context(self, task_id: int, signature: str) -> dict[str, Any]:
        cluster, context_rows, stats = self.get_context_for_signature(task_id, signature, stage="deep")
        return {"cluster": cluster, "records": context_rows, "summary": stats.get("context_summary", {}), "stats": stats}

    def get_movement_timeline(self, task_id: int, cycle_no: int | None = None, track_order: str = "default") -> list[dict[str, Any]]:
        stmt = select(
            StepSummaryModel.cycle_no,
            StepSummaryModel.sub_step,
            StepSummaryModel.component,
            StepSummaryModel.chip_name,
            StepSummaryModel.start_epoch_ms,
            StepSummaryModel.end_epoch_ms,
            StepSummaryModel.duration_ms,
            StepSummaryModel.threshold_ms,
            StepSummaryModel.is_over_threshold,
            StepSummaryModel.start_time_text,
            StepSummaryModel.end_time_text,
        ).where(StepSummaryModel.task_id == task_id)
        if cycle_no is not None:
            stmt = stmt.where(StepSummaryModel.cycle_no == cycle_no)
        stmt = stmt.order_by(StepSummaryModel.cycle_no.asc(), StepSummaryModel.start_epoch_ms.asc(), StepSummaryModel.sub_step.asc())
        output = []
        lanes: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for r in self.db.execute(stmt).mappings():
            sub_step = str(r["sub_step"] or "")
            component = str(r["component"] or "")
            if not (r["start_epoch_ms"] and r["end_epoch_ms"]):
                continue
            movement_like = any(key in sub_step.lower() for key in ["move", "align", "scan", "transfer", "temperature", "priming", "coarsetheta", "finealign"]) or component in {"XYZStage", "Scanner_1", "Scanner_2", "Workflow", "StageRunMgr", "ImagingMetrics"}
            if not movement_like:
                continue
            base_track = f"{r['component'] or '未知部件'} | Cycle {r['cycle_no'] or 'NA'}"
            lane_idx = 0
            start_ms = r["start_epoch_ms"]
            end_ms = r["end_epoch_ms"]
            existing = lanes[base_track]
            while lane_idx < len(existing) and start_ms < existing[lane_idx][1]:
                lane_idx += 1
            if lane_idx == len(existing):
                existing.append((start_ms, end_ms))
            else:
                existing[lane_idx] = (start_ms, end_ms)
            track = base_track if lane_idx == 0 else f"{base_track} | lane {lane_idx+1}"
            item = dict(r)
            item["module"] = item.get("component")
            item["message"] = item.get("sub_step")
            item["start_time_sec"] = self._epoch_to_seconds(start_ms)
            item["end_time_sec"] = self._epoch_to_seconds(end_ms)
            item["source_file"] = None
            item["start"] = datetime.fromtimestamp(start_ms / 1000).isoformat(timespec="seconds")
            item["end"] = datetime.fromtimestamp(end_ms / 1000).isoformat(timespec="seconds")
            item["track"] = track
            output.append(item)
        if track_order == "cycle":
            output.sort(key=lambda x: ((x.get("cycle_no") is None), x.get("cycle_no") or -1, x.get("track") or ""))
        return output

    def get_timeline_error_points(self, task_id: int, cycle_no: int | None = None) -> list[dict[str, Any]]:
        stmt = (
            select(
                NormalizedEventModel.id,
                NormalizedEventModel.cycle_no,
                NormalizedEventModel.component,
                NormalizedEventModel.module,
                NormalizedEventModel.sub_step,
                NormalizedEventModel.epoch_ms,
                NormalizedEventModel.formatted_ms,
                NormalizedEventModel.message,
                NormalizedEventModel.normalized_signature,
                NormalizedEventModel.error_family,
                NormalizedEventModel.severity,
                NormalizedEventModel.error_code,
                NormalizedEventModel.exception_type,
                NormalizedEventModel.source_file,
            )
            .where(
                NormalizedEventModel.task_id == task_id,
                NormalizedEventModel.normalized_signature.is_not(None),
                NormalizedEventModel.epoch_ms.is_not(None),
            )
            .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
        )
        if cycle_no is not None:
            stmt = stmt.where(NormalizedEventModel.cycle_no == cycle_no)
        points: list[dict[str, Any]] = []
        for r in self.db.execute(stmt).mappings():
            epoch_ms = r["epoch_ms"]
            if epoch_ms is None:
                continue
            points.append({
                "event_id": r["id"],
                "cycle_no": r["cycle_no"],
                "component": r["component"],
                "module": r["module"],
                "sub_step": r["sub_step"],
                "track": f"{r['component'] or '\u93c8\ue046\u7161\u95ae\u3124\u6b22'} | Cycle {r['cycle_no'] or 'NA'}",
                "time": datetime.fromtimestamp(epoch_ms / 1000).isoformat(timespec="seconds"),
                "time_text": r["formatted_ms"] or self._epoch_to_seconds(epoch_ms),
                "epoch_ms": epoch_ms,
                "message": r["message"],
                "normalized_signature": r["normalized_signature"],
                **self._error_family_fields(r["error_family"]),
                "severity": r["severity"],
                "error_code": r["error_code"],
                "exception_type": r["exception_type"],
                "source_file": r["source_file"],
            })
        return points

    def get_operational_metrics(self, task_id: int, cycle_no: int | None = None) -> dict[str, Any]:
        photo_names = {"imaging_time_real", "coarse_theta", "finealign", "row_scan"}
        temperature_names = {"temperature_rise_n", "temperature_rise_f", "temperature_drop_n", "temperature_drop_f"}
        result = {
            "photo_summary": [],
            "transfer_summary": [],
            "cpas_priming_summary": [],
            "cpas_summary": [],
            "temperature_times": [],
            "metric_stage_avg": self.get_row_scan_metric_stage_series(task_id, unit="ms"),
        }
        for row in self.get_parameter_results(task_id):
            if cycle_no is not None and row.get("cycle") != cycle_no:
                continue
            name = row["parameter_name"]
            if name in photo_names:
                result["photo_summary"].append(row)
            elif name == "transfer_time":
                result["transfer_summary"].append(row)
            elif name == "cpas_priming":
                result["cpas_priming_summary"].append(row)
            elif name == "cpas_time":
                result["cpas_summary"].append(row)
            elif name in temperature_names:
                result["temperature_times"].append(row)
        return result

    def get_temperature_cycle_validation(self, task_id: int) -> list[dict[str, Any]]:
        target_names = {"temperature_rise_n", "temperature_rise_f", "temperature_drop_n", "temperature_drop_f"}
        grouped: dict[int | None, dict[str, Any]] = defaultdict(lambda: {"cycle": None, "rise_count": 0, "drop_count": 0, "records": []})
        for r in self.get_parameter_results(task_id):
            if r["parameter_name"] not in target_names:
                continue
            item = grouped[r.get("cycle")]
            item["cycle"] = r.get("cycle")
            if "rise" in r["parameter_name"]:
                item["rise_count"] += 1
            else:
                item["drop_count"] += 1
            item["records"].append(r)
        out = []
        for cycle, item in grouped.items():
            ok = item["rise_count"] == 3 and item["drop_count"] == 3
            out.append({**item, "is_expected": ok, "validation_message": "OK" if ok else "不满足 3 次升温 + 3 次降温"})
        return sorted(out, key=lambda x: x["cycle"] if x["cycle"] is not None else -1)

    def get_substep_cycle_series(self, task_id: int, agg_mode: str = "mean", unit: str = "s") -> list[dict[str, Any]]:
        out = []
        agg_fn = func.sum if agg_mode == "sum" else func.avg
        stmt = (
            select(
                StepSummaryModel.cycle_no.label("cycle_no"),
                StepSummaryModel.sub_step.label("sub_step"),
                agg_fn(StepSummaryModel.duration_ms).label("agg_duration_ms"),
                func.count(StepSummaryModel.id).label("sample_count"),
            )
            .where(
                StepSummaryModel.task_id == task_id,
                StepSummaryModel.cycle_no.is_not(None),
                StepSummaryModel.duration_ms.is_not(None),
            )
            .group_by(StepSummaryModel.cycle_no, StepSummaryModel.sub_step)
            .order_by(StepSummaryModel.sub_step.asc(), StepSummaryModel.cycle_no.asc())
        )
        for row in self.db.execute(stmt).mappings():
            val_ms = float(row["agg_duration_ms"] or 0.0)
            out.append({
                "cycle_no": row["cycle_no"],
                "sub_step": row["sub_step"] or "unknown",
                "duration_ms": round(val_ms, 3),
                "duration_value": self._convert_duration(val_ms, unit),
                "duration_unit": unit,
                "sample_count": int(row["sample_count"] or 0),
            })
        return out

    def get_error_clusters(self, task_id: int, offset: int = 0, limit: int = 100) -> dict[str, Any]:
        count_stmt = select(func.count()).select_from(ErrorClusterModel).where(ErrorClusterModel.task_id == task_id)
        total = int(self.db.scalar(count_stmt) or 0)
        stmt = (
            select(
                ErrorClusterModel.id,
                ErrorClusterModel.normalized_signature,
                ErrorClusterModel.error_family,
                ErrorClusterModel.severity,
                ErrorClusterModel.component,
                ErrorClusterModel.count,
                ErrorClusterModel.representative_message,
                ErrorClusterModel.first_seen_epoch_ms,
                ErrorClusterModel.last_seen_epoch_ms,
            )
            .where(ErrorClusterModel.task_id == task_id)
            .order_by(ErrorClusterModel.count.desc(), ErrorClusterModel.id.asc())
            .offset(max(0, offset))
            .limit(limit)
        )
        rows = self.db.execute(stmt).mappings()
        items = [{
            "id": r["id"],
            "normalized_signature": r["normalized_signature"],
            "display_signature": r["representative_message"],
            **self._error_family_fields(r["error_family"]),
            "severity": r["severity"],
            "component": r["component"],
            "count": r["count"],
            "representative_message": r["representative_message"],
            "first_seen_text": self._epoch_to_seconds(r["first_seen_epoch_ms"]),
            "last_seen_text": self._epoch_to_seconds(r["last_seen_epoch_ms"]),
        } for r in rows]
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def get_error_regression_trend(self, task_id: int, signature: str | None = None, family: str | None = None, bucket: str = "day") -> list[dict[str, Any]]:
        grouped: dict[str, int] = defaultdict(int)
        stmt = (
            select(
                NormalizedEventModel.normalized_signature,
                NormalizedEventModel.error_family,
                NormalizedEventModel.parsed_datetime,
            )
            .where(
                NormalizedEventModel.task_id == task_id,
                NormalizedEventModel.normalized_signature.is_not(None),
            )
            .order_by(NormalizedEventModel.epoch_ms.asc())
        )
        for r in self.db.execute(stmt).mappings():
            if signature and r["normalized_signature"] != signature:
                continue
            if family and r["error_family"] != family:
                continue
            parsed_datetime = r["parsed_datetime"]
            if not parsed_datetime:
                continue
            key = parsed_datetime.strftime("%Y-%m-%d" if bucket == "day" else "%Y-W%W")
            grouped[key] += 1
        return [{"bucket": k, "count": v} for k, v in sorted(grouped.items())]

    def list_task_files(self, task_id: int, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        task = self.db.get(UploadTaskModel, task_id)
        if not task:
            return {"items": [], "total": 0, "offset": offset, "limit": limit}
        root = Path(task.stored_path)
        if not root.exists():
            return {"items": [], "total": 0, "offset": offset, "limit": limit}
        rows = []
        for p in root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                rows.append({"relative_path": rel, "size_bytes": p.stat().st_size, "mime_type": mimetypes.guess_type(p.name)[0] or "application/octet-stream"})
        rows = sorted(rows, key=lambda x: x["relative_path"])
        total = len(rows)
        return {"items": rows[offset: offset + limit], "total": total, "offset": offset, "limit": limit}

    def preview_task_file(self, task_id: int, relative_path: str, max_lines: int = 200) -> dict[str, Any]:
        task = self.db.get(UploadTaskModel, task_id)
        if not task:
            raise ValueError("任务不存在")
        root = Path(task.stored_path)
        file_path = (root / relative_path).resolve()
        if root.resolve() not in file_path.parents and file_path != root.resolve():
            raise ValueError("非法路径")
        if not file_path.exists() or not file_path.is_file():
            raise ValueError("文件不存在")
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        with file_path.open("rb") as handle:
            raw = handle.read(1024 * 128)
        binary = b"\x00" in raw
        if binary:
            return {"relative_path": relative_path, "mime_type": mime, "encoding": None, "binary": True, "line_count": 1, "preview": [raw[: min(len(raw), 256)].hex(" ")]}
        for encoding in ["utf-8", "utf-8-sig", "gbk", "latin1"]:
            try:
                lines: list[str] = []
                with file_path.open("r", encoding=encoding, errors="replace") as handle:
                    for _ in range(max_lines):
                        line = handle.readline()
                        if not line:
                            break
                        lines.append(line.rstrip("\r\n"))
                return {"relative_path": relative_path, "mime_type": mime, "encoding": encoding, "binary": False, "line_count": len(lines), "preview": lines}
            except Exception:
                continue
        return {"relative_path": relative_path, "mime_type": mime, "encoding": None, "binary": False, "line_count": 0, "preview": []}

    def get_audit_logs(self, task_id: int, limit: int = 200) -> list[dict[str, Any]]:
        key = self._cache_key(task_id, "audit_logs", limit=limit)
        def factory():
            rows = list(self.db.scalars(select(TaskAuditLogModel).where(TaskAuditLogModel.task_id == task_id).order_by(TaskAuditLogModel.created_at.desc()).limit(limit)))
            return [{"id": r.id, "task_id": r.task_id, "task_uuid": r.task_uuid, "action": r.action, "status": r.status, "stage": r.stage, "detail": r.detail, "actor": r.actor, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
        return self._cached(key, factory)

    def get_llm_results(self, task_id: int, limit: int = 200) -> list[dict[str, Any]]:
        key = self._cache_key(task_id, "llm_results", limit=limit)
        def factory():
            rows = list(self.db.scalars(select(LLMAnalysisResultModel).where(LLMAnalysisResultModel.task_id == task_id).order_by(LLMAnalysisResultModel.created_at.desc()).limit(limit)))
            return [{"id": r.id, "task_id": r.task_id, "normalized_signature": r.normalized_signature, "model_name": r.model_name, "prompt_version": getattr(r, "prompt_version", None), "analysis_stage": getattr(r, "analysis_stage", None), "chinese_summary": r.chinese_summary, "request_payload": self._llm_extra(r.request_payload), "response_payload": self._llm_extra(r.response_payload), "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
        return self._cached(key, factory)

    def get_performance_summary(self, task_uuid: str) -> dict[str, Any]:
        return self.performance.read_summary(task_uuid)
