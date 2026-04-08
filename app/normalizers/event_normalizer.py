from __future__ import annotations

import re
from typing import Any

from app.core.settings import get_settings
from app.schemas.common import NormalizedEvent, RawLogRecord, build_normalized_event
from app.utils.side_inference import infer_scope_from_texts
from app.utils.text import (
    extract_operation_name,
    infer_chip_name,
    infer_cycle_from_text,
    infer_stage_name,
    safe_component_name,
)
from app.utils.timeparse import format_ms, parse_datetime, to_epoch_ms

STEP_DURATION_RE = re.compile(r"span time[:=]\s*([0-9.]+)\s*s", re.IGNORECASE)
COMPLETED_IN_RE = re.compile(r"\bcompleted\s+in\s+([0-9.]+)\s*sec", re.IGNORECASE)
ERROR_CODE_RE = re.compile(r"\b(?:error\s*code|code)[:= ]+([A-Za-z0-9_.-]+)", re.IGNORECASE)
EXCEPTION_TYPE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_.]*(?:Exception|Error))\b")
ERROR_CODE_FIELD_RE = re.compile(r"\berror\s*code\s*[:= ]*[a-z0-9_.-]*", re.IGNORECASE)

START_PATTERNS = [
    r"\bstart\b",
    r"\bbegin\b",
    r"\brequest\b",
    r"\bsetup\b",
    r"\bwf start\b",
    r"\brunning position\b",
    r"\bstatus\s*:\s*running\b",
]
END_PATTERNS = [
    r"\bcompleted\b",
    r"\bend\b",
    r"\bsuccess\b",
    r"\bdone\b",
    r"\bfinished\b",
    r"\bstatus\s*:\s*(?:stopped|completed|idle|failed|error|success)\b",
    r"\bhas\s+hold\s+imager\b",
]
SUCCESS_RE = re.compile(r"\bis success\b|\bsuccess!\b", re.IGNORECASE)
START_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in START_PATTERNS]
END_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in END_PATTERNS]
EXPLICIT_SUBSTEP_REGEXES = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"<+\s*(.*?)\s*completed",
        r"<+\s*(.*?)\s*start",
        r"Imaging Completed for\s+([A-Za-z0-9_.-]+)",
        r"Imaging start(?:\s+for)?\s*(?:cycle\s*=\s*\d+)?",
        r"Start\s+(.*?)$",
        r"begin\s+(.*?)$",
    ]
]
IMAGING_COMPLETED_RE = re.compile(r"Imaging Completed for", re.IGNORECASE)
IMAGING_START_RE = re.compile(r"Imaging start", re.IGNORECASE)


def infer_sub_step(record: RawLogRecord) -> str | None:
    msg = (record.message or "").strip()
    method_name = record.method_name
    for pattern in EXPLICIT_SUBSTEP_REGEXES:
        m = pattern.search(msg)
        if m:
            found = m.group(1) if m.lastindex else m.group(0)
            if IMAGING_COMPLETED_RE.search(msg):
                return "Imaging"
            if IMAGING_START_RE.search(msg):
                return "Imaging"
            return re.sub(r"\s+", " ", found).strip(" <>._-")

    op = extract_operation_name(msg, method_name=method_name)
    if op:
        return op
    if len(msg) < 120:
        return msg
    return None


def infer_event_kind(record: RawLogRecord) -> tuple[str | None, str | None]:
    lower = (record.message or "").lower()
    lower_for_error = ERROR_CODE_FIELD_RE.sub("", lower)
    level = (record.level or "INFO").upper()

    if record.parser_name == "metrics_csv":
        return "metric", None

    if "span time" in lower or "completed in" in lower or SUCCESS_RE.search(lower):
        return "step", "end"
    for pattern in END_REGEXES:
        if pattern.search(lower):
            return "step", "end"
    for pattern in START_REGEXES:
        if pattern.search(lower):
            return "step", "start"
    if any(k in lower_for_error for k in ["exception", "error", "timeout", "failed"]) or level in {"ERROR", "FATAL"}:
        return "error", None
    if any(k in lower for k in ["move", "fill", "switch", "aspirate", "dispense", "transfer", "scan"]):
        return "action", None
    return "log", None


IMAGING_METRIC_KEYS = {
    "setup",
    "move2start",
    "setTDIdir",
    "caculateImageType",
    "setupPEG",
    "waitForBCSRearyTime",
    "completeAcq",
    "sendrowInfo",
    "endmove2start",
    "waitForAFTime",
    "enablePEG",
    "turnLaserOnTime",
    "scan",
    "turnLaserOffTime",
    "ScanTotalTime",
}


def _normalize_record_payload(record: RawLogRecord) -> dict[str, Any]:
    settings = get_settings()
    dt = parse_datetime(record.original_time_text, rounding=settings.default_time_rounding)
    event_kind, direction = infer_event_kind(record)
    sub_step = infer_sub_step(record)
    duration_ms = None
    for pattern in (STEP_DURATION_RE, COMPLETED_IN_RE):
        m = pattern.search(record.message)
        if m:
            duration_ms = float(m.group(1)) * 1000
            break

    extra = dict(record.extra)
    error_code_match = ERROR_CODE_RE.search(record.message)
    exception_match = EXCEPTION_TYPE_RE.search(record.raw_text)
    cycle_no = infer_cycle_from_text(record.source_file, record.message, record.raw_text)
    chip_name = infer_chip_name(record.source_file, record.message, record.raw_text)
    stage_name = infer_stage_name(record.source_file, record.message, record.raw_text)
    component = safe_component_name(record.component or record.module, source_file=record.source_file)
    if record.parser_name == "metrics_csv":
        # metrics/FOV 场景优先从 extra 中抽取稳定字段
        if isinstance(extra, dict):
            cycle_no = cycle_no or _to_int(extra.get("Cycle") or extra.get("cycle"))
            chip_name = chip_name or extra.get("Flowcell Id") or extra.get("chip_name") or extra.get("slide")
            component = component or ("FOVMetrics" if "Flowcell Id" in extra else "ImagingMetrics")
            if component == "ImagingMetrics":
                metric_name = extra.get("metric_name")
                if metric_name:
                    sub_step = f"imaging::{metric_name}"
                    metric_value = _to_float(extra.get("metric_value"))
                    if metric_value is not None:
                        duration_ms = metric_value * 1000.0
            elif component == "FOVMetrics":
                sub_step = "fov_capture"

    scope = infer_scope_from_texts(
        source_file=record.source_file,
        message=record.message,
        raw_text=record.raw_text,
        chip_name=chip_name,
        stage_name=stage_name,
        extra=extra,
    )
    chip_name = scope.chip_name or chip_name

    return {
        "source_file": record.source_file,
        "parser_name": record.parser_name,
        "original_time_text": record.original_time_text,
        "parsed_datetime": dt,
        "epoch_ms": to_epoch_ms(dt),
        "formatted_ms": format_ms(dt),
        "level": (record.level or "INFO").upper(),
        "component": component,
        "module": record.module,
        "thread": record.thread,
        "method_name": record.method_name,
        "class_name": record.class_name,
        "source_path": record.source_path,
        "line_no": record.line_no,
        "message": record.message,
        "raw_text": record.raw_text,
        "cycle_no": cycle_no,
        "sub_step": sub_step,
        "instrument_scope": scope.instrument_scope,
        "side_scope": scope.side_scope,
        "side_group": scope.side_group,
        "chip_name": chip_name,
        "chip_position": scope.chip_position,
        "chuck_no": scope.chuck_no,
        "slot_no": scope.slot_no,
        "stage_key": scope.stage_key,
        "stage_name": stage_name,
        "board_name": component,
        "event_kind": event_kind,
        "direction": direction,
        "duration_ms": duration_ms,
        "status": "error" if (record.level or "").upper() in {"WARN", "ERROR", "FATAL"} else "ok",
        "error_code": error_code_match.group(1) if error_code_match else None,
        "exception_type": exception_match.group(1) if exception_match else None,
        "side_confidence": scope.side_confidence,
        "side_evidence": scope.side_evidence,
        "extra_json": extra,
    }


def normalize_record_fast(record: RawLogRecord) -> dict[str, Any]:
    return _normalize_record_payload(record)


def normalize_record(record: RawLogRecord) -> NormalizedEvent:
    return build_normalized_event(**_normalize_record_payload(record))


def _to_int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except Exception:
        return None


def _to_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except Exception:
        return None
