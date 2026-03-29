from __future__ import annotations

import json
import math
from typing import Any


def format_metric_value(value: Any) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        if value.is_integer():
            return f"{int(value):,}"
        if abs(value) >= 100:
            return f"{value:,.0f}"
        if abs(value) >= 10:
            return f"{value:,.1f}"
        return f"{value:,.2f}"
    return str(value)


def format_percent(numerator: int | float, denominator: int | float, digits: int = 1) -> str:
    if not denominator:
        return "0%"
    return f"{(float(numerator) / float(denominator)) * 100:.{digits}f}%"


def preview_text(value: Any, *, limit: int = 220, empty_text: str = "暂无说明") -> str:
    if value in (None, ""):
        return empty_text
    text = str(value).strip()
    if not text:
        return empty_text
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def display_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None:
        return "-"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
