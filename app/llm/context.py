from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ContextConfig:
    pre_lines: int = 8
    post_lines: int = 8
    time_window_seconds: int = 90
    related_component_limit: int = 30
    related_cycle_limit: int = 30
    max_stack_frames: int = 8
    max_token_budget: int = 2200
    stage1_token_budget: int = 1200


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 3.5))


def _normalize_line(item: dict[str, Any]) -> str:
    text = f"{item.get('level','')}|{item.get('component','')}|{item.get('method_name','')}|{item.get('exception_type','')}|{item.get('message','')}"
    text = re.sub(r"\b\d+\b", "#", text)
    text = re.sub(r"0x[a-fA-F0-9]+", "0x#", text)
    text = re.sub(r"[A-Z]:\\[^ ]+", "PATH", text)
    return text


def _compress_stack(message: str, max_frames: int) -> str:
    lines = [l.rstrip() for l in str(message).splitlines() if l.strip()]
    if len(lines) <= max_frames + 1:
        return "\n".join(lines)
    hidden = max(0, len(lines) - (max_frames + 1))
    return "\n".join(lines[:1] + lines[1:max_frames + 1] + [f"... <omitted {hidden} stack lines>"])


def _truncate_text(text: str, max_chars: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_chars:
        return text
    keep_head = max_chars // 2
    keep_tail = max_chars - keep_head - 16
    return f"{text[:keep_head]} ... <trimmed> ... {text[-keep_tail:]}"


def _row_priority(row: dict[str, Any]) -> tuple[int, int]:
    level = str(row.get("level", "")).upper()
    msg = str(row.get("message", "")).lower()
    score = 0
    if row.get("normalized_signature"):
        score += 120
    if level in {"FATAL", "ERROR"}:
        score += 80
    elif level == "WARN":
        score += 50
    elif level == "INFO":
        score += 10
    if row.get("exception_type"):
        score += 45
    if row.get("sub_step"):
        score += 20
    if row.get("cycle_no") is not None:
        score += 10
    for keyword, bonus in {
        "timeout": 40,
        "exception": 35,
        "failed": 30,
        "error": 30,
        "abort": 25,
        "retry": 18,
        "disconnect": 18,
        "stall": 18,
        "warning": 10,
        "start": 6,
        "complete": 4,
        "completed": 4,
    }.items():
        if keyword in msg:
            score += bonus
    epoch_ms = row.get("epoch_ms")
    epoch_sort = -int(epoch_ms) if isinstance(epoch_ms, (int, float)) else 0
    return score, epoch_sort


def _compact_row(row: dict[str, Any], *, include_message: bool = True) -> dict[str, Any]:
    compact = {
        "time": row.get("time"),
        "level": row.get("level"),
        "component": row.get("component"),
        "cycle_no": row.get("cycle_no"),
        "sub_step": row.get("sub_step"),
        "exception_type": row.get("exception_type"),
        "source_file": row.get("source_file"),
    }
    msg = str(row.get("message") or "")
    if include_message:
        compact["message"] = _truncate_text(msg, max_chars=220)
    compact = {k: v for k, v in compact.items() if v not in (None, "", [], {})}
    return compact


def compress_records(raw_rows: list[dict[str, Any]], cfg: ContextConfig, token_budget: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen = set()
    removed_duplicate_count = 0
    removed_info_complete_count = 0
    for source_row in raw_rows:
        row = dict(source_row)
        row["message"] = _compress_stack(str(row.get("message") or ""), cfg.max_stack_frames)
        key = _normalize_line(row)
        if key in seen:
            removed_duplicate_count += 1
            continue
        if str(row.get("level", "")).upper() == "INFO" and not row.get("sub_step") and "completed" in str(row.get("message", "")).lower():
            removed_info_complete_count += 1
            continue
        seen.add(key)
        deduped.append(row)

    priority_sorted = sorted(deduped, key=_row_priority, reverse=True)
    selected = [_compact_row(row) for row in priority_sorted]
    trim_rounds = 0
    trim_strategy = []

    def _tokens(rows: list[dict[str, Any]]) -> int:
        return estimate_tokens("\n".join(str(r) for r in rows))

    while selected and _tokens(selected) > token_budget:
        trim_rounds += 1
        current_tokens = _tokens(selected)
        next_rows: list[dict[str, Any]] = []
        for r in selected:
            level = str(r.get("level", "")).upper()
            msg = str(r.get("message", "")).lower()
            keep = (
                level in {"ERROR", "FATAL", "WARN"}
                or bool(r.get("exception_type"))
                or bool(r.get("sub_step"))
                or any(k in msg for k in ["timeout", "exception", "failed", "error", "abort", "retry"])
            )
            if keep:
                next_rows.append(r)
        if next_rows and len(next_rows) < len(selected):
            trim_strategy.append(f"filter_noncritical:{len(selected)}->{len(next_rows)}")
            selected = next_rows
            continue
        if len(selected) > 12:
            reduced = selected[: max(12, int(len(selected) * 0.75))]
            trim_strategy.append(f"top_priority_slice:{len(selected)}->{len(reduced)}")
            selected = reduced
            continue
        if current_tokens > token_budget:
            for r in selected:
                if "message" in r:
                    r["message"] = _truncate_text(str(r.get("message") or ""), max_chars=120)
            trim_strategy.append("truncate_message_120")
            if _tokens(selected) <= token_budget:
                break
            for r in selected:
                if "message" in r:
                    r["message"] = _truncate_text(str(r.get("message") or ""), max_chars=80)
            trim_strategy.append("truncate_message_80")
            if _tokens(selected) <= token_budget:
                break
            for r in selected:
                if "message" in r and len(str(r.get("message") or "")) > 48:
                    r["message"] = _truncate_text(str(r.get("message") or ""), max_chars=48)
            trim_strategy.append("truncate_message_48")
            if _tokens(selected) <= token_budget:
                break
            selected = selected[: max(5, len(selected) - 1)]
            trim_strategy.append(f"hard_drop_tail:{len(selected)+1}->{len(selected)}")

    raw_text = "\n".join(str(r) for r in raw_rows)
    deduped_text = "\n".join(str(r) for r in deduped)
    compressed_text = "\n".join(str(r) for r in selected)
    raw_tokens = estimate_tokens(raw_text)
    deduped_tokens = estimate_tokens(deduped_text) if deduped else 0
    compressed_tokens = estimate_tokens(compressed_text) if selected else 0
    stats = {
        "raw_line_count": len(raw_rows),
        "deduped_line_count": len(deduped),
        "compressed_line_count": len(selected),
        "raw_estimated_tokens": raw_tokens,
        "deduped_estimated_tokens": deduped_tokens,
        "compressed_estimated_tokens": compressed_tokens,
        "compression_ratio": round(len(selected) / max(1, len(raw_rows)), 4),
        "token_compression_ratio": round(compressed_tokens / max(1, raw_tokens), 4),
        "line_reduction_percent": round((1 - len(selected) / max(1, len(raw_rows))) * 100, 2),
        "token_reduction_percent": round((1 - compressed_tokens / max(1, raw_tokens)) * 100, 2),
        "dedup_reduction_percent": round((1 - len(deduped) / max(1, len(raw_rows))) * 100, 2),
        "token_budget": token_budget,
        "within_budget": compressed_tokens <= token_budget,
        "removed_duplicate_count": removed_duplicate_count,
        "removed_info_complete_count": removed_info_complete_count,
        "trim_rounds": trim_rounds,
        "trim_strategy": trim_strategy,
        "selection_strategy": "priority_score + dedupe + critical_only + message_truncation",
    }
    return selected, stats
