from __future__ import annotations

import hashlib
import re
from pathlib import Path

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


def safe_component_name(value: str | None, source_file: str | None = None) -> str | None:
    if value:
        value = value.strip().strip("_|-")
        if value and value not in {"System", ".NET TP Worker"}:
            return value
    source = source_file or ""
    for pattern, name in COMPONENT_FILENAME_PATTERNS:
        if re.search(pattern, source, re.IGNORECASE):
            return name
    return value or None


def sha1_short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def remove_dynamic_tokens(text: str) -> str:
    patterns = [
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
    cleaned = text
    for p in patterns:
        cleaned = re.sub(p, "<*>", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b<\*>\s*,\s*<\*>\b", "<*>", cleaned)
    cleaned = re.sub(r"\b<\*>\b(?:\s*\.\s*<\*>)+", "<*>", cleaned)
    cleaned = normalize_whitespace(cleaned)
    return cleaned


def infer_cycle_from_text(*texts: str) -> int | None:
    patterns = [
        r"\bCycle\s*(\d+)\b",
        r"\bcycle\s*[=:]?\s*(\d+)\b",
        r"\bcycle(\d{1,4})\b",
        r"\bposition\s+(\d{1,4})\b",
        r"\bS(\d{3,4})\b",
        r"\bCycle(\d{1,4})\b",
    ]
    for text in texts:
        if not text:
            continue
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return int(m.group(1))
    return None


def infer_chip_name(*texts: str) -> str | None:
    patterns = [
        r"\bchip[_ -]?name[:= ]+([A-Za-z0-9_.-]+)",
        r"\bslide[_FN]*[:= ]+([A-Za-z0-9_.-]+)",
        r"\bflowcell id[,=: ]+([A-Za-z0-9_.-]+)",
        r"\b(HLAB\d{4,})\b",
        r"\b([A-Z]{2,}\d{3,})\b",
    ]
    for text in texts:
        if not text:
            continue
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1)
    return None


def infer_stage_name(*texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        m = re.search(r"\b([AB]\d{1,2})\b", text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def file_stem(path: str) -> str:
    return Path(path).stem


def extract_operation_name(message: str, method_name: str | None = None) -> str | None:
    msg = normalize_whitespace(message)
    if method_name:
        base = re.sub(r"Async$", "", method_name.strip())
        if base:
            device_match = re.search(r"DeviceName\s*([^,|]+)", msg, re.IGNORECASE)
            if device_match:
                return f"{base}:{device_match.group(1).strip()}"
            return base
    for pattern in KNOWN_OPERATION_PATTERNS:
        m = re.search(pattern, msg, re.IGNORECASE)
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
