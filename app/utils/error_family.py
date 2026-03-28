from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.settings import get_settings
from app.utils.rules import load_yaml

DEFAULT_FALLBACK_FAMILY = "general_error"


def _catalog_version(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _default_label(family: str) -> str:
    return family.replace("_", " ").strip().title() or DEFAULT_FALLBACK_FAMILY


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        text = str(pattern or "").strip()
        if not text:
            continue
        try:
            compiled.append(re.compile(text, re.IGNORECASE))
        except re.error:
            compiled.append(re.compile(re.escape(text), re.IGNORECASE))
    return compiled


@lru_cache(maxsize=8)
def _load_catalog_cached(path_str: str, version: int) -> dict[str, Any]:
    raw = load_yaml(Path(path_str))
    fallback_family = str(raw.get("fallback_family") or DEFAULT_FALLBACK_FAMILY).strip() or DEFAULT_FALLBACK_FAMILY
    raw_rules = raw.get("family_rules") or []

    rules: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, str]] = {}

    if isinstance(raw_rules, dict):
        for family, patterns in raw_rules.items():
            family_key = str(family or "").strip()
            if not family_key:
                continue
            pattern_list = [str(p) for p in (patterns or []) if str(p or "").strip()]
            rules.append(
                {
                    "family": family_key,
                    "patterns": _compile_patterns(pattern_list),
                }
            )
            metadata[family_key] = {
                "key": family_key,
                "label": _default_label(family_key),
                "description": "",
                "tone": "",
            }
    elif isinstance(raw_rules, list):
        for item in raw_rules:
            if not isinstance(item, dict):
                continue
            family_key = str(item.get("key") or item.get("family") or "").strip()
            if not family_key:
                continue
            pattern_list = [str(p) for p in (item.get("patterns") or []) if str(p or "").strip()]
            rules.append(
                {
                    "family": family_key,
                    "patterns": _compile_patterns(pattern_list),
                }
            )
            metadata[family_key] = {
                "key": family_key,
                "label": str(item.get("label") or _default_label(family_key)),
                "description": str(item.get("description") or ""),
                "tone": str(item.get("tone") or ""),
            }

    metadata.setdefault(
        fallback_family,
        {
            "key": fallback_family,
            "label": _default_label(fallback_family),
            "description": "",
            "tone": "",
        },
    )
    return {
        "rules": rules,
        "metadata": metadata,
        "fallback_family": fallback_family,
    }


def get_error_family_catalog() -> dict[str, Any]:
    settings = get_settings()
    path = settings.error_rules_path
    return _load_catalog_cached(str(path), _catalog_version(path))


def get_error_family_metadata(family: str | None) -> dict[str, str]:
    family_key = str(family or "").strip() or get_error_family_catalog()["fallback_family"]
    catalog = get_error_family_catalog()
    meta = dict(catalog["metadata"].get(family_key) or {})
    return {
        "key": family_key,
        "label": str(meta.get("label") or _default_label(family_key)),
        "description": str(meta.get("description") or ""),
        "tone": str(meta.get("tone") or ""),
    }


def classify_error_family_text(message: str | None, context: str | None = None) -> str:
    catalog = get_error_family_catalog()
    message_text = str(message or "")
    context_text = str(context or message_text or "")
    for target in [message_text, context_text]:
        if not target:
            continue
        for rule in catalog["rules"]:
            if any(pattern.search(target) for pattern in rule["patterns"]):
                return str(rule["family"])
    return str(catalog["fallback_family"])
