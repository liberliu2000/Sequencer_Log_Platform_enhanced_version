from __future__ import annotations

import re
from collections import defaultdict

from app.core.settings import get_settings
from app.schemas.common import NormalizedEvent, StepSummary
from app.utils.rules import load_yaml


def normalize_step_key(name: str | None) -> str | None:
    if not name:
        return None
    text = name.lower().strip()
    text = re.sub(r"^<+\s*|\s*>+$", "", text)
    text = re.sub(r"\b(is success|success!?|completed|start|begin|done|finished|for cycle\s*=\s*\d+)\b", "", text)
    text = re.sub(r"\bcycle\s*[=:]?\s*\d+\b", "", text)
    text = re.sub(r"\bposition\s*\d+\b", "", text)
    text = re.sub(r"\bfor\s+[a-z0-9_.-]+\.s\d+\b", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_<>.,:")


def build_group_key(event: NormalizedEvent) -> tuple[str | None, int | None, str | None]:
    return (event.component, event.cycle_no, event.chip_name)


MAX_PAIR_GAP_MS = 20 * 60 * 1000


def pair_start_end(events: list[NormalizedEvent]) -> list[StepSummary]:
    settings = get_settings()
    thresholds = load_yaml(settings.thresholds_path)
    by_group = defaultdict(list)
    for event in sorted(events, key=lambda e: (e.epoch_ms or 0, e.source_file, e.message)):
        if event.event_kind not in {"step", "action", "metric"}:
            continue
        key = build_group_key(event)
        by_group[key].append(event)

    summaries: list[StepSummary] = []
    for (component, cycle_no, chip_name), group in by_group.items():
        active: dict[str, list[NormalizedEvent]] = defaultdict(list)
        for event in group:
            step_key = normalize_step_key(event.sub_step or event.message)
            if not step_key:
                continue

            if event.direction == "start":
                active[step_key].append(event)
                continue

            if event.direction == "end":
                start_event = None
                candidates = active.get(step_key, [])
                if candidates:
                    # 优先最近的未闭合开始事件，避免相同动作串扰
                    for idx in range(len(candidates) - 1, -1, -1):
                        candidate = candidates[idx]
                        if _is_pairable(candidate, event):
                            start_event = candidates.pop(idx)
                            break
                if start_event:
                    duration_ms = _derive_duration_ms(start_event, event)
                    threshold_ms = get_step_threshold_ms(thresholds, component, step_key)
                    summaries.append(
                        StepSummary(
                            cycle_no=cycle_no,
                            sub_step=step_key,
                            component=component,
                            chip_name=chip_name or event.chip_name or start_event.chip_name,
                            start_epoch_ms=start_event.epoch_ms,
                            end_epoch_ms=event.epoch_ms,
                            duration_ms=duration_ms,
                            threshold_ms=threshold_ms,
                            is_over_threshold=bool(duration_ms and threshold_ms and duration_ms > threshold_ms),
                            start_time_text=start_event.formatted_ms,
                            end_time_text=event.formatted_ms,
                        )
                    )
                elif event.duration_ms is not None and event.epoch_ms is not None:
                    # 只有 completed/span time，没有明确 start 时，用反推方式生成摘要
                    start_epoch_ms = int(event.epoch_ms - event.duration_ms)
                    threshold_ms = get_step_threshold_ms(thresholds, component, step_key)
                    summaries.append(
                        StepSummary(
                            cycle_no=cycle_no,
                            sub_step=step_key,
                            component=component,
                            chip_name=chip_name or event.chip_name,
                            start_epoch_ms=start_epoch_ms,
                            end_epoch_ms=event.epoch_ms,
                            duration_ms=event.duration_ms,
                            threshold_ms=threshold_ms,
                            is_over_threshold=bool(event.duration_ms and threshold_ms and event.duration_ms > threshold_ms),
                            start_time_text=None,
                            end_time_text=event.formatted_ms,
                        )
                    )
                continue

            if event.duration_ms is not None:
                threshold_ms = get_step_threshold_ms(thresholds, component, step_key)
                summaries.append(
                    StepSummary(
                        cycle_no=cycle_no,
                        sub_step=step_key,
                        component=component,
                        chip_name=chip_name or event.chip_name,
                        start_epoch_ms=None,
                        end_epoch_ms=event.epoch_ms,
                        duration_ms=event.duration_ms,
                        threshold_ms=threshold_ms,
                        is_over_threshold=bool(event.duration_ms and threshold_ms and event.duration_ms > threshold_ms),
                        start_time_text=None,
                        end_time_text=event.formatted_ms,
                    )
                )

        for step_key, start_events in active.items():
            for start_event in start_events:
                threshold_ms = get_step_threshold_ms(thresholds, component, step_key)
                summaries.append(
                    StepSummary(
                        cycle_no=cycle_no,
                        sub_step=step_key,
                        component=component,
                        chip_name=chip_name or start_event.chip_name,
                        start_epoch_ms=start_event.epoch_ms,
                        end_epoch_ms=None,
                        duration_ms=None,
                        threshold_ms=threshold_ms,
                        is_over_threshold=False,
                        start_time_text=start_event.formatted_ms,
                        end_time_text=None,
                    )
                )
    return summaries


def _derive_duration_ms(start_event: NormalizedEvent, end_event: NormalizedEvent) -> float | None:
    if start_event.epoch_ms is not None and end_event.epoch_ms is not None:
        return float(end_event.epoch_ms - start_event.epoch_ms)
    return end_event.duration_ms


def _is_pairable(start_event: NormalizedEvent, end_event: NormalizedEvent) -> bool:
    if start_event.component != end_event.component:
        return False
    if start_event.cycle_no is not None and end_event.cycle_no is not None and start_event.cycle_no != end_event.cycle_no:
        return False
    if start_event.chip_name and end_event.chip_name and start_event.chip_name != end_event.chip_name:
        return False
    if start_event.epoch_ms is not None and end_event.epoch_ms is not None:
        return 0 <= (end_event.epoch_ms - start_event.epoch_ms) <= MAX_PAIR_GAP_MS
    return True


def get_step_threshold_ms(thresholds: dict, component: str | None, step_key: str) -> float | None:
    rules = thresholds.get("step_thresholds_ms", {})
    if component and component in rules:
        component_rules = rules[component]
        if step_key in component_rules:
            return float(component_rules[step_key])
    default_rules = rules.get("default", {})
    if step_key in default_rules:
        return float(default_rules[step_key])
    return thresholds.get("default_threshold_ms")
