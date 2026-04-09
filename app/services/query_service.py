from __future__ import annotations

from bisect import bisect_right
import gc
import json
import mimetypes
import re
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.llm.context import ContextConfig, compress_records
from app.models.db_models import ErrorClusterModel, LLMAnalysisResultModel, NormalizedEventModel, ParameterResultModel, StepSummaryModel, TaskAuditLogModel, UploadTaskModel
from app.repositories.task_repository import TaskRepository
from app.schemas.common import NormalizedEvent, ParameterResult, StepSummary
from app.services.cycle_service import _definition_values, _event_time_text, _safe_seconds
from app.services.cycle_inference import CURRENT_CYCLE_HINTS, NEXT_CYCLE_HINTS
from app.services.parameter_definitions import PARAMETER_DEFINITIONS, PAIRING_RULES
from app.services.perf_cache import TTLCache
from app.services.performance_service import PerformanceService
from app.services.streaming_aggregation import StreamingAggregationCoordinator
from app.utils.error_family import get_error_family_metadata
from app.utils.side_inference import (
    UNASSIGNED_SCOPE_TOKEN,
    expand_parent_branch_side_family,
    infer_side_group,
    normalize_side_scope,
    repair_scope_inference,
    side_scopes_share_parent_branch_scope,
)
from app.utils.timeparse import format_seconds, parse_datetime, to_epoch_ms

_SETTINGS = get_settings()
_QUERY_CACHE = TTLCache(max_entries=_SETTINGS.service_cache_max_entries, ttl_seconds=_SETTINGS.service_cache_ttl_seconds)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
UTC_TZ = ZoneInfo("UTC")
TIMELINE_ERROR_NOISE_REGEXES = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bbad message format\b",
        r"\bunknown message format\b",
    ]
]
SUBSTEP_CURRENT_CYCLE_HINTS = tuple(
    dict.fromkeys(
        list(CURRENT_CYCLE_HINTS)
        + [
            "coarsetheta",
            "coarsethetawithoutmovestage",
            "finealign",
            "imaging_time_real",
            "imaging",
            "row scan",
            "scan",
            "cpas time",
            "cpas completed",
        ]
    )
)
SUBSTEP_NEXT_CYCLE_HINTS = tuple(
    dict.fromkeys(
        list(NEXT_CYCLE_HINTS)
        + [
            "fill ir",
            "priming",
            "reagent priming",
            "wash",
            "washing",
            "chuck stage",
            "transfer from imager to chuck",
            "transfer to chuck",
            "cycle finished",
        ]
    )
)


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
        dt = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC_TZ).astimezone(BEIJING_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _epoch_to_iso_text(self, epoch_ms: int | None) -> str | None:
        if epoch_ms is None:
            return None
        dt = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC_TZ).astimezone(BEIJING_TZ)
        return dt.isoformat(timespec="seconds")

    @staticmethod
    def _preferred_time_text(*values: Any) -> str | None:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return None

    def _time_text_to_epoch_ms(self, value: Any) -> int | None:
        text = self._preferred_time_text(value)
        if not text:
            return None
        parsed = parse_datetime(text)
        if parsed is not None:
            return to_epoch_ms(parsed)
        return None

    def _parameter_time_epoch_ms(self, row: dict[str, Any]) -> int | None:
        extra = self._llm_extra(row.get("extra")) if isinstance(row.get("extra"), str) else (row.get("extra") or {})
        if isinstance(extra, dict):
            for key in ("started_at_epoch_ms", "ended_at_epoch_ms"):
                value = extra.get(key)
                if value is not None:
                    try:
                        return int(value)
                    except Exception:
                        pass
        for key in ("start_epoch_ms", "end_epoch_ms", "epoch_ms"):
            value = row.get(key)
            if value is not None:
                try:
                    return int(value)
                except Exception:
                    pass
        return self._time_text_to_epoch_ms(row.get("start_time") or row.get("start_time_text") or row.get("end_time") or row.get("end_time_text"))

    def _substep_time_epoch_ms(self, row: dict[str, Any]) -> int | None:
        for key in ("start_epoch_ms", "min_start_epoch_ms", "end_epoch_ms", "max_end_epoch_ms"):
            value = row.get(key)
            if value is not None:
                try:
                    return int(value)
                except Exception:
                    pass
        return self._time_text_to_epoch_ms(
            row.get("start_time_text")
            or row.get("end_time_text")
            or row.get("start_time")
            or row.get("end_time")
        )

    def _timeline_time_bounds(self, row: dict[str, Any]) -> dict[str, Any] | None:
        start_epoch_ms = None
        end_epoch_ms = None
        for key in ("start_epoch_ms", "min_start_epoch_ms"):
            value = row.get(key)
            if value is not None:
                try:
                    start_epoch_ms = int(value)
                    break
                except Exception:
                    pass
        for key in ("end_epoch_ms", "max_end_epoch_ms"):
            value = row.get(key)
            if value is not None:
                try:
                    end_epoch_ms = int(value)
                    break
                except Exception:
                    pass

        start_time_text = self._preferred_time_text(row.get("start_time_text"), row.get("start_time"))
        end_time_text = self._preferred_time_text(row.get("end_time_text"), row.get("end_time"))
        if start_epoch_ms is None and start_time_text:
            start_epoch_ms = self._time_text_to_epoch_ms(start_time_text)
        if end_epoch_ms is None and end_time_text:
            end_epoch_ms = self._time_text_to_epoch_ms(end_time_text)

        numeric_duration_ms: float | None = None
        if row.get("duration_ms") is not None:
            try:
                numeric_duration_ms = float(row["duration_ms"])
            except Exception:
                numeric_duration_ms = None

        inferred = False
        if start_epoch_ms is None and end_epoch_ms is not None and numeric_duration_ms is not None:
            start_epoch_ms = max(0, int(round(end_epoch_ms - numeric_duration_ms)))
            inferred = True
        if end_epoch_ms is None and start_epoch_ms is not None and numeric_duration_ms is not None:
            end_epoch_ms = int(round(start_epoch_ms + numeric_duration_ms))
            inferred = True

        if start_epoch_ms is None or end_epoch_ms is None or end_epoch_ms < start_epoch_ms:
            return None

        return {
            "start_epoch_ms": start_epoch_ms,
            "end_epoch_ms": end_epoch_ms,
            "start": self._preferred_time_text(start_time_text, self._epoch_to_seconds(start_epoch_ms), self._epoch_to_iso_text(start_epoch_ms)),
            "end": self._preferred_time_text(end_time_text, self._epoch_to_seconds(end_epoch_ms), self._epoch_to_iso_text(end_epoch_ms)),
            "start_time_sec": self._epoch_to_seconds(start_epoch_ms),
            "end_time_sec": self._epoch_to_seconds(end_epoch_ms),
            "time_bounds_inferred": inferred,
        }

    @staticmethod
    def _coerce_cycle_no(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except Exception:
            return None

    def _trusted_substep_cycle_anchor_catalog(self, task_id: int) -> dict[tuple[str | None, str | None], list[dict[str, int]]]:
        key = self._cache_key(task_id, "trusted_substep_cycle_anchor_catalog")

        def factory():
            grouped: dict[tuple[str | None, str | None], dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
            for row in self.get_parameter_results(task_id):
                if row.get("parameter_name") not in {"imaging_time_real", "cycle_time"}:
                    continue
                cycle_no = self._coerce_cycle_no(row.get("cycle"))
                time_epoch_ms = self._parameter_time_epoch_ms(row)
                if cycle_no is None or time_epoch_ms is None:
                    continue
                repaired = self._repair_scope_fields(dict(row))
                side_scope = normalize_side_scope(repaired.get("side_scope"))
                chip_name = repaired.get("chip_name")
                grouped[(side_scope, chip_name)][cycle_no].append(int(time_epoch_ms))
                grouped[(side_scope, None)][cycle_no].append(int(time_epoch_ms))
                grouped[(None, None)][cycle_no].append(int(time_epoch_ms))

            catalog: dict[tuple[str | None, str | None], list[dict[str, int]]] = {}
            for anchor_key, cycle_map in grouped.items():
                anchors = [
                    {"cycle": cycle_no, "epoch_ms": min(epochs)}
                    for cycle_no, epochs in cycle_map.items()
                    if epochs
                ]
                anchors.sort(key=lambda item: (item["epoch_ms"], item["cycle"]))
                if anchors:
                    catalog[anchor_key] = anchors
            return catalog

        return self._cached(key, factory)

    def _substep_cycle_anchor_rows(
        self,
        task_id: int,
        *,
        side_scope: str | None,
        chip_name: str | None,
    ) -> list[dict[str, int]]:
        catalog = self._trusted_substep_cycle_anchor_catalog(task_id)
        normalized_side = normalize_side_scope(side_scope)
        for anchor_key in (
            (normalized_side, chip_name or None),
            (normalized_side, None),
            (None, None),
        ):
            anchors = catalog.get(anchor_key)
            if anchors:
                return anchors
        return []

    @staticmethod
    def _is_plausible_cycle_between_anchors(
        cycle_no: int | None,
        prev_anchor: dict[str, int] | None,
        next_anchor: dict[str, int] | None,
    ) -> bool:
        if cycle_no is None:
            return False
        if prev_anchor and next_anchor:
            low = min(int(prev_anchor["cycle"]), int(next_anchor["cycle"]))
            high = max(int(prev_anchor["cycle"]), int(next_anchor["cycle"]))
            return high - low <= 4 and low <= cycle_no <= high
        if prev_anchor:
            return 0 <= cycle_no - int(prev_anchor["cycle"]) <= 2
        if next_anchor:
            return 0 <= int(next_anchor["cycle"]) - cycle_no <= 2
        return False

    @staticmethod
    def _substep_cycle_relation(*parts: Any) -> str:
        text = " ".join(str(part or "") for part in parts).strip().lower()
        if not text:
            return "nearest"
        if any(token in text for token in SUBSTEP_NEXT_CYCLE_HINTS):
            return "next"
        if any(token in text for token in SUBSTEP_CURRENT_CYCLE_HINTS):
            return "current"
        return "nearest"

    @classmethod
    def _rank_aligned_cycle_from_anchors(
        cls,
        *,
        index: int,
        total_rows: int,
        anchors: list[dict[str, int]],
    ) -> int | None:
        if not anchors or total_rows <= 0:
            return None
        if total_rows == 1:
            return int(anchors[0]["cycle"])
        anchor_index = round(index * max(len(anchors) - 1, 0) / max(total_rows - 1, 1))
        anchor_index = max(0, min(anchor_index, len(anchors) - 1))
        return int(anchors[anchor_index]["cycle"])

    def _resolve_substep_cycle_from_anchors(
        self,
        task_id: int,
        row: dict[str, Any],
        *,
        rank_index: int | None = None,
        rank_total: int | None = None,
    ) -> tuple[int | None, str]:
        side_scope = row.get("side_scope")
        chip_name = row.get("chip_name")
        anchors = self._substep_cycle_anchor_rows(task_id, side_scope=side_scope, chip_name=chip_name)
        original_cycle = self._coerce_cycle_no(row.get("cycle_no"))
        if not anchors:
            return original_cycle, "original_no_anchor"

        time_epoch_ms = self._substep_time_epoch_ms(row)
        relation = self._substep_cycle_relation(row.get("sub_step"), row.get("parameter_name"), row.get("component"))
        if time_epoch_ms is not None:
            anchor_times = [int(anchor["epoch_ms"]) for anchor in anchors]
            anchor_pos = bisect_right(anchor_times, time_epoch_ms)
            prev_anchor = anchors[anchor_pos - 1] if anchor_pos > 0 else None
            next_anchor = anchors[anchor_pos] if anchor_pos < len(anchors) else None

            if self._is_plausible_cycle_between_anchors(original_cycle, prev_anchor, next_anchor):
                return original_cycle, "plausible_original_between_anchors"

            if relation == "next" and next_anchor is not None:
                return int(next_anchor["cycle"]), "time_anchor_next_cycle"
            if relation == "current" and prev_anchor is not None:
                return int(prev_anchor["cycle"]), "time_anchor_current_cycle"
            if prev_anchor is not None and next_anchor is not None:
                prev_time = int(prev_anchor["epoch_ms"])
                next_time = int(next_anchor["epoch_ms"])
                if abs(time_epoch_ms - prev_time) <= abs(next_time - time_epoch_ms):
                    return int(prev_anchor["cycle"]), "time_anchor_nearest_prev"
                return int(next_anchor["cycle"]), "time_anchor_nearest_next"
            if prev_anchor is not None:
                return int(prev_anchor["cycle"]), "time_anchor_prev_only"
            if next_anchor is not None:
                return int(next_anchor["cycle"]), "time_anchor_next_only"

        if (
            rank_index is not None
            and rank_total is not None
            and rank_total > 1
            and abs(rank_total - len(anchors)) <= 3
        ):
            ranked_cycle = self._rank_aligned_cycle_from_anchors(index=rank_index, total_rows=rank_total, anchors=anchors)
            if ranked_cycle is not None:
                return ranked_cycle, "rank_anchor_fallback"

        if original_cycle is not None:
            anchor_cycles = {int(anchor["cycle"]) for anchor in anchors}
            if original_cycle in anchor_cycles:
                return original_cycle, "original_in_anchor_set"

        return original_cycle or int(anchors[0]["cycle"]), "fallback_original_or_first_anchor"

    @staticmethod
    def _series_scope_label(side_scope: str | None, chip_name: str | None) -> str:
        if side_scope and chip_name:
            return f"{side_scope} | {chip_name}"
        if side_scope:
            return str(side_scope)
        if chip_name:
            return f"Unassigned | {chip_name}"
        return "Unassigned"

    @staticmethod
    def _is_uncertain_side(side_scope: str | None, side_confidence: Any) -> bool:
        if not side_scope:
            return True
        try:
            return float(side_confidence or 0.0) < 0.75
        except Exception:
            return False

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

    @staticmethod
    def _numeric_sort_value(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:
            return None

    @classmethod
    def _sort_trend_points(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def key(item: dict[str, Any]) -> tuple[Any, ...]:
            x_sort = cls._numeric_sort_value(item.get("x_axis_sort_value"))
            time_epoch_ms = cls._numeric_sort_value(item.get("time_epoch_ms"))
            return (
                0 if x_sort is not None else 1,
                x_sort if x_sort is not None else float("inf"),
                item.get("series_name") or "",
                time_epoch_ms if time_epoch_ms is not None else float("inf"),
                item.get("x_axis_label") or "",
                item.get("parameter_name") or item.get("metric_stage") or item.get("sub_step") or "",
                item.get("chip_name") or "",
            )

        return sorted(rows, key=key)

    @classmethod
    def _collapse_trend_points(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in cls._sort_trend_points(rows):
            x_sort = cls._numeric_sort_value(row.get("x_axis_sort_value"))
            key = (
                row.get("series_name") or "",
                row.get("x_axis_type") or "",
                x_sort if x_sort is not None else row.get("x_axis_label") or "",
                row.get("x_axis_label") or "",
            )
            grouped.setdefault(key, []).append(row)

        output: list[dict[str, Any]] = []
        for bucket in grouped.values():
            exemplar = dict(bucket[0])
            sample_count = 0
            for item in bucket:
                sample_count += int(item.get("sample_count") or 1)
            exemplar["sample_count"] = sample_count
            exemplar["aggregated_point_count"] = len(bucket)

            for field in ("duration_value", "duration_ms", "duration_seconds"):
                values: list[float] = []
                for item in bucket:
                    value = cls._numeric_sort_value(item.get(field))
                    if value is not None:
                        values.append(value)
                if values:
                    exemplar[field] = sum(values) / len(values)

            output.append(exemplar)

        return cls._sort_trend_points(output)

    @classmethod
    def _is_timeline_error_relevant(cls, item: dict[str, Any]) -> bool:
        message = str(item.get("message") or item.get("normalized_signature") or "").strip()
        if not message:
            return False
        lowered = message.lower()
        if any(pattern.search(lowered) for pattern in TIMELINE_ERROR_NOISE_REGEXES):
            return False
        component = str(item.get("component") or item.get("module") or "").strip()
        sub_step = item.get("sub_step") or message
        return cls._is_movement_like(sub_step, component)

    @staticmethod
    def _normalize_filter_values(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item and item.strip()]
        if isinstance(value, (list, tuple, set)):
            output: list[str] = []
            for item in value:
                output.extend(QueryService._normalize_filter_values(item))
            return output
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _apply_optional_in_filter(stmt, count_stmt, column, values: list[str]):
        if not values:
            return stmt, count_stmt
        include_unassigned = UNASSIGNED_SCOPE_TOKEN in values
        exact_values = [value for value in values if value != UNASSIGNED_SCOPE_TOKEN]
        conditions = []
        if exact_values:
            conditions.append(column.in_(exact_values))
        if include_unassigned:
            conditions.append(column.is_(None))
        if not conditions:
            return stmt, count_stmt
        condition = or_(*conditions)
        return stmt.where(condition), count_stmt.where(condition)

    @staticmethod
    def _apply_side_scope_filter_with_repair_support(stmt, count_stmt, column, values: list[str]):
        if not values:
            return stmt, count_stmt
        include_unassigned = UNASSIGNED_SCOPE_TOKEN in values
        exact_values = [value for value in values if value != UNASSIGNED_SCOPE_TOKEN]
        conditions = []
        if exact_values:
            conditions.append(column.in_(exact_values))
            conditions.append(column.is_(None))
        elif include_unassigned:
            conditions.append(column.is_(None))
        if not conditions:
            return stmt, count_stmt
        condition = or_(*conditions)
        return stmt.where(condition), count_stmt.where(condition)

    @classmethod
    def _value_matches_filter(cls, actual: Any, values: list[str]) -> bool:
        if not values:
            return True
        normalized_actual = None if actual in (None, "") else str(actual)
        if normalized_actual is None:
            return UNASSIGNED_SCOPE_TOKEN in values
        return normalized_actual in values

    @staticmethod
    def _timeline_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item.get("start_epoch_ms")
            if item.get("start_epoch_ms") is not None
            else item.get("epoch_ms")
            if item.get("epoch_ms") is not None
            else float("inf"),
            item.get("cycle_no") if item.get("cycle_no") is not None else -1,
            item.get("track") or "",
        )

    def _load_distinct_side_scopes(self, model: Any, task_id: int) -> list[str]:
        rows = self.db.execute(
            select(model.side_scope)
            .where(
                model.task_id == task_id,
                model.side_scope.is_not(None),
            )
            .distinct()
            .order_by(model.side_scope.asc())
        )
        return [
            str(value)
            for value in (row[0] for row in rows)
            if str(value or "").strip()
        ]

    def _expand_timeline_side_scope_filters(self, model: Any, task_id: int, values: list[str]) -> list[str]:
        if not values:
            return []
        requested = [normalize_side_scope(value) or str(value) for value in values if value != UNASSIGNED_SCOPE_TOKEN]
        include_unassigned = UNASSIGNED_SCOPE_TOKEN in values
        if not requested:
            return [UNASSIGNED_SCOPE_TOKEN] if include_unassigned else []
        known_side_scopes = self._load_distinct_side_scopes(model, task_id)
        expanded: list[str] = []
        for value in requested:
            expanded.extend(expand_parent_branch_side_family(value, known_side_scopes))
        if include_unassigned:
            expanded.append(UNASSIGNED_SCOPE_TOKEN)
        return list(dict.fromkeys(expanded))

    @classmethod
    def _value_matches_timeline_side_filter(cls, actual: Any, values: list[str]) -> bool:
        if not values:
            return True
        normalized_actual = normalize_side_scope(actual)
        if normalized_actual is None:
            return UNASSIGNED_SCOPE_TOKEN in values
        for value in values:
            if value == UNASSIGNED_SCOPE_TOKEN:
                continue
            if side_scopes_share_parent_branch_scope(normalized_actual, value):
                return True
        return False

    @classmethod
    def _row_matches_scope_filters(
        cls,
        row: dict[str, Any],
        *,
        side_scopes: list[str] | None = None,
        side_groups: list[str] | None = None,
        chip_names: list[str] | None = None,
    ) -> bool:
        return (
            cls._value_matches_filter(row.get("side_scope"), side_scopes or [])
            and cls._value_matches_filter(row.get("side_group"), side_groups or [])
            and cls._value_matches_filter(row.get("chip_name"), chip_names or [])
        )

    @classmethod
    def _row_matches_timeline_scope_filters(
        cls,
        row: dict[str, Any],
        *,
        side_scopes: list[str] | None = None,
        side_groups: list[str] | None = None,
        chip_names: list[str] | None = None,
    ) -> bool:
        return (
            cls._value_matches_timeline_side_filter(row.get("side_scope"), side_scopes or [])
            and cls._value_matches_filter(row.get("side_group"), side_groups or [])
            and cls._value_matches_filter(row.get("chip_name"), chip_names or [])
        )

    @staticmethod
    def _scope_display(value: str | None) -> str:
        return str(value or "Unassigned")

    def _repair_scope_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        current_evidence = self._llm_extra(item.get("side_evidence")) or {}
        inference = repair_scope_inference(
            source_file=item.get("source_file"),
            message=item.get("message"),
            raw_text=item.get("raw_text"),
            sub_step=item.get("sub_step"),
            start_message=item.get("start_message"),
            end_message=item.get("end_message"),
            parameter_name=item.get("parameter_name"),
            parameter_display_name=item.get("parameter_display_name"),
            slide=item.get("slide"),
            chip_name=item.get("chip_name"),
            stage_name=item.get("stage_name"),
            stage_key=item.get("stage_key"),
            chuck_no=item.get("chuck_no"),
            slot_no=item.get("slot_no"),
            instrument_scope=item.get("instrument_scope"),
            side_scope=item.get("side_scope"),
            side_group=item.get("side_group"),
            side_confidence=item.get("side_confidence"),
            side_evidence=current_evidence,
        )
        item["side_scope"] = inference.side_scope
        item["side_group"] = inference.side_group or infer_side_group(inference.side_scope)
        item["chip_name"] = item.get("chip_name") or inference.chip_name
        item["chip_position"] = item.get("chip_position") or inference.chip_position
        item["chuck_no"] = item.get("chuck_no") or inference.chuck_no
        item["slot_no"] = item.get("slot_no") or inference.slot_no
        item["stage_key"] = item.get("stage_key") or inference.stage_key
        item["side_confidence"] = inference.side_confidence
        item["side_evidence"] = inference.side_evidence or current_evidence
        return item

    @staticmethod
    def _timeline_granularity(value: str | None) -> str:
        normalized = str(value or "component").strip().lower().replace("+", "_")
        if normalized in {"sidechip", "chip", "chip_name"}:
            return "side_chip"
        if normalized not in {"component", "side", "side_chip"}:
            return "component"
        return normalized

    @classmethod
    def _build_timeline_base_track(
        cls,
        *,
        component: str | None,
        cycle_no: int | None,
        side_scope: str | None,
        chip_name: str | None,
        track_granularity: str,
    ) -> str:
        granularity = cls._timeline_granularity(track_granularity)
        component_label = str(component or "Unknown Component")
        cycle_label = f"Cycle {cycle_no}" if cycle_no is not None else "Cycle NA"
        side_label = cls._scope_display(side_scope)
        chip_label = cls._scope_display(chip_name)

        if granularity == "side":
            return f"{side_label} | {cycle_label}"
        if granularity == "side_chip":
            return f"{side_label} | {chip_label} | {cycle_label}"
        if side_scope or chip_name:
            if chip_name:
                return f"{component_label} | {side_label} | {chip_label} | {cycle_label}"
            return f"{component_label} | {side_label} | {cycle_label}"
        return f"{component_label} | {cycle_label}"

    @staticmethod
    def _is_movement_like(sub_step: str | None, component: str | None) -> bool:
        sub_step_text = str(sub_step or "").lower()
        component_text = str(component or "")
        return any(
            token in sub_step_text
            for token in ["move", "align", "scan", "transfer", "temperature", "priming", "coarsetheta", "finealign", "fill", "wash", "washing"]
        ) or component_text in {"XYZStage", "Scanner_1", "Scanner_2", "Workflow", "StageRunMgr", "ImagingMetrics"}

    def _group_timeline_records_by_side(
        self,
        rows: list[dict[str, Any]],
        *,
        row_key: str,
        render_side_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_rows = [dict(row) for row in rows]
        known_side_order = list(
            dict.fromkeys(
                normalize_side_scope(row.get("side_scope")) or str(row.get("side_scope"))
                for row in normalized_rows
                if row.get("side_scope") not in (None, "")
            )
        )
        uncertain_rows = [row for row in normalized_rows if self._is_uncertain_side(row.get("side_scope"), row.get("side_confidence"))]
        requested_render_sides = [
            normalize_side_scope(value) or str(value)
            for value in (render_side_scopes or [])
            if value not in (None, "", UNASSIGNED_SCOPE_TOKEN)
        ]
        render_side_order = list(dict.fromkeys(requested_render_sides or known_side_order))

        if not render_side_order:
            side_groups = [
                {
                    "side_scope": None,
                    "side_label": "Unassigned",
                    row_key: normalized_rows,
                    "uncertain_count": len(uncertain_rows),
                }
            ]
        else:
            side_groups = []
            for side_scope in render_side_order:
                group_rows: list[dict[str, Any]] = []
                shared_side_scopes: list[str] = []
                shared_count = 0
                for row in normalized_rows:
                    actual_side_scope = normalize_side_scope(row.get("side_scope"))
                    if self._is_uncertain_side(row.get("side_scope"), row.get("side_confidence")):
                        continue
                    if not side_scopes_share_parent_branch_scope(actual_side_scope, side_scope):
                        continue
                    copy_row = dict(row)
                    copy_row["render_side_scope"] = side_scope
                    copy_row["original_side_scope"] = actual_side_scope
                    is_shared = bool(actual_side_scope and actual_side_scope != side_scope)
                    copy_row["is_shared_side_family"] = is_shared
                    if is_shared:
                        shared_count += 1
                        shared_side_scopes.append(actual_side_scope)
                    group_rows.append(copy_row)
                replicated_uncertain = []
                for row in uncertain_rows:
                    copy_row = dict(row)
                    copy_row["is_uncertain_side"] = True
                    copy_row["original_side_scope"] = row.get("side_scope")
                    copy_row["render_side_scope"] = side_scope
                    copy_row["is_shared_side_family"] = False
                    replicated_uncertain.append(copy_row)
                side_groups.append(
                    {
                        "side_scope": side_scope,
                        "side_label": self._scope_display(side_scope),
                        row_key: sorted(
                            group_rows + replicated_uncertain,
                            key=self._timeline_sort_key,
                        ),
                        "uncertain_count": len(replicated_uncertain),
                        "shared_count": shared_count,
                        "shared_side_scopes": list(dict.fromkeys(shared_side_scopes)),
                    }
                )
        return {
            "side_order": render_side_order,
            "by_side": side_groups,
            "unassigned_side_rows": uncertain_rows,
            row_key: normalized_rows,
        }

    def _dict_to_step(self, row: dict[str, Any]) -> StepSummary:
        return StepSummary(
            cycle_no=row.get("cycle_no"),
            parameter_name=row.get("parameter_name"),
            sub_step=str(row.get("sub_step") or ""),
            component=row.get("component"),
            instrument_scope=row.get("instrument_scope"),
            side_scope=row.get("side_scope"),
            side_group=row.get("side_group"),
            chip_name=row.get("chip_name"),
            chip_position=row.get("chip_position"),
            chuck_no=row.get("chuck_no"),
            slot_no=row.get("slot_no"),
            stage_key=row.get("stage_key"),
            start_epoch_ms=row.get("start_epoch_ms"),
            end_epoch_ms=row.get("end_epoch_ms"),
            duration_ms=row.get("duration_ms"),
            threshold_ms=row.get("threshold_ms"),
            is_over_threshold=bool(row.get("is_over_threshold")),
            start_time_text=row.get("start_time_text"),
            end_time_text=row.get("end_time_text"),
            side_confidence=row.get("side_confidence"),
            side_evidence=self._llm_extra(row.get("side_evidence")) if isinstance(row.get("side_evidence"), str) else (row.get("side_evidence") or {}),
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
            instrument_scope=self._row_value(ev, "instrument_scope"),
            side_scope=self._row_value(ev, "side_scope"),
            side_group=self._row_value(ev, "side_group"),
            chip_name=self._row_value(ev, "chip_name"),
            chip_position=self._row_value(ev, "chip_position"),
            chuck_no=self._row_value(ev, "chuck_no"),
            slot_no=self._row_value(ev, "slot_no"),
            stage_key=self._row_value(ev, "stage_key"),
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
            side_confidence=self._row_value(ev, "side_confidence"),
            side_evidence=self._llm_extra(self._row_value(ev, "side_evidence")) or {},
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

    def list_events(
        self,
        task_id: int,
        component: str | None = None,
        level: str | None = None,
        cycle_no: int | None = None,
        chip_name: str | list[str] | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
    ) -> dict[str, Any]:
        chip_names = self._normalize_filter_values(chip_name)
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        stmt = select(
            NormalizedEventModel.id,
            NormalizedEventModel.formatted_ms,
            NormalizedEventModel.parsed_datetime,
            NormalizedEventModel.level,
            NormalizedEventModel.component,
            NormalizedEventModel.module,
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
            NormalizedEventModel.method_name,
            NormalizedEventModel.exception_type,
            NormalizedEventModel.error_code,
            NormalizedEventModel.message,
            NormalizedEventModel.source_file,
            NormalizedEventModel.side_confidence,
            NormalizedEventModel.side_evidence,
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
        stmt, count_stmt = self._apply_optional_in_filter(stmt, count_stmt, NormalizedEventModel.side_scope, side_scope_values)
        stmt, count_stmt = self._apply_optional_in_filter(stmt, count_stmt, NormalizedEventModel.side_group, side_group_values)
        stmt, count_stmt = self._apply_optional_in_filter(stmt, count_stmt, NormalizedEventModel.chip_name, chip_names)
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
                "instrument_scope": r["instrument_scope"],
                "side_scope": r["side_scope"],
                "side_group": r["side_group"],
                "chip_name": r["chip_name"],
                "chip_position": r["chip_position"],
                "chuck_no": r["chuck_no"],
                "slot_no": r["slot_no"],
                "stage_key": r["stage_key"],
                "method_name": r["method_name"],
                "exception_type": r["exception_type"],
                "error_code": r["error_code"],
                "message": r["message"],
                "source_file": r["source_file"],
                "side_confidence": r["side_confidence"],
                "side_evidence": self._llm_extra(r["side_evidence"]) or {},
                "cycle_inferred": extra.get("cycle_inferred", r["cycle_inferred"]),
                "cycle_infer_method": extra.get("cycle_infer_method", r["cycle_infer_method"]),
                "cycle_infer_confidence": extra.get("cycle_infer_confidence", r["cycle_infer_confidence"]),
                "cycle_infer_reason": extra.get("cycle_infer_reason", r["cycle_infer_reason"]),
            })
        return {"items": output, "total": total, "offset": offset, "limit": limit}

    def list_cycles(self, task_id: int) -> list[int]:
        key = self._cache_key(task_id, "cycles")
        return self._cached(key, lambda: [int(r[0]) for r in self.db.execute(select(NormalizedEventModel.cycle_no).where(NormalizedEventModel.task_id == task_id, NormalizedEventModel.cycle_no.is_not(None)).distinct().order_by(NormalizedEventModel.cycle_no.asc())) if r[0] is not None])

    def get_scope_catalog(self, task_id: int) -> dict[str, Any]:
        key = self._cache_key(task_id, "scope_catalog")
        def factory():
            instrument_scope = self.db.scalar(
                select(func.max(NormalizedEventModel.instrument_scope)).where(NormalizedEventModel.task_id == task_id)
            )
            side_rows = list(
                self.db.execute(
                    select(
                        NormalizedEventModel.side_scope,
                        func.max(NormalizedEventModel.side_group).label("side_group"),
                        func.count().label("count"),
                    )
                    .where(NormalizedEventModel.task_id == task_id)
                    .group_by(NormalizedEventModel.side_scope)
                    .order_by(NormalizedEventModel.side_scope.asc())
                ).mappings()
            )
            chip_rows = list(
                self.db.execute(
                    select(
                        NormalizedEventModel.chip_name,
                        func.max(NormalizedEventModel.side_scope).label("side_scope"),
                        func.max(NormalizedEventModel.side_group).label("side_group"),
                        func.max(NormalizedEventModel.chip_position).label("chip_position"),
                        func.count().label("count"),
                    )
                    .where(NormalizedEventModel.task_id == task_id)
                    .group_by(NormalizedEventModel.chip_name)
                    .order_by(NormalizedEventModel.side_scope.asc(), NormalizedEventModel.chip_name.asc())
                ).mappings()
            )
            return {
                "instrument_scope": instrument_scope,
                "sides": [
                    {
                        "value": row["side_scope"] if row["side_scope"] is not None else UNASSIGNED_SCOPE_TOKEN,
                        "label": row["side_scope"] or "Unassigned",
                        "side_scope": row["side_scope"],
                        "side_group": row["side_group"],
                        "count": int(row["count"] or 0),
                    }
                    for row in side_rows
                ],
                "chips": [
                    {
                        "value": row["chip_name"] if row["chip_name"] is not None else UNASSIGNED_SCOPE_TOKEN,
                        "label": f"{(row['side_scope'] if row['chip_name'] is not None else None) or 'Unassigned'} | {row['chip_name'] or 'Unassigned'}",
                        "chip_name": row["chip_name"],
                        "side_scope": row["side_scope"] if row["chip_name"] is not None else None,
                        "side_group": row["side_group"] if row["chip_name"] is not None else None,
                        "chip_position": row["chip_position"],
                        "count": int(row["count"] or 0),
                    }
                    for row in chip_rows
                ],
            }
        return self._cached(key, factory)

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

    def get_step_summaries(
        self,
        task_id: int,
        cycle_no: int | None = None,
        parameter_name: str | None = None,
        offset: int = 0,
        limit: int = 200,
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> dict[str, Any]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        stmt = select(
            StepSummaryModel.cycle_no,
            StepSummaryModel.parameter_name,
            StepSummaryModel.sub_step,
            StepSummaryModel.component,
            StepSummaryModel.instrument_scope,
            StepSummaryModel.side_scope,
            StepSummaryModel.side_group,
            StepSummaryModel.chip_name,
            StepSummaryModel.chip_position,
            StepSummaryModel.chuck_no,
            StepSummaryModel.slot_no,
            StepSummaryModel.stage_key,
            StepSummaryModel.start_epoch_ms,
            StepSummaryModel.end_epoch_ms,
            StepSummaryModel.duration_ms,
            StepSummaryModel.threshold_ms,
            StepSummaryModel.is_over_threshold,
            StepSummaryModel.start_time_text,
            StepSummaryModel.end_time_text,
            StepSummaryModel.side_confidence,
            StepSummaryModel.side_evidence,
        ).where(StepSummaryModel.task_id == task_id)
        count_stmt = select(func.count()).select_from(StepSummaryModel).where(StepSummaryModel.task_id == task_id)
        if cycle_no is not None:
            stmt = stmt.where(StepSummaryModel.cycle_no == cycle_no)
            count_stmt = count_stmt.where(StepSummaryModel.cycle_no == cycle_no)
        if parameter_name:
            stmt = stmt.where(StepSummaryModel.parameter_name == parameter_name)
            count_stmt = count_stmt.where(StepSummaryModel.parameter_name == parameter_name)
        stmt, count_stmt = self._apply_side_scope_filter_with_repair_support(stmt, count_stmt, StepSummaryModel.side_scope, side_scope_values)
        stmt, count_stmt = self._apply_optional_in_filter(stmt, count_stmt, StepSummaryModel.side_group, side_group_values)
        stmt, count_stmt = self._apply_optional_in_filter(stmt, count_stmt, StepSummaryModel.chip_name, chip_value_list)
        total = int(self.db.scalar(count_stmt) or 0)
        stmt = stmt.order_by(StepSummaryModel.cycle_no.asc(), StepSummaryModel.start_epoch_ms.asc(), StepSummaryModel.sub_step.asc()).offset(max(0, offset)).limit(limit)
        rows = self.db.execute(stmt).mappings()
        items = []
        for r in rows:
            item = self._repair_scope_fields(
                {
                    "cycle_no": r["cycle_no"],
                    "parameter_name": r["parameter_name"],
                    "sub_step": r["sub_step"],
                    "component": r["component"],
                    "module": r["component"],
                    "instrument_scope": r["instrument_scope"],
                    "side_scope": r["side_scope"],
                    "side_group": r["side_group"],
                    "chip_name": r["chip_name"],
                    "chip_position": r["chip_position"],
                    "chuck_no": r["chuck_no"],
                    "slot_no": r["slot_no"],
                    "stage_key": r["stage_key"],
                    "start_epoch_ms": r["start_epoch_ms"],
                    "end_epoch_ms": r["end_epoch_ms"],
                    "duration_ms": r["duration_ms"],
                    "threshold_ms": r["threshold_ms"],
                    "is_over_threshold": r["is_over_threshold"],
                    "start_time_text": r["start_time_text"],
                    "end_time_text": r["end_time_text"],
                    "side_confidence": r["side_confidence"],
                    "side_evidence": self._llm_extra(r["side_evidence"]) or {},
                    "start_time_sec": self._epoch_to_seconds(r["start_epoch_ms"]),
                    "end_time_sec": self._epoch_to_seconds(r["end_epoch_ms"]),
                    "message": r["sub_step"],
                    "source_file": None,
                }
            )
            if not self._row_matches_scope_filters(
                item,
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            ):
                continue
            items.append(item)
        visible_total = len(items) if side_scope_values or side_group_values or chip_value_list else total
        return {"items": items, "total": visible_total, "offset": offset, "limit": limit}

    def get_cycle_summaries(
        self,
        task_id: int,
        unit: str = "ms",
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> list[dict]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        key = self._cache_key(
            task_id,
            "cycle_summaries",
            unit=unit,
            side_scopes=",".join(side_scope_values),
            side_groups=",".join(side_group_values),
            chip_names=",".join(chip_value_list),
        )
        def factory():
            output = []
            stmt = (
                select(
                    StepSummaryModel.cycle_no.label("cycle_no"),
                    StepSummaryModel.instrument_scope.label("instrument_scope"),
                    StepSummaryModel.side_scope.label("side_scope"),
                    StepSummaryModel.side_group.label("side_group"),
                    StepSummaryModel.chip_name.label("chip_name"),
                    func.max(StepSummaryModel.chip_position).label("chip_position"),
                    func.max(StepSummaryModel.chuck_no).label("chuck_no"),
                    func.max(StepSummaryModel.slot_no).label("slot_no"),
                    func.max(StepSummaryModel.stage_key).label("stage_key"),
                    func.max(StepSummaryModel.side_confidence).label("side_confidence"),
                    func.min(StepSummaryModel.start_epoch_ms).label("started_at"),
                    func.max(StepSummaryModel.end_epoch_ms).label("ended_at"),
                    func.sum(StepSummaryModel.duration_ms).label("duration_sum"),
                    func.max(func.abs(func.coalesce(StepSummaryModel.duration_ms, 0))).label("max_abs_duration"),
                )
                .where(StepSummaryModel.task_id == task_id)
                .group_by(
                    StepSummaryModel.cycle_no,
                    StepSummaryModel.instrument_scope,
                    StepSummaryModel.side_scope,
                    StepSummaryModel.side_group,
                    StepSummaryModel.chip_name,
                )
                .order_by(StepSummaryModel.cycle_no.asc(), StepSummaryModel.side_scope.asc(), StepSummaryModel.chip_name.asc())
            )
            stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), StepSummaryModel.side_scope, side_scope_values)
            stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), StepSummaryModel.side_group, side_group_values)
            stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), StepSummaryModel.chip_name, chip_value_list)
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
                    "instrument_scope": row["instrument_scope"],
                    "side_scope": row["side_scope"],
                    "side_group": row["side_group"],
                    "chip_name": row["chip_name"],
                    "chip_position": row["chip_position"],
                    "chuck_no": row["chuck_no"],
                    "slot_no": row["slot_no"],
                    "stage_key": row["stage_key"],
                    "side_confidence": row["side_confidence"],
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
        item = {
            "parameter_name": self._row_value(row, "parameter_name"),
            "parameter_display_name": self._row_value(row, "parameter_display_name"),
            "cycle": self._row_value(row, "cycle_no"),
            "slide": self._row_value(row, "slide"),
            "instrument_scope": self._row_value(row, "instrument_scope"),
            "side_scope": self._row_value(row, "side_scope"),
            "side_group": self._row_value(row, "side_group"),
            "chip_name": self._row_value(row, "chip_name"),
            "chip_position": self._row_value(row, "chip_position"),
            "chuck_no": self._row_value(row, "chuck_no"),
            "slot_no": self._row_value(row, "slot_no"),
            "stage_key": self._row_value(row, "stage_key"),
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
            "side_confidence": self._row_value(row, "side_confidence"),
            "side_evidence": self._llm_extra(self._row_value(row, "side_evidence")) or {},
            "extra": extra,
        }
        return self._repair_scope_fields(item)

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

    def _load_cycle_summary_stats(self, task_id: int) -> dict[tuple[int | None, str | None, str | None], dict[str, Any]]:
        stats: dict[tuple[int | None, str | None, str | None], dict[str, Any]] = defaultdict(
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
                StepSummaryModel.side_scope.label("side_scope"),
                StepSummaryModel.chip_name.label("chip_name"),
                func.min(StepSummaryModel.start_epoch_ms).label("min_start"),
                func.max(StepSummaryModel.end_epoch_ms).label("max_end"),
                func.sum(StepSummaryModel.duration_ms).label("duration_sum"),
                func.max(func.abs(func.coalesce(StepSummaryModel.duration_ms, 0))).label("max_abs_duration"),
            )
            .where(StepSummaryModel.task_id == task_id)
            .group_by(StepSummaryModel.cycle_no, StepSummaryModel.side_scope, StepSummaryModel.chip_name)
        )
        for row in self.db.execute(stmt).mappings():
            stats[(row["cycle_no"], row["side_scope"], row["chip_name"])] = {
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
            "side_evidence": json.dumps(result.side_evidence or {}, ensure_ascii=False, default=str),
            "extra_json": json.dumps(result.extra or {}, ensure_ascii=False, default=str),
        }

    def _rebuild_parameter_results_from_events(self, task_id: int) -> list[dict[str, Any]]:
        coordinator = StreamingAggregationCoordinator(self.db, task_id, self.settings)
        pairing_open_maps = {rule.parameter_name: defaultdict(deque) for rule in PAIRING_RULES}
        direct_duration_results: list[ParameterResult] = []
        pairing_results: list[ParameterResult] = []
        metric_state: dict[tuple[int | None, str | None, str | None, str], dict[str, Any]] = defaultdict(
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
        for (cycle_no, side_scope, chip_name, metric_name), stats in metric_state.items():
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
                    start_event_id=getattr(exemplar, "id", None),
                    end_event_id=getattr(exemplar, "id", None),
                    side_confidence=exemplar.side_confidence,
                    side_evidence=dict(exemplar.side_evidence or {}),
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

    def get_parameter_series(
        self,
        task_id: int,
        parameter_name: str,
        unit: str = "s",
        axis_mode: str = "cycle",
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        x_axis_type = "time" if str(axis_mode or "").strip().lower() == "time" else "cycle"
        rows = [
            r
            for r in self.get_parameter_results(task_id)
            if r["parameter_name"] == parameter_name
            and self._row_matches_scope_filters(
                r,
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            )
        ]
        out = []
        for r in rows:
            duration_ms = r.get("duration_ms")
            threshold = r.get("threshold")
            expected = r.get("expected")
            time_epoch_ms = self._parameter_time_epoch_ms(r)
            series_name = self._series_scope_label(r.get("side_scope"), r.get("chip_name"))
            x_axis_value = (
                self._preferred_time_text(r.get("start_time"), r.get("end_time"), self._epoch_to_seconds(time_epoch_ms))
                if x_axis_type == "time"
                else (r.get("cycle") if r.get("cycle") is not None else "NA")
            )
            out.append({
                **r,
                "duration_value": self._convert_duration(duration_ms, unit),
                "duration_unit": unit,
                "threshold_value": threshold if unit == "s" else self._convert_duration((threshold or 0) * 1000 if threshold is not None else None, unit),
                "expected_value": expected if unit == "s" else self._convert_duration((expected or 0) * 1000 if expected is not None else None, unit),
                "x_axis_type": x_axis_type,
                "x_axis_value": x_axis_value,
                "x_axis_label": str(x_axis_value),
                "x_axis_sort_value": time_epoch_ms if x_axis_type == "time" else (r.get("cycle") if r.get("cycle") is not None else -1),
                "time_epoch_ms": time_epoch_ms,
                "series_name": series_name,
            })
        return self._collapse_trend_points(out)

    def get_row_scan_metric_stage_series(
        self,
        task_id: int,
        unit: str = "ms",
        axis_mode: str = "cycle",
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        x_axis_type = "time" if str(axis_mode or "").strip().lower() == "time" else "cycle"
        rows = [
            r
            for r in self.get_parameter_results(task_id)
            if r["parameter_name"] == "row_scan_metric_avg"
            and self._row_matches_scope_filters(
                r,
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            )
        ]
        out = []
        for r in rows:
            stage = r.get("extra", {}).get("metric_stage")
            time_epoch_ms = self._parameter_time_epoch_ms(r)
            series_name = f"{self._series_scope_label(r.get('side_scope'), r.get('chip_name'))} | {stage or 'unknown'}"
            x_axis_value = (
                self._preferred_time_text(r.get("start_time"), r.get("end_time"), self._epoch_to_seconds(time_epoch_ms))
                if x_axis_type == "time"
                else (r.get("cycle") if r.get("cycle") is not None else "NA")
            )
            out.append({
                "cycle": r.get("cycle"),
                "side_scope": r.get("side_scope"),
                "side_group": r.get("side_group"),
                "metric_stage": stage,
                "chip_name": r.get("chip_name"),
                "chip_position": r.get("chip_position"),
                "chuck_no": r.get("chuck_no"),
                "slot_no": r.get("slot_no"),
                "duration_ms": r.get("duration_ms"),
                "duration_seconds": r.get("duration_seconds"),
                "duration_value": self._convert_duration(r.get("duration_ms"), unit),
                "duration_unit": unit,
                "row_count": r.get("extra", {}).get("row_count"),
                "source_file": r.get("source_file"),
                "x_axis_type": x_axis_type,
                "x_axis_value": x_axis_value,
                "x_axis_label": str(x_axis_value),
                "x_axis_sort_value": time_epoch_ms if x_axis_type == "time" else (r.get("cycle") if r.get("cycle") is not None else -1),
                "time_epoch_ms": time_epoch_ms,
                "series_name": series_name,
            })
        return self._collapse_trend_points(out)

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
            "side_scope": ev.side_scope,
            "side_group": ev.side_group,
            "chip_name": ev.chip_name,
            "chuck_no": ev.chuck_no,
            "slot_no": ev.slot_no,
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

    def get_movement_timeline(
        self,
        task_id: int,
        cycle_no: int | None = None,
        track_order: str = "default",
        track_granularity: str = "component",
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
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
            item["start"] = self._epoch_to_iso_text(start_ms)
            item["end"] = self._epoch_to_iso_text(end_ms)
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
            component_label = r["component"] or "Unknown Component"
            points.append({
                "event_id": r["id"],
                "cycle_no": r["cycle_no"],
                "component": r["component"],
                "module": r["module"],
                "sub_step": r["sub_step"],
                "track": f"{component_label} | Cycle {r['cycle_no'] or 'NA'}",
                "time": self._epoch_to_iso_text(epoch_ms),
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

    def get_movement_timeline(
        self,
        task_id: int,
        cycle_no: int | None = None,
        track_order: str = "default",
        track_granularity: str = "component",
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> dict[str, Any]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        timeline_side_scope_values = self._expand_timeline_side_scope_filters(StepSummaryModel, task_id, side_scope_values)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        granularity = self._timeline_granularity(track_granularity)
        stmt = (
            select(
                StepSummaryModel.cycle_no,
                StepSummaryModel.sub_step,
                StepSummaryModel.component,
                StepSummaryModel.instrument_scope,
                StepSummaryModel.side_scope,
                StepSummaryModel.side_group,
                StepSummaryModel.chip_name,
                StepSummaryModel.chip_position,
                StepSummaryModel.chuck_no,
                StepSummaryModel.slot_no,
                StepSummaryModel.stage_key,
                StepSummaryModel.start_epoch_ms,
                StepSummaryModel.end_epoch_ms,
                StepSummaryModel.duration_ms,
                StepSummaryModel.threshold_ms,
                StepSummaryModel.is_over_threshold,
                StepSummaryModel.start_time_text,
                StepSummaryModel.end_time_text,
                StepSummaryModel.side_confidence,
                StepSummaryModel.side_evidence,
            )
            .where(StepSummaryModel.task_id == task_id)
        )
        if cycle_no is not None:
            stmt = stmt.where(StepSummaryModel.cycle_no == cycle_no)
        stmt, _ = self._apply_side_scope_filter_with_repair_support(stmt, select(func.count()), StepSummaryModel.side_scope, timeline_side_scope_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), StepSummaryModel.side_group, side_group_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), StepSummaryModel.chip_name, chip_value_list)
        stmt = stmt.order_by(StepSummaryModel.cycle_no.asc(), StepSummaryModel.start_epoch_ms.asc(), StepSummaryModel.sub_step.asc())
        output: list[dict[str, Any]] = []
        lanes: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for row in self.db.execute(stmt).mappings():
            bounds = self._timeline_time_bounds(dict(row))
            if bounds is None:
                continue
            item = self._repair_scope_fields(dict(row))
            base_track = self._build_timeline_base_track(
                component=item["component"],
                cycle_no=item["cycle_no"],
                side_scope=item["side_scope"],
                chip_name=item["chip_name"],
                track_granularity=granularity,
            )
            lane_idx = 0
            start_ms = int(bounds["start_epoch_ms"])
            end_ms = int(bounds["end_epoch_ms"])
            existing = lanes[base_track]
            while lane_idx < len(existing) and start_ms < existing[lane_idx][1]:
                lane_idx += 1
            if lane_idx == len(existing):
                existing.append((start_ms, end_ms))
            else:
                existing[lane_idx] = (start_ms, end_ms)
            track = base_track if lane_idx == 0 else f"{base_track} | lane {lane_idx + 1}"
            item["module"] = item.get("component")
            item["message"] = item.get("sub_step") or item.get("parameter_name") or item.get("component")
            item["start_epoch_ms"] = start_ms
            item["end_epoch_ms"] = end_ms
            item["start_time_sec"] = bounds["start_time_sec"]
            item["end_time_sec"] = bounds["end_time_sec"]
            item["source_file"] = None
            item["start"] = bounds["start"]
            item["end"] = bounds["end"]
            item["base_track"] = base_track
            item["track"] = track
            item["track_granularity"] = granularity
            item["is_uncertain_side"] = self._is_uncertain_side(item.get("side_scope"), item.get("side_confidence"))
            item["side_evidence"] = self._llm_extra(item.get("side_evidence")) or {}
            item["time_bounds_inferred"] = bool(bounds["time_bounds_inferred"])
            if not self._row_matches_timeline_scope_filters(
                item,
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            ):
                continue
            output.append(item)
        if track_order == "cycle":
            output.sort(
                key=lambda item: (
                    (item.get("cycle_no") is None),
                    item.get("cycle_no") or -1,
                    item.get("side_scope") or "",
                    item.get("chip_name") or "",
                    item.get("track") or "",
                )
            )
        else:
            output.sort(
                key=lambda item: (
                    item.get("start_epoch_ms") if item.get("start_epoch_ms") is not None else float("inf"),
                    item.get("cycle_no") if item.get("cycle_no") is not None else -1,
                    item.get("track") or "",
                )
            )
        return self._group_timeline_records_by_side(output, row_key="rows", render_side_scopes=side_scope_values)

    def get_timeline_error_points(
        self,
        task_id: int,
        cycle_no: int | None = None,
        track_granularity: str = "component",
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> dict[str, Any]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        timeline_side_scope_values = self._expand_timeline_side_scope_filters(NormalizedEventModel, task_id, side_scope_values)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        granularity = self._timeline_granularity(track_granularity)
        stmt = (
            select(
                NormalizedEventModel.id,
                NormalizedEventModel.cycle_no,
                NormalizedEventModel.component,
                NormalizedEventModel.module,
                NormalizedEventModel.sub_step,
                NormalizedEventModel.instrument_scope,
                NormalizedEventModel.side_scope,
                NormalizedEventModel.side_group,
                NormalizedEventModel.chip_name,
                NormalizedEventModel.chip_position,
                NormalizedEventModel.chuck_no,
                NormalizedEventModel.slot_no,
                NormalizedEventModel.stage_key,
                NormalizedEventModel.epoch_ms,
                NormalizedEventModel.original_time_text,
                NormalizedEventModel.formatted_ms,
                NormalizedEventModel.message,
                NormalizedEventModel.normalized_signature,
                NormalizedEventModel.error_family,
                NormalizedEventModel.severity,
                NormalizedEventModel.error_code,
                NormalizedEventModel.exception_type,
                NormalizedEventModel.source_file,
                NormalizedEventModel.side_confidence,
                NormalizedEventModel.side_evidence,
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
        stmt, _ = self._apply_side_scope_filter_with_repair_support(stmt, select(func.count()), NormalizedEventModel.side_scope, timeline_side_scope_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), NormalizedEventModel.side_group, side_group_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), NormalizedEventModel.chip_name, chip_value_list)
        points: list[dict[str, Any]] = []
        for row in self.db.execute(stmt).mappings():
            epoch_ms = row["epoch_ms"]
            if epoch_ms is None:
                continue
            item = self._repair_scope_fields(
                {
                    "event_id": row["id"],
                    "cycle_no": row["cycle_no"],
                    "component": row["component"],
                    "module": row["module"],
                    "sub_step": row["sub_step"],
                    "instrument_scope": row["instrument_scope"],
                    "side_scope": row["side_scope"],
                    "side_group": row["side_group"],
                    "chip_name": row["chip_name"],
                    "chip_position": row["chip_position"],
                    "chuck_no": row["chuck_no"],
                    "slot_no": row["slot_no"],
                    "stage_key": row["stage_key"],
                    "message": row["message"],
                    "raw_text": row["message"],
                    "source_file": row["source_file"],
                    "side_confidence": row["side_confidence"],
                    "side_evidence": self._llm_extra(row["side_evidence"]) or {},
                }
            )
            base_track = self._build_timeline_base_track(
                component=item["component"],
                cycle_no=item["cycle_no"],
                side_scope=item["side_scope"],
                chip_name=item["chip_name"],
                track_granularity=granularity,
            )
            item.update(
                {
                    "track": base_track,
                    "base_track": base_track,
                    "track_granularity": granularity,
                    "time": self._preferred_time_text(row["original_time_text"], row["formatted_ms"], self._epoch_to_seconds(epoch_ms), self._epoch_to_iso_text(epoch_ms)),
                    "time_text": self._preferred_time_text(row["original_time_text"], row["formatted_ms"], self._epoch_to_seconds(epoch_ms)),
                    "epoch_ms": epoch_ms,
                    "normalized_signature": row["normalized_signature"],
                    **self._error_family_fields(row["error_family"]),
                    "severity": row["severity"],
                    "error_code": row["error_code"],
                    "exception_type": row["exception_type"],
                }
            )
            item["is_uncertain_side"] = self._is_uncertain_side(item["side_scope"], item["side_confidence"])
            if not self._is_timeline_error_relevant(item):
                continue
            if not self._row_matches_timeline_scope_filters(
                item,
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            ):
                continue
            points.append(item)
        return self._group_timeline_records_by_side(points, row_key="points", render_side_scopes=side_scope_values)

    def get_operational_metrics(
        self,
        task_id: int,
        cycle_no: int | None = None,
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> dict[str, Any]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        photo_names = {"imaging_time_real", "coarse_theta", "finealign", "row_scan"}
        temperature_names = {"temperature_rise_n", "temperature_rise_f", "temperature_drop_n", "temperature_drop_f"}
        result = {
            "photo_summary": [],
            "transfer_summary": [],
            "cpas_priming_summary": [],
            "cpas_summary": [],
            "temperature_times": [],
            "metric_stage_avg": self.get_row_scan_metric_stage_series(
                task_id,
                unit="ms",
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            ),
        }
        for row in self.get_parameter_results(task_id):
            if cycle_no is not None and row.get("cycle") != cycle_no:
                continue
            if not self._row_matches_scope_filters(
                row,
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            ):
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

    def get_substep_cycle_series(
        self,
        task_id: int,
        agg_mode: str = "mean",
        unit: str = "s",
        axis_mode: str = "cycle",
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        x_axis_type = "time" if str(axis_mode or "").strip().lower() == "time" else "cycle"
        stmt = (
            select(
                StepSummaryModel.id.label("id"),
                StepSummaryModel.cycle_no.label("cycle_no"),
                StepSummaryModel.parameter_name.label("parameter_name"),
                StepSummaryModel.sub_step.label("sub_step"),
                StepSummaryModel.instrument_scope.label("instrument_scope"),
                StepSummaryModel.side_scope.label("side_scope"),
                StepSummaryModel.side_group.label("side_group"),
                StepSummaryModel.chip_name.label("chip_name"),
                StepSummaryModel.chip_position.label("chip_position"),
                StepSummaryModel.chuck_no.label("chuck_no"),
                StepSummaryModel.slot_no.label("slot_no"),
                StepSummaryModel.start_epoch_ms.label("start_epoch_ms"),
                StepSummaryModel.end_epoch_ms.label("end_epoch_ms"),
                StepSummaryModel.start_time_text.label("start_time_text"),
                StepSummaryModel.end_time_text.label("end_time_text"),
                StepSummaryModel.duration_ms.label("duration_ms"),
                StepSummaryModel.side_confidence.label("side_confidence"),
                StepSummaryModel.side_evidence.label("side_evidence"),
            )
            .where(
                StepSummaryModel.task_id == task_id,
                StepSummaryModel.cycle_no.is_not(None),
                StepSummaryModel.duration_ms.is_not(None),
            )
            .order_by(
                StepSummaryModel.side_scope.asc(),
                StepSummaryModel.chip_name.asc(),
                StepSummaryModel.sub_step.asc(),
                StepSummaryModel.start_epoch_ms.asc(),
                StepSummaryModel.end_epoch_ms.asc(),
                StepSummaryModel.cycle_no.asc(),
                StepSummaryModel.id.asc(),
            )
        )
        stmt, _ = self._apply_side_scope_filter_with_repair_support(stmt, select(func.count()), StepSummaryModel.side_scope, side_scope_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), StepSummaryModel.side_group, side_group_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), StepSummaryModel.chip_name, chip_value_list)
        raw_rows: list[dict[str, Any]] = []
        grouped_raw_rows: dict[tuple[str | None, str | None, str], list[dict[str, Any]]] = defaultdict(list)
        for row in self.db.execute(stmt).mappings():
            repaired_row = self._repair_scope_fields(dict(row))
            item = {
                **dict(row),
                "instrument_scope": repaired_row["instrument_scope"],
                "side_scope": repaired_row["side_scope"],
                "side_group": repaired_row["side_group"],
                "chip_name": repaired_row["chip_name"],
                "chip_position": repaired_row.get("chip_position"),
                "chuck_no": repaired_row.get("chuck_no"),
                "slot_no": repaired_row.get("slot_no"),
                "side_confidence": repaired_row.get("side_confidence"),
                "side_evidence": repaired_row.get("side_evidence"),
            }
            if not self._row_matches_scope_filters(
                item,
                side_scopes=side_scope_values,
                side_groups=side_group_values,
                chip_names=chip_value_list,
            ):
                continue
            group_key = (
                item.get("side_scope"),
                item.get("chip_name"),
                str(item.get("sub_step") or "unknown"),
            )
            grouped_raw_rows[group_key].append(item)
            raw_rows.append(item)

        corrected_rows: list[dict[str, Any]] = []
        for group_rows in grouped_raw_rows.values():
            ordered_group_rows = sorted(
                group_rows,
                key=lambda item: (
                    self._substep_time_epoch_ms(item) if self._substep_time_epoch_ms(item) is not None else float("inf"),
                    self._coerce_cycle_no(item.get("cycle_no")) if self._coerce_cycle_no(item.get("cycle_no")) is not None else -1,
                    int(item.get("id") or 0),
                ),
            )
            for index, row in enumerate(ordered_group_rows):
                corrected_cycle, correction_source = self._resolve_substep_cycle_from_anchors(
                    task_id,
                    row,
                    rank_index=index,
                    rank_total=len(ordered_group_rows),
                )
                corrected_rows.append(
                    {
                        **row,
                        "resolved_cycle_no": corrected_cycle,
                        "original_cycle_no": row.get("cycle_no"),
                        "cycle_resolution_source": correction_source,
                    }
                )

        aggregated: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in corrected_rows:
            resolved_cycle = self._coerce_cycle_no(row.get("resolved_cycle_no"))
            if resolved_cycle is None:
                continue
            key = (
                resolved_cycle,
                str(row.get("sub_step") or "unknown"),
                row.get("instrument_scope"),
                row.get("side_scope"),
                row.get("side_group"),
                row.get("chip_name"),
            )
            stats = aggregated.get(key)
            duration_ms = float(row.get("duration_ms") or 0.0)
            row_time_epoch_ms = self._substep_time_epoch_ms(row)
            if stats is None:
                stats = {
                    "cycle": resolved_cycle,
                    "cycle_no": resolved_cycle,
                    "sub_step": row.get("sub_step") or "unknown",
                    "parameter_name": row.get("parameter_name"),
                    "instrument_scope": row.get("instrument_scope"),
                    "side_scope": row.get("side_scope"),
                    "side_group": row.get("side_group"),
                    "chip_name": row.get("chip_name"),
                    "chip_position": row.get("chip_position"),
                    "chuck_no": row.get("chuck_no"),
                    "slot_no": row.get("slot_no"),
                    "min_start_epoch_ms": row.get("start_epoch_ms"),
                    "max_end_epoch_ms": row.get("end_epoch_ms"),
                    "start_time_text": row.get("start_time_text"),
                    "end_time_text": row.get("end_time_text"),
                    "sample_count": 0,
                    "sum_duration_ms": 0.0,
                    "duration_values": [],
                    "time_epoch_ms": row_time_epoch_ms,
                    "cycle_resolution_sources": [],
                    "original_cycle_values": [],
                }
                aggregated[key] = stats

            stats["sample_count"] = int(stats["sample_count"]) + 1
            stats["sum_duration_ms"] = float(stats["sum_duration_ms"]) + duration_ms
            stats["duration_values"].append(duration_ms)
            stats["cycle_resolution_sources"].append(str(row.get("cycle_resolution_source") or ""))
            if row.get("original_cycle_no") is not None:
                stats["original_cycle_values"].append(int(row["original_cycle_no"]))
            if row.get("chip_position") and not stats.get("chip_position"):
                stats["chip_position"] = row.get("chip_position")
            if row.get("chuck_no") and not stats.get("chuck_no"):
                stats["chuck_no"] = row.get("chuck_no")
            if row.get("slot_no") and not stats.get("slot_no"):
                stats["slot_no"] = row.get("slot_no")
            start_epoch_ms = row.get("start_epoch_ms")
            end_epoch_ms = row.get("end_epoch_ms")
            if start_epoch_ms is not None:
                current_min = stats.get("min_start_epoch_ms")
                stats["min_start_epoch_ms"] = start_epoch_ms if current_min is None else min(int(current_min), int(start_epoch_ms))
            if end_epoch_ms is not None:
                current_max = stats.get("max_end_epoch_ms")
                stats["max_end_epoch_ms"] = end_epoch_ms if current_max is None else max(int(current_max), int(end_epoch_ms))
            if not stats.get("start_time_text"):
                stats["start_time_text"] = row.get("start_time_text")
            if row.get("end_time_text"):
                current_end_text = stats.get("end_time_text")
                if not current_end_text or (self._time_text_to_epoch_ms(row.get("end_time_text")) or 0) >= (self._time_text_to_epoch_ms(current_end_text) or 0):
                    stats["end_time_text"] = row.get("end_time_text")
            if row_time_epoch_ms is not None:
                current_time_epoch_ms = stats.get("time_epoch_ms")
                if current_time_epoch_ms is None or row_time_epoch_ms < current_time_epoch_ms:
                    stats["time_epoch_ms"] = row_time_epoch_ms

        out: list[dict[str, Any]] = []
        for stats in aggregated.values():
            duration_values = [float(value) for value in stats.pop("duration_values")]
            if not duration_values:
                continue
            duration_ms = sum(duration_values) if agg_mode == "sum" else (sum(duration_values) / len(duration_values))
            time_epoch_ms = stats.get("min_start_epoch_ms") or stats.get("max_end_epoch_ms") or stats.get("time_epoch_ms")
            x_axis_value = (
                self._preferred_time_text(
                    stats.get("start_time_text"),
                    stats.get("end_time_text"),
                    self._epoch_to_seconds(time_epoch_ms),
                )
                if x_axis_type == "time"
                else (stats["cycle_no"] if stats["cycle_no"] is not None else "NA")
            )
            out.append(
                {
                    **stats,
                    "duration_ms": round(float(duration_ms), 3),
                    "duration_value": self._convert_duration(duration_ms, unit),
                    "duration_unit": unit,
                    "x_axis_type": x_axis_type,
                    "x_axis_value": x_axis_value,
                    "x_axis_label": str(x_axis_value),
                    "x_axis_sort_value": time_epoch_ms if x_axis_type == "time" else (stats["cycle_no"] if stats["cycle_no"] is not None else -1),
                    "time_epoch_ms": time_epoch_ms,
                    "cycle_resolution_source": ",".join(sorted(set(filter(None, stats.get("cycle_resolution_sources", []))))),
                    "original_cycle_values": sorted(set(stats.get("original_cycle_values", []))),
                    "series_name": f"{self._series_scope_label(stats['side_scope'], stats['chip_name'])} | {stats['sub_step'] or 'unknown'}",
                }
            )
        return self._collapse_trend_points(out)

    def get_error_clusters(
        self,
        task_id: int,
        offset: int = 0,
        limit: int = 100,
        side_scopes: str | list[str] | None = None,
        side_groups: str | list[str] | None = None,
        chip_names: str | list[str] | None = None,
    ) -> dict[str, Any]:
        side_scope_values = self._normalize_filter_values(side_scopes)
        side_group_values = self._normalize_filter_values(side_groups)
        chip_value_list = self._normalize_filter_values(chip_names)
        stmt = (
            select(
                NormalizedEventModel.id,
                NormalizedEventModel.normalized_signature,
                NormalizedEventModel.error_family,
                NormalizedEventModel.severity,
                NormalizedEventModel.component,
                NormalizedEventModel.message,
                NormalizedEventModel.exception_type,
                NormalizedEventModel.epoch_ms,
                NormalizedEventModel.side_scope,
                NormalizedEventModel.side_group,
                NormalizedEventModel.chip_name,
            )
            .where(
                NormalizedEventModel.task_id == task_id,
                NormalizedEventModel.normalized_signature.is_not(None),
            )
            .order_by(NormalizedEventModel.normalized_signature.asc(), NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
        )
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), NormalizedEventModel.side_scope, side_scope_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), NormalizedEventModel.side_group, side_group_values)
        stmt, _ = self._apply_optional_in_filter(stmt, select(func.count()), NormalizedEventModel.chip_name, chip_value_list)
        grouped: dict[str, dict[str, Any]] = {}
        for row in self.db.execute(stmt).mappings():
            signature = str(row["normalized_signature"] or "")
            if not signature:
                continue
            item = grouped.setdefault(
                signature,
                {
                    "id": row["id"],
                    "normalized_signature": signature,
                    "error_family": row["error_family"],
                    "severity": row["severity"],
                    "component": row["component"],
                    "count": 0,
                    "representative_message": row["message"],
                    "representative_exception": row["exception_type"],
                    "first_seen_epoch_ms": row["epoch_ms"],
                    "last_seen_epoch_ms": row["epoch_ms"],
                    "side_scope_stats": defaultdict(int),
                    "chip_name_stats": defaultdict(int),
                },
            )
            item["count"] += 1
            epoch_ms = row["epoch_ms"]
            if epoch_ms is not None:
                first_seen = item["first_seen_epoch_ms"]
                last_seen = item["last_seen_epoch_ms"]
                item["first_seen_epoch_ms"] = epoch_ms if first_seen is None else min(int(first_seen), int(epoch_ms))
                item["last_seen_epoch_ms"] = epoch_ms if last_seen is None else max(int(last_seen), int(epoch_ms))
            if not item.get("representative_message") and row["message"]:
                item["representative_message"] = row["message"]
            if not item.get("representative_exception") and row["exception_type"]:
                item["representative_exception"] = row["exception_type"]
            side_key = row["side_scope"] if row["side_scope"] is not None else UNASSIGNED_SCOPE_TOKEN
            chip_key = row["chip_name"] if row["chip_name"] is not None else UNASSIGNED_SCOPE_TOKEN
            item["side_scope_stats"][side_key] += 1
            item["chip_name_stats"][chip_key] += 1

        ranked_items = sorted(grouped.values(), key=lambda item: (-int(item["count"]), str(item["normalized_signature"])))
        total = len(ranked_items)
        sliced_items = ranked_items[max(0, offset): max(0, offset) + limit]
        items: list[dict[str, Any]] = []
        for row in sliced_items:
            side_scope_stats = dict(row["side_scope_stats"])
            chip_name_stats = dict(row["chip_name_stats"])
            primary_side_scope = None
            if side_scope_stats:
                primary_side_scope = max(side_scope_stats.items(), key=lambda item: (item[1], str(item[0])))[0]
                if primary_side_scope == UNASSIGNED_SCOPE_TOKEN:
                    primary_side_scope = None
            primary_chip_name = None
            if chip_name_stats:
                primary_chip_name = max(chip_name_stats.items(), key=lambda item: (item[1], str(item[0])))[0]
                if primary_chip_name == UNASSIGNED_SCOPE_TOKEN:
                    primary_chip_name = None
            items.append(
                {
                    "id": row["id"],
                    "normalized_signature": row["normalized_signature"],
                    "display_signature": row["representative_message"] or row["normalized_signature"],
                    **self._error_family_fields(row["error_family"]),
                    "severity": row["severity"],
                    "component": row["component"],
                    "count": row["count"],
                    "representative_message": row["representative_message"],
                    "representative_exception": row["representative_exception"],
                    "first_seen_text": self._epoch_to_seconds(row["first_seen_epoch_ms"]),
                    "last_seen_text": self._epoch_to_seconds(row["last_seen_epoch_ms"]),
                    "primary_side_scope": primary_side_scope,
                    "primary_chip_name": primary_chip_name,
                    "side_scope_count": len(side_scope_stats),
                    "chip_count": len(chip_name_stats),
                    "side_scopes": sorted(None if key == UNASSIGNED_SCOPE_TOKEN else key for key in side_scope_stats.keys()),
                    "chip_names": sorted(None if key == UNASSIGNED_SCOPE_TOKEN else key for key in chip_name_stats.keys()),
                    "side_scope_stats": {
                        (None if key == UNASSIGNED_SCOPE_TOKEN else key): value
                        for key, value in side_scope_stats.items()
                    },
                    "chip_name_stats": {
                        (None if key == UNASSIGNED_SCOPE_TOKEN else key): value
                        for key, value in chip_name_stats.items()
                    },
                }
            )
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
