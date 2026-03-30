from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from typing import Iterable

from app.schemas.common import NormalizedEvent

CURRENT_CYCLE_HINTS = [
    "imaging at cycle",
    "imaging complete for cycle",
    "row scan done",
    "coarsethetawithoutmovestage",
    "finealign",
    "cpas completed for cycle",
    "mda",
    "bc",
]
NEXT_CYCLE_HINTS = [
    "before cycle",
    "start for cycle",
    "reagent priming start before cycle",
    "reagent priming completed before cycle",
    "move slide from imager to chuck stage",
]


def _mark(event: NormalizedEvent, inferred: bool, method: str, confidence: str, reason: str | None = None, cycle_no: int | None = None):
    extra = dict(event.extra_json or {})
    extra["cycle_inferred"] = inferred
    extra["cycle_infer_method"] = method
    extra["cycle_infer_confidence"] = confidence
    if reason:
        extra["cycle_infer_reason"] = reason
    if cycle_no is not None:
        event.cycle_no = cycle_no
    event.extra_json = extra
    return event


def infer_missing_cycles(events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    ordered = sorted(events, key=lambda e: (e.epoch_ms or 0, e.source_file, e.message))
    anchors = [(idx, e.cycle_no) for idx, e in enumerate(ordered) if e.cycle_no is not None]
    if not anchors:
        for e in ordered:
            if e.cycle_no is None:
                _mark(e, False, "insufficient_context", "low", "insufficient_context")
        return ordered

    anchor_positions = [a[0] for a in anchors]
    component_cycle_votes: dict[tuple[str | None, str | None], Counter] = defaultdict(Counter)
    for e in ordered:
        if e.cycle_no is not None:
            component_cycle_votes[(e.component, e.sub_step)][e.cycle_no] += 1

    for idx, event in enumerate(ordered):
        if event.cycle_no is not None:
            _mark(event, False, "existing", "high")
            continue

        msg = (event.message or "").lower()
        pos = bisect_left(anchor_positions, idx)
        prev_anchor = anchors[pos - 1] if pos > 0 else None
        next_anchor = anchors[pos] if pos < len(anchors) else None

        # 1) component/step majority vote
        votes = component_cycle_votes.get((event.component, event.sub_step)) or component_cycle_votes.get((event.component, None))
        if votes:
            winner, count = votes.most_common(1)[0]
            total = sum(votes.values())
            if total >= 2 and count / total >= 0.7:
                _mark(event, True, "component_cluster", "high", cycle_no=winner)
                continue

        # 2) interval + semantics
        if prev_anchor and next_anchor:
            prev_cycle = prev_anchor[1]
            next_cycle = next_anchor[1]
            if prev_cycle == next_cycle:
                _mark(event, True, "time_interval_same_cycle", "high", cycle_no=prev_cycle)
                continue
            if any(k in msg for k in NEXT_CYCLE_HINTS):
                _mark(event, True, "time_interval_next_cycle", "medium", cycle_no=next_cycle)
                continue
            if any(k in msg for k in CURRENT_CYCLE_HINTS):
                _mark(event, True, "time_interval_current_cycle", "medium", cycle_no=prev_cycle)
                continue
            # nearer anchor fallback
            if event.epoch_ms is not None:
                prev_time = ordered[prev_anchor[0]].epoch_ms or event.epoch_ms
                next_time = ordered[next_anchor[0]].epoch_ms or event.epoch_ms
                if abs(event.epoch_ms - prev_time) <= abs(next_time - event.epoch_ms):
                    _mark(event, True, "time_nearest_anchor", "low", cycle_no=prev_cycle)
                else:
                    _mark(event, True, "time_nearest_anchor", "low", cycle_no=next_cycle)
                continue

        # 3) inherit previous or next single anchor conservatively
        if prev_anchor and any(k in msg for k in CURRENT_CYCLE_HINTS):
            _mark(event, True, "previous_anchor", "medium", cycle_no=prev_anchor[1])
            continue
        if next_anchor and any(k in msg for k in NEXT_CYCLE_HINTS):
            _mark(event, True, "next_anchor", "medium", cycle_no=next_anchor[1])
            continue

        _mark(event, False, "insufficient_context", "low", "insufficient_context")

    return ordered
