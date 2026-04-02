from __future__ import annotations

from collections import defaultdict, deque

from app.schemas.common import CycleSummary, NormalizedEvent, ParameterResult, StepSummary
from app.services.parameter_definitions import DIRECT_DURATION_RULES, PAIRING_RULES, ROW_SCAN_METRIC_STAGES, parameter_definition_map

PARAM_MAP = parameter_definition_map()


def summarize_cycles(step_summaries: list[StepSummary]) -> list[CycleSummary]:
    grouped: dict[tuple[int | None, str | None], dict[str, float | int | None | bool]] = defaultdict(
        lambda: {
            "min_start": None,
            "max_end": None,
            "duration_sum": 0.0,
            "has_nonzero_duration": False,
        }
    )
    for item in step_summaries:
        stats = grouped[(item.cycle_no, item.chip_name)]
        if item.start_epoch_ms is not None:
            current_min = stats["min_start"]
            stats["min_start"] = item.start_epoch_ms if current_min is None else min(int(current_min), item.start_epoch_ms)
        if item.end_epoch_ms is not None:
            current_max = stats["max_end"]
            stats["max_end"] = item.end_epoch_ms if current_max is None else max(int(current_max), item.end_epoch_ms)
        if item.duration_ms:
            stats["has_nonzero_duration"] = True
            stats["duration_sum"] = float(stats["duration_sum"]) + float(item.duration_ms)

    out: list[CycleSummary] = []
    for (cycle_no, chip_name), stats in grouped.items():
        min_start = stats["min_start"]
        max_end = stats["max_end"]
        total_ms = None
        if min_start is not None and max_end is not None:
            total_ms = float(int(max_end) - int(min_start))
        elif bool(stats["has_nonzero_duration"]):
            total_ms = float(stats["duration_sum"])
        out.append(
            CycleSummary(
                cycle_no=cycle_no,
                chip_name=chip_name,
                total_duration_ms=total_ms,
                started_at=int(min_start) if min_start is not None else None,
                ended_at=int(max_end) if max_end is not None else None,
            )
        )
    return sorted(out, key=lambda x: (x.cycle_no if x.cycle_no is not None else -1, x.chip_name or ""))


def build_unified_parameter_results(events: list[NormalizedEvent], existing_steps: list[StepSummary]) -> list[ParameterResult]:
    results: list[ParameterResult] = []
    events_sorted = sorted(events, key=lambda x: (x.epoch_ms or 0, x.source_file, x.message))
    results.extend(_build_cycle_time_results(existing_steps, events_sorted))
    results.extend(_build_direct_duration_results(events_sorted))
    results.extend(_build_pairing_results(events_sorted))
    results.extend(_build_row_scan_metric_results(events_sorted))
    results.sort(key=lambda x: (x.cycle if x.cycle is not None else -1, x.parameter_name, x.slide or "", x.start_time or ""))
    return results


def aggregate_metric_steps(events: list[NormalizedEvent]) -> list[StepSummary]:
    """
    兼容旧 ingestion_service 调用。
    从 metrics 事件聚合出可落库的 StepSummary 列表。
    仅处理 imaging::* 类 metrics 行扫阶段。
    """
    out: list[StepSummary] = []
    for pr in _build_row_scan_metric_results(sorted(events, key=lambda x: (x.epoch_ms or 0, x.source_file, x.message))):
        threshold_ms = (pr.threshold * 1000.0) if pr.threshold is not None else None
        out.append(
            StepSummary(
                cycle_no=pr.cycle,
                parameter_name=pr.parameter_name,
                sub_step=pr.extra.get("metric_stage") or pr.parameter_display_name,
                component=pr.component,
                chip_name=pr.chip_name,
                start_epoch_ms=None,
                end_epoch_ms=None,
                duration_ms=pr.duration_ms,
                threshold_ms=threshold_ms,
                is_over_threshold=pr.is_exceed,
                start_time_text=pr.start_time,
                end_time_text=pr.end_time,
            )
        )
    return out


def build_parameter_summaries(events: list[NormalizedEvent], existing_steps: list[StepSummary]) -> list[StepSummary]:
    """
    兼容旧 ingestion_service 调用。
    将统一参数结果转换成可落库的 StepSummary，供 query_service / dashboard / export 继续使用。
    这里排除 row_scan_metric_avg，避免与 aggregate_metric_steps 重复。
    """
    out: list[StepSummary] = []
    for pr in build_unified_parameter_results(events, existing_steps):
        if pr.parameter_name == "row_scan_metric_avg":
            continue
        threshold_ms = (pr.threshold * 1000.0) if pr.threshold is not None else None
        out.append(
            StepSummary(
                cycle_no=pr.cycle,
                parameter_name=pr.parameter_name,
                sub_step=pr.parameter_display_name,
                component=pr.component,
                chip_name=pr.chip_name,
                start_epoch_ms=None,
                end_epoch_ms=None,
                duration_ms=pr.duration_ms,
                threshold_ms=threshold_ms,
                is_over_threshold=pr.is_exceed,
                start_time_text=pr.start_time,
                end_time_text=pr.end_time,
            )
        )
    return out


def _safe_seconds(ms: float | None) -> float | None:
    return None if ms is None else round(float(ms) / 1000.0, 6)


def _event_time_text(ev: NormalizedEvent | None) -> str | None:
    if not ev:
        return None
    if ev.parsed_datetime:
        try:
            return ev.parsed_datetime.isoformat(timespec="seconds")
        except TypeError:
            return ev.parsed_datetime.isoformat()
    return ev.formatted_ms or ev.original_time_text


def _definition_values(parameter_name: str) -> tuple[float | None, float | None]:
    d = PARAM_MAP.get(parameter_name)
    return (None, None) if not d else (d.threshold_seconds, d.expected_seconds)


def _mk_result(parameter_name: str, display_name: str, cycle: int | None, slide: str | None, chip_name: str | None, start_event: NormalizedEvent | None, end_event: NormalizedEvent | None, duration_ms: float | None, source_file: str | None, source_type: str, component: str | None = None, extra: dict | None = None) -> ParameterResult:
    threshold, expected = _definition_values(parameter_name)
    duration_seconds = _safe_seconds(duration_ms)
    is_exceed = bool(duration_seconds is not None and threshold is not None and duration_seconds > threshold)
    return ParameterResult(
        parameter_name=parameter_name,
        parameter_display_name=display_name,
        cycle=cycle,
        slide=slide,
        chip_name=chip_name,
        duration_seconds=duration_seconds,
        duration_ms=duration_ms,
        start_time=_event_time_text(start_event),
        end_time=_event_time_text(end_event),
        start_message=start_event.message if start_event else None,
        end_message=end_event.message if end_event else None,
        source_file=source_file or (end_event.source_file if end_event else (start_event.source_file if start_event else None)),
        source_type=source_type,
        threshold=threshold,
        expected=expected,
        is_exceed=is_exceed,
        component=component or (end_event.component if end_event else (start_event.component if start_event else None)),
        start_event_id=getattr(start_event, "id", None),
        end_event_id=getattr(end_event, "id", None),
        extra=extra or {},
    )


def _build_cycle_time_results(existing_steps: list[StepSummary], events: list[NormalizedEvent]) -> list[ParameterResult]:
    out: list[ParameterResult] = []
    anchors = [ev for ev in events if ev.epoch_ms is not None and "current imaging cycle" in (ev.message or "").lower()]
    anchors = sorted(anchors, key=lambda x: x.epoch_ms or 0)
    if len(anchors) >= 2:
        for i in range(len(anchors) - 1):
            cur_ev = anchors[i]
            next_ev = anchors[i + 1]
            if cur_ev.epoch_ms is None or next_ev.epoch_ms is None:
                continue
            out.append(_mk_result("cycle_time", "cycle time", cur_ev.cycle_no, None, cur_ev.chip_name or next_ev.chip_name, cur_ev, next_ev, float(next_ev.epoch_ms - cur_ev.epoch_ms), cur_ev.source_file, "derived", component="Workflow", extra={"method": "current_imaging_cycle_anchor"}))
        return out

    for c in summarize_cycles(existing_steps):
        threshold, expected = _definition_values("cycle_time")
        duration_s = _safe_seconds(c.total_duration_ms)
        out.append(ParameterResult(parameter_name="cycle_time", parameter_display_name="cycle time", cycle=c.cycle_no, slide=None, chip_name=c.chip_name, duration_seconds=duration_s, duration_ms=c.total_duration_ms, start_time=None, end_time=None, start_message=None, end_message=None, source_file=None, source_type="derived", threshold=threshold, expected=expected, is_exceed=bool(duration_s is not None and threshold is not None and duration_s > threshold), component="Workflow", extra={"started_at_epoch_ms": c.started_at, "ended_at_epoch_ms": c.ended_at, "method": "step_summary_fallback"}))
    return out


def _build_direct_duration_results(events: list[NormalizedEvent]) -> list[ParameterResult]:
    out: list[ParameterResult] = []
    for ev in events:
        if ev.duration_ms is None:
            continue
        msg = f"{ev.message or ''} {ev.sub_step or ''}".lower()
        for rule in DIRECT_DURATION_RULES:
            if any(tok in msg for tok in rule["matchers"]):
                out.append(_mk_result(rule["parameter_name"], rule["display_name"], ev.cycle_no, _extract_slide_name(ev.message), ev.chip_name, None, ev, float(ev.duration_ms), ev.source_file, "log", component=ev.component))
                break
    return out


def _build_pairing_results(events: list[NormalizedEvent]) -> list[ParameterResult]:
    out: list[ParameterResult] = []
    for rule in PAIRING_RULES:
        open_map: dict[tuple, deque[NormalizedEvent]] = defaultdict(deque)
        for ev in events:
            msg = ev.message or ""
            sm = rule.start_pattern.search(msg)
            if sm:
                if rule.is_temperature_rule():
                    target = _extract_float_from_groups(sm.groups())
                    if target is None or not _within_temperature(target, rule.target_temp, rule.target_temp_tolerance):
                        continue
                cycle = _extract_cycle_from_match(sm.groups()) if rule.cycle_from_match else ev.cycle_no
                slide = _extract_slide_from_match(sm.groups()) if rule.slide_from_match else _extract_slide_name(msg)
                open_map[_pairing_key(rule.parameter_name, cycle, slide, ev.chip_name)].append(ev)
                continue
            em = rule.end_pattern.search(msg)
            if not em:
                continue
            if rule.is_temperature_rule():
                target = _extract_float_from_groups(em.groups())
                if target is None or not _within_temperature(target, rule.target_temp, rule.target_temp_tolerance):
                    continue
            cycle = _extract_cycle_from_match(em.groups()) if rule.cycle_from_match else ev.cycle_no
            slide = _extract_slide_from_match(em.groups()) if rule.slide_from_match else _extract_slide_name(msg)
            key = _pairing_key(rule.parameter_name, cycle, slide, ev.chip_name)
            starts = open_map.get(key) or open_map.get(_pairing_key(rule.parameter_name, cycle, slide, None))
            if not starts:
                continue
            start_event = starts.popleft()
            if start_event.epoch_ms is None or ev.epoch_ms is None:
                continue
            out.append(_mk_result(rule.parameter_name, rule.display_name, cycle, slide, ev.chip_name or start_event.chip_name, start_event, ev, float(ev.epoch_ms - start_event.epoch_ms), ev.source_file, rule.source_type, component=ev.component or start_event.component, extra={"rule_notes": rule.notes}))
    return out


def _build_row_scan_metric_results(events: list[NormalizedEvent]) -> list[ParameterResult]:
    grouped: dict[tuple[int | None, str | None, str], dict[str, object]] = defaultdict(
        lambda: {"sum_duration_ms": 0.0, "row_count": 0, "exemplar": None, "raw_duration_ms_list": []}
    )
    for ev in events:
        if ev.parser_name != "metrics_csv":
            continue
        if not ev.sub_step or not str(ev.sub_step).startswith("imaging::"):
            continue
        metric_name = str(ev.sub_step).split("::", 1)[-1]
        norm_name = "scanTotalTime" if metric_name == "ScanTotalTime" else metric_name
        if norm_name not in ROW_SCAN_METRIC_STAGES:
            continue
        if ev.duration_ms is None:
            continue
        stats = grouped[(ev.cycle_no, ev.chip_name, norm_name)]
        stats["sum_duration_ms"] = float(stats["sum_duration_ms"]) + float(ev.duration_ms)
        stats["row_count"] = int(stats["row_count"]) + 1
        if stats["exemplar"] is None:
            stats["exemplar"] = ev
        raw_duration_ms_list = stats["raw_duration_ms_list"]
        if isinstance(raw_duration_ms_list, list) and len(raw_duration_ms_list) < 20:
            raw_duration_ms_list.append(float(ev.duration_ms))

    out: list[ParameterResult] = []
    threshold, expected = _definition_values("row_scan_metric_avg")
    for (cycle_no, chip_name, metric_name), stats in grouped.items():
        row_count = int(stats["row_count"])
        if row_count <= 0:
            continue
        avg_ms = float(stats["sum_duration_ms"]) / row_count
        exemplar = stats["exemplar"]
        if exemplar is None:
            continue
        out.append(
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
                extra={
                    "metric_stage": metric_name,
                    "row_count": row_count,
                    "raw_duration_ms_list": list(stats["raw_duration_ms_list"]),
                },
            )
        )
    return out


def _extract_cycle_from_match(groups: tuple[str, ...]) -> int | None:
    for g in groups:
        if g is None:
            continue
        if str(g).isdigit():
            return int(g)
    return None


def _extract_slide_from_match(groups: tuple[str, ...]) -> str | None:
    for g in groups:
        if g and len(str(g)) <= 8 and any(ch.isalpha() for ch in str(g)):
            return str(g)
    return None


def _extract_float_from_groups(groups: tuple[str, ...]) -> float | None:
    for g in groups:
        if g is None:
            continue
        try:
            return float(str(g))
        except Exception:
            continue
    return None


def _within_temperature(value: float, target: float | None, tolerance: float) -> bool:
    return True if target is None else abs(float(value) - float(target)) <= tolerance


def _extract_slide_name(message: str | None) -> str | None:
    if not message:
        return None
    tokens = message.replace('.', ' ').split()
    for tok in tokens:
        if len(tok) <= 8 and tok[:1].isalpha() and any(ch.isdigit() for ch in tok):
            return tok
    return None


def _pairing_key(parameter_name: str, cycle: int | None, slide: str | None, chip_name: str | None) -> tuple:
    return parameter_name, cycle, (slide or '').upper(), chip_name or ''
