from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from app.schemas.common import NormalizedEvent
from app.utils.error_family import classify_error_family_text, get_error_family_metadata
from app.utils.text import build_error_display_label, remove_dynamic_tokens, sha1_short


NOISE_PATTERNS = [
    r"create logger",
    r"logger:",
    r"debug trace",
]


def normalize_error_signature(event: NormalizedEvent) -> tuple[str | None, str | None, str | None]:
    message = event.message or ""
    lowered = message.lower()
    if event.level not in {"WARN", "ERROR", "FATAL"} and not any(
        k in lowered for k in ["exception", "error", "timeout", "failed"]
    ):
        return None, None, None

    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in NOISE_PATTERNS):
        return None, None, None

    family = classify_error_family(
        message,
        exception_type=event.exception_type,
        method_name=event.method_name,
        component=event.component,
    )
    family_meta = get_error_family_metadata(family)
    severity = "fatal" if event.level == "FATAL" else "error" if event.level == "ERROR" else "warning"
    display_label = build_error_display_label(event.exception_type, event.method_name, message, max_len=160)

    signature_core = " | ".join(
        p
        for p in [
            family,
            event.component,
            event.exception_type,
            event.method_name,
            remove_dynamic_tokens(message.lower())[:180],
        ]
        if p
    )
    signature = sha1_short(signature_core or message)
    event.extra_json = dict(event.extra_json or {})
    event.extra_json["display_signature"] = display_label
    event.extra_json["signature_core"] = signature_core[:240]
    event.extra_json["error_family_display"] = family_meta["label"]
    event.extra_json["error_family_description"] = family_meta["description"]
    return signature, family, severity


def classify_error_family(
    message: str,
    *,
    exception_type: str | None = None,
    method_name: str | None = None,
    component: str | None = None,
) -> str:
    context = " ".join(filter(None, [message, exception_type, method_name, component]))
    return classify_error_family_text(message=message, context=context)


def annotate_errors(events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
    result = []
    for event in events:
        signature, family, severity = normalize_error_signature(event)
        event.normalized_signature = signature
        event.error_family = family
        event.severity = severity
        result.append(event)
    return result


def top_error_clusters(events: list[NormalizedEvent], limit: int = 20) -> list[dict]:
    counter = Counter(e.normalized_signature for e in events if e.normalized_signature)
    representatives = {}
    for e in events:
        if e.normalized_signature and e.normalized_signature not in representatives:
            representatives[e.normalized_signature] = e
    rows = []
    for signature, count in counter.most_common(limit):
        rep = representatives[signature]
        display_label = None
        if isinstance(rep.extra_json, dict):
            display_label = rep.extra_json.get("display_signature")
        rows.append(
            {
                "normalized_signature": signature,
                "display_signature": display_label or rep.message[:120],
                "count": count,
                "error_family": rep.error_family,
                "severity": rep.severity,
                "component": rep.component,
                "message": rep.message,
                "exception_type": rep.exception_type,
            }
        )
    return rows
