from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.utils.side_inference import extract_chip_name, extract_stage_name_side

COMPONENT_FILENAME_PATTERNS = [
    (r"OpticalBoard", "OpticalBoard"),
    (r"RobotScheduler", "RobotScheduler"),
    (r"RunError", "RunErrorService"),
    (r"Scanner[_-]?1", "Scanner_1"),
    (r"Scanner[_-]?2", "Scanner_2"),
    (r"ScriptRunner", "ScriptRunner"),
    (r"StageRunMgr", "StageRunMgr"),
    (r"T100Scheduler", "T100Scheduler"),
    (r"XYZStage", "XYZStage"),
    (r"ErrorLogs", "GlobalErrorLog"),
    (r"ImagingMetrics", "ImagingMetrics"),
    (r"FOVMetrics", "FOVMetrics"),
    (r"workflow", "Workflow"),
]
COMPONENT_FILENAME_REGEXES = [(re.compile(pattern, re.IGNORECASE), name) for pattern, name in COMPONENT_FILENAME_PATTERNS]


KNOWN_OPERATION_PATTERNS = [
    r"([A-Za-z][A-Za-z0-9_]+):\s*DeviceName\s*([^,|]+)",
    r"([A-Za-z][A-Za-z0-9_]+)\s+is\s+success",
    r"([A-Za-z][A-Za-z0-9_]+)\s+Completed",
    r"([A-Za-z][A-Za-z0-9_]+)\s+start",
    r"Transfer from Chuck to Imager",
    r"Transfer from Imager to Chuck",
    r"Imaging Completed",
    r"Imaging start",
    r"CoarseThetaWithoutMoveStage",
    r"FineAlign",
    r"Incubation",
]
KNOWN_OPERATION_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in KNOWN_OPERATION_PATTERNS]
DEVICE_NAME_RE = re.compile(r"DeviceName\s*([^,|]+)", re.IGNORECASE)
REMOVE_DYNAMIC_TOKEN_REGEXES = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b\d+\b",
        r"\b\d+\.\d+\b",
        r"0x[a-fA-F0-9]+",
        r"\b[0-9a-f]{8,}\b",
        r"[A-Z]:\\[^\s|]+",
        r"/[^\s|]+",
        r":\d+\b",
        r"\b[0-9a-fA-F-]{16,}\b",
        r"\b(client|task|request|trace|session|token|id)[ :=-]*[a-z0-9-]{4,}\b",
        r"\b(row|column|cycle|position|serverid|server id|volume|asprate|startspeed|accspeed|status|power)[ :=-]*<\*>",
    ]
]
CYCLE_REGEXES = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bCycle\s*(\d+)\b",
        r"\bcycle\s*[=:]?\s*(\d+)\b",
        r"\bcycle(\d{1,4})(?=[_.\-\s]|$)",
        r"\bposition\s+(\d{1,4})\b",
        r"\bS(\d{3,4})\b",
        r"\bCycle(\d{1,4})\b",
    ]
]


def safe_component_name(value: str | None, source_file: str | None = None) -> str | None:
    if value:
        value = value.strip().strip("_|-")
        if value and value not in {"System", ".NET TP Worker"}:
            return value
    source = source_file or ""
    for pattern, name in COMPONENT_FILENAME_REGEXES:
        if pattern.search(source):
            return name
    return value or None


def sha1_short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def remove_dynamic_tokens(text: str) -> str:
    cleaned = text
    for pattern in REMOVE_DYNAMIC_TOKEN_REGEXES:
        cleaned = pattern.sub("<*>", cleaned)
    cleaned = re.sub(r"\b<\*>\s*,\s*<\*>\b", "<*>", cleaned)
    cleaned = re.sub(r"\b<\*>\b(?:\s*\.\s*<\*>)+", "<*>", cleaned)
    cleaned = normalize_whitespace(cleaned)
    return cleaned


def infer_cycle_from_text(*texts: str) -> int | None:
    for text in texts:
        if not text:
            continue
        for pattern in CYCLE_REGEXES:
            m = pattern.search(text)
            if m:
                return int(m.group(1))
    return None


def infer_chip_name(*texts: str) -> str | None:
    return extract_chip_name(*texts)


def infer_stage_name(*texts: str) -> str | None:
    return extract_stage_name_side(*texts)


def file_stem(path: str) -> str:
    return Path(path).stem


def extract_operation_name(message: str, method_name: str | None = None) -> str | None:
    msg = normalize_whitespace(message)
    if method_name:
        base = re.sub(r"Async$", "", method_name.strip())
        if base:
            device_match = DEVICE_NAME_RE.search(msg)
            if device_match:
                return f"{base}:{device_match.group(1).strip()}"
            return base
    for pattern in KNOWN_OPERATION_REGEXES:
        m = pattern.search(msg)
        if m:
            if m.lastindex and m.lastindex >= 2:
                return f"{m.group(1)}:{m.group(2).strip()}"
            return m.group(1) if m.lastindex else m.group(0)
    if ":" in msg and len(msg) < 120:
        return msg.split(":", 1)[0].strip()
    return None


def build_error_display_label(exception_type: str | None, method_name: str | None, message: str, max_len: int = 120) -> str:
    text = remove_dynamic_tokens(message.lower())
    text = re.sub(r"^\|_\|\s*", "", text)
    text = normalize_whitespace(text)
    prefix = " | ".join([p for p in [exception_type, method_name] if p])
    label = f"{prefix} | {text}" if prefix else text
    return label[:max_len]
