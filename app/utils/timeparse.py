from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

TIME_PATTERNS = [
    ("%Y/%m/%d %H:%M:%S.%f", re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3,6}")),
    ("%Y/%m/%d %H:%M:%S:%f", re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}:\d{3,6}")),
    ("%Y-%m-%d %H:%M:%S.%f", re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3,6}")),
]


def extract_first_datetime(text: str) -> str | None:
    for _, pattern in TIME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def normalize_fractional_seconds(dt_text: str, rounding: Literal["truncate", "round"] = "truncate") -> tuple[str, str]:
    """
    返回: (标准化后的 datetime 文本, 原始文本)
    统一策略:
    - 保留 original_time_text 原样
    - 解析时支持 3~6 位小数
    - 输出 formatted_ms 统一为毫秒 3 位
    - 四位小数秒及以上默认截断到毫秒，也可切换 round
    """
    original = dt_text
    match = re.search(r"([.:])(\d{3,6})$", dt_text)
    if not match:
        return dt_text, original
    sep = match.group(1)
    frac = match.group(2)
    micros = frac.ljust(6, "0")
    if len(frac) > 3:
        if rounding == "round":
            micros_int = int(round(int(micros) / 1000.0) * 1000)
            micros = str(min(micros_int, 999000)).rjust(6, "0")
        else:
            micros = frac[:3].ljust(6, "0")
    else:
        micros = frac.ljust(6, "0")
    new_text = dt_text[: match.start(2)] + micros
    if sep == ":":
        # 格式化时保留 ':'，给 strptime 用
        new_text = new_text
    return new_text, original


def parse_datetime(dt_text: str | None, rounding: Literal["truncate", "round"] = "truncate") -> datetime | None:
    if not dt_text:
        return None
    normalized, _ = normalize_fractional_seconds(dt_text, rounding=rounding)
    for fmt, _ in TIME_PATTERNS:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def to_epoch_ms(dt: datetime | None) -> int | None:
    if not dt:
        return None
    return int(dt.timestamp() * 1000)


def format_ms(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}"


def format_seconds(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")
