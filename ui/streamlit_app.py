from __future__ import annotations

import json
import math
import os
import re
import sys
import textwrap
import hashlib
import inspect
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from app.core.bootstrap import bootstrap_for_local_run
bootstrap_for_local_run()

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import yaml
from ui.shared.design_system import get_design_tokens, streamlit_component_overrides, streamlit_root_vars

st.set_page_config(page_title="测序仪日志整理及问题反馈系统", layout="wide")

DEFAULT_API_BASE = os.getenv("STREAMLIT_API_BASE", "http://127.0.0.1:8000/api/v1")
DURATION_UNITS = {"毫秒(ms)": "ms", "秒(s)": "s", "分钟(min)": "min", "小时(h)": "h"}
PLOTLY_COLOR_SEQUENCE = ["#052659", "#0B5CAD", "#5483B3", "#7DA0CA", "#38A3E0", "#C1E8FF"]
TIMELINE_COLOR_SEQUENCE = list(
    dict.fromkeys(
        px.colors.qualitative.Safe
        + px.colors.qualitative.Bold
        + px.colors.qualitative.Plotly
        + px.colors.qualitative.Dark24
    )
)
ERROR_SEVERITY_COLORS = {
    "fatal": "#8C1C13",
    "error": "#D94841",
    "warn": "#D96B3B",
    "warning": "#D96B3B",
    "info": "#5B7C99",
    "unknown": "#7A7A7A",
}
_ACTIVE_SCOPE_PARAMS: dict[str, Any] = {}
PAGE_META = {
    "首页 / 仪表盘": {"title": "首页总览", "icon": "dashboard", "description": "集中查看任务状态、问题密度、组件分布与关键处理指标。"},
    "历史项目中心": {"title": "历史项目中心", "icon": "archive", "description": "浏览已有任务记录，快速切换不同项目并回看历史分析结果。"},
    "文件上传": {"title": "文件上传", "icon": "upload", "description": "上传日志文件或压缩包，提交后台解析与聚合任务。"},
    "统一事件流": {"title": "统一事件流", "icon": "stream", "description": "按组件、级别、Cycle 和关键词检索统一归档后的事件流。"},
    "耗时分析": {"title": "耗时分析", "icon": "clock", "description": "查看 Cycle 与 Sub-step 的耗时表现，定位潜在性能瓶颈。"},
    "事件流时间轴": {"title": "事件流时间轴", "icon": "timeline", "description": "从时间维度观察各组件动作顺序与阶段重叠关系。"},
    "错误分析": {"title": "错误分析", "icon": "alert", "description": "聚焦错误簇、错误家族和组件分布，快速识别高频问题。"},
    "参数趋势分析": {"title": "参数趋势分析", "icon": "sliders", "description": "分析关键参数随时间或 Cycle 的变化趋势。"},
    "LLM 诊断": {"title": "LLM 综合诊断", "icon": "brain", "description": "结合日志、上下文、源码与历史案例生成结构化诊断结论。"},
    "原始文件预览": {"title": "原始文件预览", "icon": "file", "description": "在线查看原始日志文件内容、编码与预览片段。"},
    "未知日志待标注池": {"title": "未知日志待标注池", "icon": "spark", "description": "收集未命中 parser 或规则的日志簇，便于补充规则与标注。"},
    "规则建议审核视图": {"title": "规则建议审核", "icon": "review", "description": "集中审核规则建议与解决方案记录，完善知识沉淀流程。"},
    "配置页面": {"title": "配置页面", "icon": "settings", "description": "查看并调整系统配置、策略开关和分析参数。"},
    "导出": {"title": "导出", "icon": "export", "description": "导出任务结果、解决方案数据及相关分析产物。"},
}


def _icon_svg(name: str) -> str:
    icons = {
        "dashboard": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="8" height="8" rx="2"></rect><rect x="13" y="3" width="8" height="5" rx="2"></rect><rect x="13" y="10" width="8" height="11" rx="2"></rect><rect x="3" y="13" width="8" height="8" rx="2"></rect></svg>',
        "archive": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1.5"></rect><path d="M5 8h14v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8Z"></path><path d="M10 12h4"></path></svg>',
        "upload": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4"></path><path d="m7 9 5-5 5 5"></path><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"></path></svg>',
        "stream": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"></path><path d="M4 12h10"></path><path d="M4 17h13"></path><circle cx="18" cy="12" r="2"></circle></svg>',
        "clock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 3"></path></svg>',
        "timeline": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6h12"></path><path d="M6 12h8"></path><path d="M6 18h12"></path><circle cx="16" cy="12" r="2"></circle><circle cx="6" cy="6" r="2"></circle><circle cx="18" cy="18" r="2"></circle></svg>',
        "alert": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4 3 20h18L12 4Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>',
        "sliders": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 21v-7"></path><path d="M4 10V3"></path><path d="M12 21v-9"></path><path d="M12 8V3"></path><path d="M20 21v-5"></path><path d="M20 12V3"></path><path d="M2 14h4"></path><path d="M10 8h4"></path><path d="M18 16h4"></path></svg>',
        "brain": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 4.5a3.5 3.5 0 0 0-3.5 3.5v7a3 3 0 0 0 3 3"></path><path d="M14.5 4.5A3.5 3.5 0 0 1 18 8v7a3 3 0 0 1-3 3"></path><path d="M9 8.5a2.5 2.5 0 0 1 5 0v7a2.5 2.5 0 0 1-5 0Z"></path><path d="M14 10.5a2.5 2.5 0 0 1 5 0v3a2.5 2.5 0 0 1-5 0"></path><path d="M5 10.5a2.5 2.5 0 0 1 5 0v3A2.5 2.5 0 0 1 5 13.5"></path></svg>',
        "file": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></svg>',
        "review": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"></path><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>',
        "settings": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 1-3 0 1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 1 0-3 1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 1 3 0 1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.29.26.49.62.6 1a1.7 1.7 0 0 0 0 3c-.11.38-.31.74-.6 1Z"></path></svg>',
        "export": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"></path><path d="m7 10 5 5 5-5"></path><path d="M5 21h14"></path></svg>',
        "spark": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z"></path><path d="M19 16l.9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9L19 16Z"></path></svg>',
        "task": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="3"></rect><path d="M8 9h8"></path><path d="M8 13h8"></path><path d="M8 17h5"></path></svg>',
        "api": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3"></path><path d="M18.4 5.6 16.3 7.7"></path><path d="M21 12h-3"></path><path d="m18.4 18.4-2.1-2.1"></path><path d="M12 21v-3"></path><path d="m7.7 16.3-2.1 2.1"></path><path d="M6 12H3"></path><path d="m7.7 7.7-2.1-2.1"></path><circle cx="12" cy="12" r="4"></circle></svg>',
    }
    return icons.get(name, icons["spark"])


def _format_metric_value(value: Any) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if math.isfinite(value):
            if value.is_integer():
                return f"{int(value):,}"
            if abs(value) >= 100:
                return f"{value:,.0f}"
            if abs(value) >= 10:
                return f"{value:,.1f}"
            return f"{value:,.2f}"
        return str(value)
    return str(value)


DEFAULT_CARD_TONES = ["#052659", "#0B5CAD", "#D96B3B", "#DCEBFA", "#6D8FB6", "#F3E1A6"]
DEFAULT_BADGE_TONES = ["#052659", "#DCEBFA", "#D96B3B", "#E7EFF8"]
JsonDict = dict[str, Any]
PROGRESS_STAGE_FLOW = ["uploaded", "parsing", "summary", "postprocess", "completed"]
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
UTC_TZ = ZoneInfo("UTC")
ADMIN_ENV_PRIORITY_KEYS = [
    "LLM_ENABLED",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_PREVIEW_TIMEOUT_SECONDS",
    "LLM_PREVIEW_MAX_RETRIES",
    "LLM_PREVIEW_CACHE_TTL_SECONDS",
    "LLM_DIAGNOSIS_UI_TIMEOUT_SECONDS",
    "LLM_CONTEXT_MAX_TOKEN_BUDGET",
    "SYSTEM_MEMORY_SOFT_LIMIT_PERCENT",
    "SYSTEM_MEMORY_SOFT_RESERVE_MB",
    "SYSTEM_CPU_SOFT_LIMIT_PERCENT",
    "SYSTEM_MEMORY_GUARD_WAIT_SECONDS",
    "MAX_UPLOAD_MB",
    "CHUNK_SIZE",
]
PROGRESS_STAGE_META = {
    "uploaded": {"label": "上传", "aliases": ("uploaded", "queued", "discover", "prescan", "prepare", "upload", "workspace", "input")},
    "parsing": {"label": "解析", "aliases": ("parse", "parser", "parsing")},
    "summary": {"label": "汇总", "aliases": ("merge", "normalize", "cycle_context", "context", "summary", "aggregate")},
    "postprocess": {"label": "后处理", "aliases": ("postprocess", "cluster", "materializ", "finaliz", "dashboard", "error_prep")},
    "completed": {"label": "完成", "aliases": ("completed", "finished", "success")},
}
_SAFE_DATAFRAME_CALL_COUNTS: dict[str, int] = {}


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    hex_value = value.strip().lstrip("#")
    if len(hex_value) == 3:
        hex_value = "".join(ch * 2 for ch in hex_value)
    if len(hex_value) != 6:
        raise ValueError(f"Unsupported color value: {value}")
    return (
        int(hex_value[0:2], 16),
        int(hex_value[2:4], 16),
        int(hex_value[4:6], 16),
    )


def _rgb_to_hex(rgb: tuple[float, float, float] | tuple[int, int, int]) -> str:
    clipped = [max(0, min(255, int(round(channel)))) for channel in rgb]
    return "#{:02X}{:02X}{:02X}".format(*clipped)


def _normalize_color_hex(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("#"):
        try:
            _hex_to_rgb(text)
            return text.upper()
        except ValueError:
            return None
    match = re.fullmatch(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)", text, re.IGNORECASE)
    if not match:
        return None
    rgb = tuple(max(0, min(255, int(channel))) for channel in match.groups())
    return _rgb_to_hex(cast(tuple[int, int, int], rgb))


def _mix_hex(source: str, target: str, ratio: float) -> str:
    start_rgb = _hex_to_rgb(source)
    end_rgb = _hex_to_rgb(target)
    ratio = max(0.0, min(1.0, ratio))
    mixed_rgb = (
        start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio,
        start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio,
        start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio,
    )
    return _rgb_to_hex(mixed_rgb)


def _relative_luminance(color: str) -> float:
    def _channel_luminance(channel: int) -> float:
        srgb = channel / 255
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    normalized = _normalize_color_hex(color)
    if normalized is None:
        return 0.5
    red, green, blue = _hex_to_rgb(normalized)
    return 0.2126 * _channel_luminance(red) + 0.7152 * _channel_luminance(green) + 0.0722 * _channel_luminance(blue)


def _contrast_ratio(color_a: str, color_b: str) -> float:
    luminance_a = _relative_luminance(color_a)
    luminance_b = _relative_luminance(color_b)
    lighter = max(luminance_a, luminance_b)
    darker = min(luminance_a, luminance_b)
    return (lighter + 0.05) / (darker + 0.05)


def _pick_contrast_text(background: str) -> str:
    light_text = "#F8FBFF"
    dark_text = "#04101F"
    return light_text if _contrast_ratio(background, light_text) >= _contrast_ratio(background, dark_text) else dark_text


def _ensure_contrast(background: str, preferred: str, fallback: str, minimum_ratio: float) -> str:
    preferred_ratio = _contrast_ratio(background, preferred)
    if preferred_ratio >= minimum_ratio:
        return preferred
    fallback_ratio = _contrast_ratio(background, fallback)
    return fallback if fallback_ratio > preferred_ratio else preferred


def _derive_readable_tint(background: str, ink: str, *, target: str, preferred_ratio: float, fallback_ratio: float) -> str:
    candidate = ink
    best_candidate = candidate
    best_ratio = _contrast_ratio(background, candidate)
    for step in range(1, 21):
        ratio = step / 20
        candidate = _mix_hex(ink, target, ratio)
        contrast = _contrast_ratio(background, candidate)
        if contrast > best_ratio:
            best_candidate = candidate
            best_ratio = contrast
        if contrast >= preferred_ratio:
            return candidate
    if best_ratio >= fallback_ratio:
        return best_candidate
    return ink


def _dropna_frame(df: pd.DataFrame, *subset: str) -> pd.DataFrame:
    # Pandas works here, but Pylance can misread the overloaded subset signature.
    return cast(pd.DataFrame, df.dropna(subset=cast(Any, tuple(subset))))


def _safe_len(value: Any) -> int:
    if isinstance(value, (str, list, tuple, set, dict)):
        return len(value)
    return 0


def _tone_vars(background: str) -> dict[str, str]:
    ink = _ensure_contrast(background, _pick_contrast_text(background), "#04101F", 4.5)
    is_dark_surface = ink == "#F8FBFF"
    chip_target = "#FFFFFF" if is_dark_surface else "#052659"
    muted = _derive_readable_tint(
        background,
        ink,
        target="#FFFFFF" if is_dark_surface else "#04101F",
        preferred_ratio=4.5,
        fallback_ratio=3.2,
    )
    line = _derive_readable_tint(
        background,
        ink,
        target="#FFFFFF" if is_dark_surface else "#052659",
        preferred_ratio=2.2,
        fallback_ratio=1.7,
    )
    chip_bg = _mix_hex(background, chip_target, 0.18 if is_dark_surface else 0.08)
    chip_ink = _ensure_contrast(chip_bg, ink, _pick_contrast_text(chip_bg), 4.5)
    return {
        "surface-bg": f"linear-gradient(180deg, {_mix_hex(background, '#FFFFFF', 0.14 if is_dark_surface else 0.04)} 0%, {background} 100%)",
        "surface-ink": ink,
        "surface-muted": muted,
        "surface-line": line,
        "surface-chip-bg": chip_bg,
        "surface-chip-line": _derive_readable_tint(
            chip_bg,
            chip_ink,
            target="#FFFFFF" if _relative_luminance(chip_bg) < 0.35 else "#052659",
            preferred_ratio=2.0,
            fallback_ratio=1.6,
        ),
        "surface-chip-ink": chip_ink,
    }


def _style_vars(style_map: dict[str, str]) -> str:
    return "; ".join(f"--{name}: {value}" for name, value in style_map.items())


def _wrap_chart_title(title: str, line_width: int = 24) -> list[str]:
    normalized = str(title or "").replace("<br>", "\n")
    wrapped_lines: list[str] = []
    for block in normalized.splitlines():
        current = block.strip()
        if not current:
            continue
        if len(current) <= line_width:
            wrapped_lines.append(current)
            continue
        wrapped_lines.extend(textwrap.wrap(current, width=line_width, break_long_words=True, break_on_hyphens=False))
    return wrapped_lines or [str(title or "").strip()]


def _format_percent(numerator: int | float, denominator: int | float, digits: int = 1) -> str:
    if not denominator:
        return "0%"
    return f"{(float(numerator) / float(denominator)) * 100:.{digits}f}%"


def _clean_chart_title(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"undefined", "none", "null", "nan"}:
        return None
    return text


def _html_block(markup: str) -> str:
    return textwrap.dedent(markup).strip()


def inject_design_system(mode: str = "light"):
    theme = get_design_tokens(mode)
    st.markdown(
        """
        <style>
        :root {
            --bg-top: #e8f5ff;
            --bg-bottom: #bfd8f0;
            --surface: rgba(255, 255, 255, 0.82);
            --surface-strong: rgba(255, 255, 255, 0.94);
            --ink: #021024;
            --muted: #3b6898;
            --line: rgba(84, 131, 179, 0.20);
            --line-strong: rgba(84, 131, 179, 0.34);
            --accent: #052659;
            --accent-strong: #5483B3;
            --accent-soft: #7DA0CA;
            --accent-ice: #C1E8FF;
            --shadow: 0 24px 72px rgba(2, 16, 36, 0.12);
            --radius-xl: 30px;
            --radius-lg: 24px;
            --page-pad: clamp(1rem, 2vw, 2rem);
        }

        html, body, [class*="css"], [data-testid="stApp"] {
            font-family: "Avenir Next", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(193, 232, 255, 0.85) 0, transparent 32%),
                radial-gradient(circle at top right, rgba(125, 160, 202, 0.25) 0, transparent 24%),
                linear-gradient(180deg, var(--bg-top) 0%, #d6eaff 40%, var(--bg-bottom) 100%);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(2, 16, 36, 0.96) 0%, rgba(5, 38, 89, 0.95) 100%);
            border-right: 1px solid rgba(193, 232, 255, 0.12);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.2rem;
        }

        .block-container {
            max-width: 1420px;
            padding-top: 1.35rem;
            padding-bottom: 3rem;
            padding-left: var(--page-pad);
            padding-right: var(--page-pad);
        }

        #MainMenu, footer, header[data-testid="stHeader"] {
            visibility: hidden;
        }

        h1, h2, h3, h4 {
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", "STSong", "Songti SC", serif;
            color: var(--ink);
            letter-spacing: -0.025em;
            line-height: 1.06;
        }

        p, label, [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {
            color: var(--ink);
        }

        [data-testid="stMarkdownContainer"] p {
            line-height: 1.65;
        }

        [data-testid="stSidebar"] .stTextInput > label,
        [data-testid="stSidebar"] .stSelectbox > label,
        [data-testid="stSidebar"] .stRadio > label {
            font-size: 0.78rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #f4fbff !important;
            font-weight: 600;
        }

        [data-testid="stSidebar"] .stTextInput > label *,
        [data-testid="stSidebar"] .stSelectbox > label *,
        [data-testid="stSidebar"] .stRadio > label *,
        [data-testid="stSidebar"] label[data-testid="stWidgetLabel"],
        [data-testid="stSidebar"] label[data-testid="stWidgetLabel"] *,
        [data-testid="stSidebar"] div[data-testid="stWidgetLabel"],
        [data-testid="stSidebar"] div[data-testid="stWidgetLabel"] * {
            color: #f4fbff !important;
        }

        [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"],
        [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] span,
        [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] div,
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stSelectbox svg {
            color: #021024 !important;
            fill: #021024 !important;
        }

        [data-testid="stSidebar"] [data-testid="stBaseButton-header"] svg,
        [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] svg {
            color: #F4FBFF !important;
            fill: currentColor !important;
            stroke: currentColor !important;
        }

        [data-testid="stSidebar"] [data-baseweb="radio"] label,
        [data-testid="stSidebar"] [data-baseweb="radio"] label *,
        [data-testid="stSidebar"] [role="radiogroup"] label,
        [data-testid="stSidebar"] [role="radiogroup"] label * {
            color: #f4fbff !important;
        }

        [data-testid="stSidebar"] [data-baseweb="radio"] label,
        [data-testid="stSidebar"] [role="radiogroup"] label {
            border-radius: 16px;
            padding: 0.28rem 0.5rem;
            transition: background 0.18s ease;
        }

        [data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div,
        [data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div *,
        [data-testid="stSidebar"] [role="radiogroup"] input:checked + div,
        [data-testid="stSidebar"] [role="radiogroup"] input:checked + div * {
            color: #ffffff !important;
        }

        [data-testid="stNumberInputContainer"],
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea,
        [data-testid="stNumberInput"] input,
        [data-testid="stFileUploader"] section {
            background: var(--surface) !important;
            border: 1px solid var(--line) !important;
            border-radius: 18px !important;
            box-shadow: none !important;
        }

        [data-testid="stNumberInputContainer"] [data-baseweb="input"] > div,
        [data-testid="stNumberInputContainer"] [data-baseweb="input"] {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }

        [data-testid="stNumberInputContainer"] button,
        [data-testid="stNumberInputContainer"] button svg {
            color: var(--ink) !important;
            fill: currentColor !important;
        }

        [data-testid="stNumberInputContainer"] button {
            background: var(--surface) !important;
            border-left: 1px solid var(--line) !important;
        }

        [data-baseweb="tag"] {
            background: rgba(84, 131, 179, 0.12) !important;
            border: 1px solid rgba(84, 131, 179, 0.18) !important;
            border-radius: 999px !important;
        }

        [data-baseweb="tag"] *,
        [data-baseweb="tag"] span,
        [data-baseweb="tag"] div {
            color: #052659 !important;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseButton-secondary"] > button,
        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-primary"] > button {
            min-height: 2.85rem;
            border-radius: 999px !important;
            border: 1px solid var(--line-strong) !important;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(193, 232, 255, 0.72) 100%) !important;
            background-color: #FFFFFF !important;
            color: var(--ink) !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.1rem !important;
            transition: all 0.18s ease;
        }

        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-primary"] > button {
            background: linear-gradient(135deg, #FFFFFF 0%, #EAF4FF 100%) !important;
            background-color: #FFFFFF !important;
            color: var(--ink) !important;
            border-color: #7DA0CA !important;
        }

        .stButton > button p,
        .stDownloadButton > button p,
        [data-testid="stBaseButton-secondary"] p,
        [data-testid="stBaseButton-primary"] p,
        .stButton > button span,
        .stDownloadButton > button span,
        [data-testid="stBaseButton-secondary"] span,
        [data-testid="stBaseButton-primary"] span,
        [data-testid="stBaseButton-secondary"] > button p,
        [data-testid="stBaseButton-primary"] > button p,
        [data-testid="stBaseButton-secondary"] > button span,
        [data-testid="stBaseButton-primary"] > button span {
            color: inherit !important;
            mix-blend-mode: normal !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stBaseButton-primary"]:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 32px rgba(31, 36, 33, 0.12);
        }

        [data-testid="stMetric"] {
            background: var(--surface) !important;
            border: 1px solid var(--line) !important;
            border-radius: 22px !important;
            padding: 1rem 1.15rem !important;
            box-shadow: var(--shadow);
            min-height: 100%;
        }

        [data-testid="stMetricLabel"] {
            color: var(--muted) !important;
            font-size: 0.82rem !important;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }

        [data-testid="stMetricValue"] {
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            font-size: clamp(1.55rem, 2vw, 2.25rem) !important;
            color: var(--ink) !important;
        }

        [data-testid="stProgressBar"] {
            margin-top: 0.25rem;
            margin-bottom: 0.55rem;
        }

        [data-testid="stProgressBar"] > div {
            background: rgba(31, 36, 33, 0.08) !important;
            border-radius: 999px !important;
        }

        [data-testid="stProgressBar"] > div > div {
            background: linear-gradient(90deg, #052659 0%, #5483B3 60%, #7DA0CA 100%) !important;
            border-radius: 999px !important;
        }

        [data-testid="stTabs"] [role="tablist"] {
            gap: 0.6rem;
            margin-bottom: 1rem;
        }

        [data-testid="stTabs"] [role="tab"] {
            border-radius: 999px;
            border: 1px solid transparent;
            background: rgba(255, 251, 246, 0.68);
            padding: 0.45rem 0.95rem;
            color: var(--muted);
        }

        [data-testid="stTabs"] [aria-selected="true"] {
            background: linear-gradient(135deg, #052659 0%, #5483B3 100%) !important;
            color: #f4fbff !important;
            border-color: #052659 !important;
        }

        [data-testid="stTabs"] [aria-selected="true"] *,
        [data-testid="stTabs"] [aria-selected="true"] p,
        [data-testid="stTabs"] [aria-selected="true"] span {
            color: #f4fbff !important;
        }

        [data-testid="stExpander"] details {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 22px;
            box-shadow: var(--shadow);
            overflow: hidden;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
            color: #0B5CAD !important;
            fill: currentColor !important;
            stroke: currentColor !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [data-testid="stExpander"] label,
        [data-testid="stSidebar"] [data-testid="stExpander"] .stTextInput label p {
            color: #04101F !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"]:has(input[type="checkbox"]) [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [data-testid="stExpander"]:has(input[type="checkbox"]) label,
        [data-testid="stSidebar"] [data-testid="stExpander"]:has(input[type="checkbox"]) span {
            color: #B42318 !important;
            font-weight: 700 !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"]:has(input[type="checkbox"]) .stButton > button,
        [data-testid="stSidebar"] [data-testid="stExpander"]:has(input[type="checkbox"]) [data-testid="stBaseButton-secondary"] > button,
        [data-testid="stSidebar"] [data-testid="stExpander"]:has(input[type="checkbox"]) [data-testid="stBaseButton-secondary"] button {
            background: linear-gradient(180deg, #FFF4F2 0%, #FFD9D4 100%) !important;
            border-color: #D92D20 !important;
            color: #B42318 !important;
        }

        [data-testid="stDataFrame"],
        [data-testid="stTable"] {
            border-radius: 24px;
            overflow: hidden;
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
        }

        div[data-testid="stPlotlyChart"] {
            background: linear-gradient(180deg, var(--plot-start) 0%, var(--plot-end) 100%);
            border: 1px solid var(--line);
            border-radius: 26px;
            box-shadow: var(--shadow);
            padding: 0.7rem 0.7rem 0.35rem;
            margin: 0 0 1rem;
            overflow: hidden;
        }

        div[data-testid="stPlotlyChart"] > div {
            position: relative;
            z-index: 0;
        }

        div[data-testid="stPlotlyChart"],
        div[data-testid="stPlotlyChart"] > div,
        div[data-testid="stPlotlyChart"] .js-plotly-plot,
        div[data-testid="stPlotlyChart"] .plot-container,
        div[data-testid="stPlotlyChart"] .svg-container,
        div[data-testid="stPlotlyChart"] .gl-container,
        div[data-testid="stPlotlyChart"] canvas {
            transition: background-color 0.18s ease, border-color 0.18s ease;
        }

        div[data-testid="stPlotlyChart"] .js-plotly-plot,
        div[data-testid="stPlotlyChart"] .plot-container,
        div[data-testid="stPlotlyChart"] .svg-container,
        div[data-testid="stPlotlyChart"] .gl-container,
        div[data-testid="stPlotlyChart"] canvas {
            background: var(--chart-paper-bg) !important;
        }

        .chart-frame-title {
            margin: 0.15rem 0 0.45rem;
            padding: 0 0.2rem;
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            font-size: clamp(1.02rem, 1.1vw, 1.22rem);
            color: var(--ink);
            line-height: 1.35;
            letter-spacing: -0.02em;
            word-break: break-word;
        }

        .modebar {
            top: 0.35rem !important;
            right: 0.35rem !important;
        }

        div[data-testid="stHorizontalBlock"] {
            align-items: stretch;
        }

        [data-testid="stAlert"] {
            border-radius: 20px;
            border: 1px solid var(--line);
        }

        .premium-hero {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.96) 0%, rgba(193, 232, 255, 0.82) 100%);
            border: 1px solid var(--line);
            border-radius: var(--radius-xl);
            padding: clamp(1.2rem, 2vw, 2rem);
            box-shadow: var(--shadow);
            margin-bottom: 1.4rem;
        }

        .dashboard-hero {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.97) 0%, rgba(233, 245, 255, 0.94) 100%);
            border: 1px solid var(--line);
            border-radius: 32px;
            box-shadow: var(--shadow);
            padding: 1.5rem 1.5rem 1.25rem;
            margin-bottom: 1.1rem;
        }

        .dashboard-hero h1,
        .dashboard-hero h2,
        .dashboard-hero h3,
        .dashboard-hero > p {
            color: #021024 !important;
        }

        .dashboard-title {
            margin: 0 0 0.3rem;
            font-size: clamp(2rem, 3vw, 3rem);
        }

        .dashboard-subtitle {
            margin: 0;
            color: #3b6898 !important;
            max-width: 58rem;
        }

        .dashboard-divider {
            height: 4px;
            border-radius: 999px;
            background: linear-gradient(90deg, #5483B3 0%, #7DA0CA 50%, #C1E8FF 100%);
            margin: 1.1rem 0 0.4rem;
        }

        .dashboard-hero .premium-stat-grid {
            margin-top: 0.9rem;
            margin-bottom: 0.4rem;
        }

        .dashboard-hero .premium-stat-card {
            box-shadow: none;
            min-height: 100%;
        }

        .dashboard-snapshot {
            display: grid;
            grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
            gap: 0.95rem;
            margin: 0.9rem 0 0.4rem;
        }

        .dashboard-progress-shell {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.84) 0%, rgba(233, 245, 255, 0.72) 100%);
            border: 1px solid rgba(84, 131, 179, 0.18);
            border-radius: 24px;
            padding: 1rem 1.05rem;
        }

        .dashboard-progress-meta {
            display: flex;
            justify-content: space-between;
            gap: 0.8rem;
            align-items: baseline;
            margin-bottom: 0.75rem;
        }

        .dashboard-progress-label {
            color: var(--muted);
            font-size: 0.78rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .dashboard-progress-value {
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            font-size: clamp(1.5rem, 2vw, 2rem);
            color: var(--ink);
        }

        .dashboard-progress-track {
            width: 100%;
            height: 0.8rem;
            background: rgba(84, 131, 179, 0.12);
            border-radius: 999px;
            overflow: hidden;
        }

        .dashboard-progress-track span {
            display: block;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #052659 0%, #0B5CAD 55%, #7DA0CA 100%);
        }

        .dashboard-progress-stage {
            margin: 0.85rem 0 0;
            color: var(--ink);
            font-size: 0.96rem;
            font-weight: 600;
        }

        .dashboard-progress-message {
            margin: 0.32rem 0 0;
            color: var(--muted);
            font-size: 0.9rem;
        }

        .dashboard-insight-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
        }

        .dashboard-insight-card {
            background: var(--surface-bg, var(--surface-strong));
            border: 1px solid var(--surface-line, var(--line));
            border-radius: 22px;
            padding: 0.85rem 0.95rem;
            min-height: 100%;
        }

        .dashboard-insight-label {
            color: var(--surface-muted, var(--muted));
            font-size: 0.76rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
            line-height: 1.4;
        }

        .dashboard-insight-value {
            margin-top: 0.42rem;
            color: var(--surface-ink, var(--ink));
            font-size: 1rem;
            font-weight: 700;
            line-height: 1.45;
            word-break: break-word;
        }

        .dashboard-progress-panel {
            position: relative;
            overflow: hidden;
            border-radius: 28px;
            border: 1px solid rgba(84, 131, 179, 0.22);
            background:
                radial-gradient(circle at top right, rgba(193, 232, 255, 0.92) 0%, rgba(193, 232, 255, 0) 36%),
                linear-gradient(135deg, rgba(3, 27, 58, 0.96) 0%, rgba(8, 44, 91, 0.96) 52%, rgba(17, 71, 130, 0.9) 100%);
            box-shadow: 0 18px 42px rgba(5, 38, 89, 0.22);
            margin: 0.4rem 0 1rem;
        }

        .dashboard-progress-panel::before {
            content: "";
            position: absolute;
            inset: -40% auto auto -10%;
            width: 220px;
            height: 220px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(193, 232, 255, 0.32) 0%, rgba(193, 232, 255, 0) 72%);
            pointer-events: none;
        }

        .dashboard-progress-hero {
            position: relative;
            padding: 1.15rem 1.2rem 0.9rem;
            border-bottom: 1px solid rgba(193, 232, 255, 0.12);
        }

        .dashboard-progress-topline {
            color: rgba(193, 232, 255, 0.88);
            font-size: 0.76rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .dashboard-progress-heading-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.9rem;
            margin-top: 0.72rem;
        }

        .dashboard-progress-heading {
            color: #F8FBFF;
            font-size: clamp(1.18rem, 1.8vw, 1.7rem);
            font-weight: 700;
            line-height: 1.25;
            word-break: break-word;
        }

        .dashboard-progress-badge {
            flex: 0 0 auto;
            padding: 0.48rem 0.8rem;
            border-radius: 999px;
            background: rgba(193, 232, 255, 0.15);
            border: 1px solid rgba(193, 232, 255, 0.22);
            color: #F8FBFF;
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            font-size: 1.05rem;
            font-weight: 700;
            min-width: 4.8rem;
            text-align: center;
            backdrop-filter: blur(8px);
        }

        .dashboard-progress-subline {
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            align-items: center;
            margin-top: 0.65rem;
            color: #F8FBFF;
            font-size: 0.95rem;
            font-weight: 600;
        }

        .dashboard-progress-subline span {
            color: rgba(193, 232, 255, 0.84);
            font-size: 0.84rem;
            font-weight: 500;
        }

        .dashboard-progress-track-shell {
            position: relative;
            width: 100%;
            height: 0.95rem;
            margin-top: 0.95rem;
            border-radius: 999px;
            background: rgba(193, 232, 255, 0.12);
            overflow: hidden;
        }

        .dashboard-progress-track-fill {
            position: relative;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #7EE0FF 0%, #92BFFF 38%, #F8FBFF 100%);
            box-shadow: 0 0 18px rgba(126, 224, 255, 0.45);
        }

        .dashboard-progress-track-fill::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(120deg, rgba(255, 255, 255, 0) 15%, rgba(255, 255, 255, 0.55) 48%, rgba(255, 255, 255, 0) 85%);
            transform: translateX(-100%);
            animation: dashboard-progress-scan 2.8s linear infinite;
        }

        @keyframes dashboard-progress-scan {
            to {
                transform: translateX(100%);
            }
        }

        .dashboard-progress-message-rich {
            margin-top: 0.85rem;
            color: rgba(244, 250, 255, 0.86);
            font-size: 0.92rem;
            line-height: 1.55;
        }

        .dashboard-progress-stage-row {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.55rem;
            margin-top: 1rem;
        }

        .dashboard-stage-pill {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            min-height: 3rem;
            padding: 0.72rem 0.7rem;
            border-radius: 18px;
            border: 1px solid rgba(193, 232, 255, 0.12);
            background: rgba(255, 255, 255, 0.06);
            color: rgba(244, 250, 255, 0.72);
        }

        .dashboard-stage-pill.completed {
            background: rgba(126, 224, 255, 0.16);
            border-color: rgba(126, 224, 255, 0.34);
            color: #F8FBFF;
        }

        .dashboard-stage-pill.active {
            background: rgba(248, 251, 255, 0.16);
            border-color: rgba(248, 251, 255, 0.34);
            color: #F8FBFF;
            box-shadow: 0 0 22px rgba(248, 251, 255, 0.12);
        }

        .dashboard-stage-index {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.72rem;
            height: 1.72rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.14);
            font-size: 0.8rem;
            font-weight: 700;
            flex: 0 0 auto;
        }

        .dashboard-stage-name {
            font-size: 0.88rem;
            font-weight: 600;
            line-height: 1.25;
        }

        .dashboard-progress-stats-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.75rem;
            padding: 1rem 1.2rem 0.85rem;
        }

        .dashboard-progress-stat-card {
            min-height: 5.35rem;
            padding: 0.88rem 0.92rem;
            border-radius: 20px;
            border: 1px solid rgba(193, 232, 255, 0.16);
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(10px);
        }

        .dashboard-progress-stat-label {
            color: rgba(193, 232, 255, 0.84);
            font-size: 0.74rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .dashboard-progress-stat-value {
            margin-top: 0.48rem;
            color: #F8FBFF;
            font-size: 1rem;
            font-weight: 700;
            line-height: 1.45;
            word-break: break-word;
        }

        .dashboard-progress-runtime {
            padding: 0 1.2rem 1rem;
            color: rgba(193, 232, 255, 0.84);
            font-size: 0.86rem;
        }

        .dashboard-progress-history-shell {
            padding: 0 1.2rem 1.15rem;
        }

        .dashboard-progress-history-title {
            color: rgba(244, 250, 255, 0.92);
            font-size: 0.92rem;
            font-weight: 700;
            margin-bottom: 0.62rem;
        }

        .dashboard-progress-history-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.62rem;
        }

        .dashboard-progress-history-card {
            padding: 0.72rem 0.78rem;
            border-radius: 16px;
            border: 1px solid rgba(193, 232, 255, 0.14);
            background: rgba(255, 255, 255, 0.06);
        }

        .dashboard-progress-history-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            color: rgba(193, 232, 255, 0.8);
            font-size: 0.72rem;
        }

        .dashboard-progress-history-stage {
            margin-top: 0.45rem;
            color: #F8FBFF;
            font-size: 0.88rem;
            font-weight: 700;
        }

        .dashboard-progress-history-note {
            margin-top: 0.32rem;
            color: rgba(244, 250, 255, 0.76);
            font-size: 0.78rem;
            line-height: 1.45;
        }

        .section-card {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.97) 0%, rgba(241, 249, 255, 0.96) 100%);
            border: 1px solid var(--line);
            border-radius: 28px;
            box-shadow: var(--shadow);
            padding: 1rem 1rem 0.55rem;
            margin-bottom: 1rem;
        }

        .section-card h1,
        .section-card h2,
        .section-card h3,
        .section-card p,
        .section-card span,
        .section-card label {
            color: #021024 !important;
        }

        .section-card-title {
            margin: 0 0 0.2rem;
            font-size: 1.1rem;
            letter-spacing: -0.02em;
        }

        .section-card-note {
            margin: 0 0 0.6rem;
            color: #3b6898 !important;
            font-size: 0.92rem;
        }

        .premium-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            margin-bottom: 0.85rem;
            font-size: 0.76rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--muted);
            font-weight: 700;
        }

        .premium-kicker svg,
        .premium-pill svg,
        .sidebar-brand svg,
        .premium-stat-card svg {
            width: 1rem;
            height: 1rem;
            flex: 0 0 1rem;
        }

        .premium-title {
            margin: 0;
            font-size: clamp(2.1rem, 4vw, 4rem);
        }

        .premium-description {
            margin: 0.8rem 0 0;
            max-width: 46rem;
            color: var(--muted);
            font-size: 1rem;
        }

        .premium-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.7rem;
            margin-top: 1.15rem;
        }

        .premium-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.48rem;
            padding: 0.62rem 0.9rem;
            background: rgba(255, 255, 255, 0.62);
            border: 1px solid var(--line);
            border-radius: 999px;
            color: var(--ink);
            font-size: 0.9rem;
        }

        .sidebar-brand .premium-pill,
        .sidebar-note .premium-pill {
            background: rgba(193, 232, 255, 0.10);
            border-color: rgba(193, 232, 255, 0.16);
            color: #f4fbff;
        }

        .sidebar-brand .icon-chip,
        .sidebar-note .icon-chip {
            color: #f4fbff;
            background: rgba(193, 232, 255, 0.12);
            border-color: rgba(193, 232, 255, 0.16);
        }

        .sidebar-brand,
        .sidebar-note {
            background: linear-gradient(180deg, rgba(7, 45, 96, 0.72) 0%, rgba(2, 16, 36, 0.68) 100%);
            border: 1px solid rgba(193, 232, 255, 0.18);
            border-radius: 24px;
            padding: 1rem 1rem 1.05rem;
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
        }

        .sidebar-brand-head {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            margin-bottom: 0.7rem;
        }

        .sidebar-brand p,
        .sidebar-note p {
            margin: 0;
            color: rgba(233, 245, 255, 0.82);
            line-height: 1.55;
            font-size: 0.92rem;
        }

        .sidebar-brand-title {
            margin: 0;
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            font-size: 1.15rem;
            color: #f4fbff;
        }

        .sidebar-brand-kicker {
            font-size: 0.74rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: rgba(193, 232, 255, 0.72);
            font-weight: 700;
        }

        .sidebar-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.85rem;
        }

        .icon-chip {
            width: 2.35rem;
            height: 2.35rem;
            border-radius: 999px;
            background: rgba(84, 131, 179, 0.12);
            border: 1px solid rgba(84, 131, 179, 0.16);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--ink);
        }

        .premium-stat-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.95rem;
            margin-bottom: 0.95rem;
        }

        .premium-stat-card {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.97) 0%, rgba(233, 245, 255, 0.92) 100%);
            border: 1px solid var(--line);
            border-radius: var(--radius-lg);
            padding: 1rem 1rem 1.05rem;
            box-shadow: var(--shadow);
            overflow: hidden;
        }

        .premium-stat-top {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            color: var(--muted);
            font-size: 0.78rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .premium-stat-value {
            margin-top: 0.8rem;
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            font-size: clamp(1.7rem, 2.2vw, 2.5rem);
            letter-spacing: -0.03em;
            color: var(--ink);
        }

        .premium-stat-note {
            margin-top: 0.35rem;
            color: var(--muted);
            font-size: 0.9rem;
        }

        .premium-stat-card .icon-chip {
            background: rgba(84, 131, 179, 0.12);
            border-color: rgba(84, 131, 179, 0.16);
            color: var(--ink);
        }

        .section-label {
            margin: 0.1rem 0 0.6rem;
            color: var(--muted);
            font-size: 0.82rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .config-info-grid,
        .config-panel-grid {
            display: grid;
            gap: 0.85rem;
            margin: 0.4rem 0 1rem;
        }

        .config-info-card,
        .config-panel-card {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.97) 0%, rgba(237, 247, 255, 0.92) 100%);
            border: 1px solid rgba(84, 131, 179, 0.18);
            border-radius: 22px;
            padding: 0.95rem 1rem;
            box-shadow: 0 18px 44px rgba(2, 16, 36, 0.08);
        }

        .config-info-label,
        .config-panel-badge {
            color: var(--muted);
            font-size: 0.74rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
        }

        .config-info-value,
        .config-panel-title {
            margin-top: 0.42rem;
            color: var(--ink);
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            font-size: 1.08rem;
            font-weight: 700;
            line-height: 1.4;
            word-break: break-word;
        }

        .config-info-note,
        .config-panel-body,
        .config-panel-note {
            margin-top: 0.38rem;
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.6;
            word-break: break-word;
        }

        .config-panel-note {
            color: #4b6e94;
        }

        .diagnosis-summary-card {
            background: var(--surface-bg, var(--surface-strong));
            border: 1px solid var(--surface-line, var(--line));
            border-radius: 22px;
            box-shadow: 0 18px 44px rgba(2, 16, 36, 0.12);
            padding: 1rem 1.1rem;
            margin: 0.45rem 0 0.9rem;
        }

        .diagnosis-summary-content {
            margin: 0;
            color: var(--surface-ink, var(--ink));
            font-size: 0.98rem;
            font-weight: 600;
            line-height: 1.75;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .config-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin: 0.4rem 0 1rem;
        }

        .config-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.48rem 0.78rem;
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(84, 131, 179, 0.18);
            border-radius: 999px;
            color: #052659;
            font-size: 0.9rem;
            line-height: 1.3;
        }

        .config-panel-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.62rem;
            background: rgba(193, 232, 255, 0.56);
            border: 1px solid rgba(84, 131, 179, 0.16);
            border-radius: 999px;
        }

        @media (max-width: 1100px) {
            .premium-stat-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .dashboard-snapshot {
                grid-template-columns: 1fr;
            }

            .dashboard-progress-stage-row,
            .dashboard-progress-history-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .dashboard-progress-stats-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 720px) {
            .block-container {
                padding-top: 1rem;
                padding-bottom: 2rem;
            }

            .premium-hero,
            .sidebar-brand,
            .sidebar-note,
            .premium-stat-card {
                border-radius: 22px;
            }

            .premium-stat-grid {
                grid-template-columns: 1fr;
                gap: 0.8rem;
            }

            .dashboard-insight-grid {
                grid-template-columns: 1fr;
            }

            .dashboard-progress-heading-row,
            .dashboard-progress-subline {
                align-items: flex-start;
            }

            .dashboard-progress-heading-row {
                flex-direction: column;
            }

            .dashboard-progress-stage-row,
            .dashboard-progress-history-grid,
            .dashboard-progress-stats-grid {
                grid-template-columns: 1fr;
            }

            .premium-meta,
            .sidebar-meta {
                gap: 0.5rem;
            }

            .premium-pill {
                width: 100%;
                justify-content: flex-start;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <style>
        {streamlit_root_vars(theme)}
        {streamlit_component_overrides()}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_shell(task_count: int, task_uuid: str, api_ok: bool, api_msg: str):
    task_label = task_uuid[:8] if task_uuid else "未选择"
    api_label = "API 已连接" if api_ok else "等待 API"
    api_detail = f"健康状态: {_format_metric_value(api_msg)}" if api_ok else _format_metric_value(api_msg)
    st.sidebar.markdown(
        f"""
        <div class="sidebar-brand">
            <div class="sidebar-brand-head">
                <span class="icon-chip">{_icon_svg("dashboard")}</span>
                <div>
                    <div class="sidebar-brand-kicker">Sequencer Log Platform</div>
                    <h2 class="sidebar-brand-title">创新智造引领生命科技</h2>
                </div>
            </div>
            <p>面向日志整理、问题定位与解决方案沉淀的统一工作台。</p>
            <div class="sidebar-meta">
                <span class="premium-pill">{_icon_svg("task")} {task_count} 个历史任务</span>
                <span class="premium-pill">{_icon_svg("api")} {api_label}</span>
            </div>
        </div>
        <div class="sidebar-note">
            <p><strong>当前任务</strong>: {escape(task_label)}</p>
            <p style="margin-top:0.45rem;">{escape(api_detail)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_intro(page: str, task_uuid: str, api_ok: bool):
    meta = PAGE_META.get(page, PAGE_META["首页 / 仪表盘"])
    pills = [
        f'<span class="premium-pill">{_icon_svg("task")} {"任务 " + escape(task_uuid[:8]) if task_uuid else "未选择任务"}</span>',
        f'<span class="premium-pill">{_icon_svg("api")} {"API 正常" if api_ok else "API 待连接"}</span>',
        f'<span class="premium-pill">{_icon_svg("spark")} MGI </span>',
    ]
    st.markdown(
        f"""
        <section class="premium-hero">
            <div class="premium-kicker">{_icon_svg(meta["icon"])} Sequence Intelligence Workspace</div>
            <h1 class="premium-title">{escape(meta["title"])}</h1>
            <p class="premium-description">{escape(meta["description"])}</p>
            <div class="premium-meta">{"".join(pills)}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _stat_grid_html(cards: list[dict[str, Any]]) -> str:
    card_html = []
    for index, card in enumerate(cards):
        note = card.get("note", "")
        note_html = escape(str(note)) if note else "&nbsp;"
        card_html.append(
            _html_block(
                f"""
                <article class="premium-stat-card">
                    <div class="premium-stat-top">
                        <span class="icon-chip">{_icon_svg(str(card.get("icon", "spark")))}</span>
                        <span>{escape(str(card.get("label", "")))}</span>
                    </div>
                    <div class="premium-stat-value">{escape(_format_metric_value(card.get("value")))}</div>
                    <div class="premium-stat-note">{note_html}</div>
                </article>
                """
            )
        )
    return f'<div class="premium-stat-grid">{"".join(card_html)}</div>'


def render_stat_cards(cards: list[dict[str, Any]]):
    st.markdown(_stat_grid_html(cards), unsafe_allow_html=True)


def render_dashboard_summary(title: str, subtitle: str, primary_cards: list[dict[str, Any]]):
    html = "".join(
        [
            '<section class="dashboard-hero">',
            f'<h1 class="dashboard-title">{escape(title)}</h1>',
            f'<p class="dashboard-subtitle">{escape(subtitle)}</p>',
            _stat_grid_html(primary_cards),
            '<div class="dashboard-divider"></div>',
            "</section>",
        ]
    )
    st.markdown(html, unsafe_allow_html=True)


def render_dashboard_snapshot(progress_percent: Any, stage: str, message: str, insight_cards: list[dict[str, Any]]):
    try:
        progress_value = max(0, min(100, int(float(progress_percent or 0))))
    except (TypeError, ValueError):
        progress_value = 0

    insight_html = []
    for index, card in enumerate(insight_cards):
        tone = str(card.get("tone") or DEFAULT_BADGE_TONES[index % len(DEFAULT_BADGE_TONES)])
        style_attr = escape(_style_vars(_tone_vars(tone)))
        insight_html.append(
            _html_block(
                f"""
                <article class="dashboard-insight-card" style="{style_attr}">
                    <div class="dashboard-insight-label">{escape(str(card.get("label", "")))}</div>
                    <div class="dashboard-insight-value">{escape(_format_metric_value(card.get("value")))}</div>
                </article>
                """
            )
        )

    stage_text = stage or "等待状态同步"
    message_text = message or "首页保留概览和问题定位信息，详细性能数据收纳到折叠区。"
    html = "".join(
        [
            '<section class="dashboard-snapshot">',
            '<div class="dashboard-progress-shell">',
            '<div class="dashboard-progress-meta">',
            '<span class="dashboard-progress-label">当前分析进度</span>',
            f'<strong class="dashboard-progress-value">{progress_value}%</strong>',
            "</div>",
            '<div class="dashboard-progress-track">',
            f'<span style="width: {progress_value}%"></span>',
            "</div>",
            f'<p class="dashboard-progress-stage">{escape(stage_text)}</p>',
            f'<p class="dashboard-progress-message">{escape(message_text)}</p>',
            "</div>",
            f'<div class="dashboard-insight-grid">{"".join(insight_html)}</div>',
            "</section>",
        ]
    )
    st.markdown(html, unsafe_allow_html=True)


def render_homepage_performance_summary(perf_summary: JsonDict, status: JsonDict):
    stage_timings = cast(JsonDict, perf_summary.get("stage_timings", {})) if isinstance(perf_summary, dict) else {}
    throughput = cast(JsonDict, perf_summary.get("throughput", {})) if isinstance(perf_summary, dict) else {}
    tuning = cast(JsonDict, perf_summary.get("tuning", {})) if isinstance(perf_summary, dict) else {}
    recommendations = perf_summary.get("recommendations", []) if isinstance(perf_summary, dict) else []
    cpu_cores = perf_summary.get("cpu_cores") or status.get("cpu_cores") or "-"
    total_seconds = stage_timings.get("total_seconds") or status.get("elapsed_seconds") or "-"
    parse_seconds = stage_timings.get("parse_seconds") or stage_timings.get("prescan_seconds") or "-"
    aggregate_seconds = stage_timings.get("aggregate_seconds") or stage_timings.get("normalize_merge_seconds") or "-"

    st.markdown("#### 处理概况")
    render_stat_cards(
        [
            {"icon": "settings", "label": "CPU 核心数", "value": cpu_cores, "note": "本次任务使用的并行核心数", "tone": "#E7EFF8"},
            {"icon": "clock", "label": "总耗时(秒)", "value": total_seconds, "note": "端到端处理耗时", "tone": "#DCEBFA"},
            {"icon": "stream", "label": "解析阶段(秒)", "value": parse_seconds, "note": "文件解析与预扫描耗时", "tone": "#0B5CAD"},
            {"icon": "dashboard", "label": "聚合阶段(秒)", "value": aggregate_seconds, "note": "聚合与归并阶段耗时", "tone": "#F3E1A6"},
        ]
    )
    if throughput:
        st.markdown("#### 吞吐指标")
        render_stat_cards(
            [
                {"icon": "stream", "label": "总体 lines/s", "value": throughput.get("overall_lines_per_sec") or throughput.get("lines_per_sec"), "note": "全流程吞吐", "tone": "#0B5CAD"},
                {"icon": "settings", "label": "解析 lines/s", "value": throughput.get("parse_lines_per_sec"), "note": "仅解析阶段吞吐", "tone": "#E7EFF8"},
                {"icon": "file", "label": "files/s", "value": throughput.get("files_per_sec"), "note": "文件处理吞吐", "tone": "#DCEBFA"},
                {"icon": "dashboard", "label": "dispatch/s", "value": throughput.get("dispatch_units_per_sec"), "note": "任务切片调度吞吐", "tone": "#F3E1A6"},
            ]
        )
    if tuning:
        st.markdown("#### 任务调优参数")
        st.json(tuning)
    if recommendations:
        st.markdown("#### 优化建议")
        for item in recommendations:
            st.caption(f"- {item}")


def _parse_iso_text(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        try:
            converted = to_pydatetime()
            if isinstance(converted, datetime):
                return converted
        except Exception:
            pass
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _format_duration_text(seconds: Any) -> str:
    try:
        total_seconds = float(seconds)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(total_seconds) or total_seconds < 0:
        return "-"
    if total_seconds < 1:
        return f"{total_seconds:.2f}s"
    days, remainder = divmod(int(round(total_seconds)), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts[:3])


def _format_datetime_text(value: Any) -> str:
    dt = _parse_iso_text(value)
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _display_datetime_text(value: Any, fallback: str = "-") -> str:
    formatted = _format_datetime_text(value)
    if formatted != "-":
        return formatted
    text = str(value or "").strip()
    return text or fallback


def _format_mb_or_gb(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(amount) or amount < 0:
        return "-"
    if amount >= 1024:
        return f"{amount / 1024:.2f} GB"
    if amount >= 100:
        return f"{amount:.0f} MB"
    return f"{amount:.1f} MB"


def _format_gb_text(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(amount) or amount < 0:
        return "-"
    if amount >= 100:
        return f"{amount:.0f} GB"
    if amount >= 10:
        return f"{amount:.1f} GB"
    return f"{amount:.2f} GB"


def _format_percent_text(value: Any) -> str:
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(percent) or percent < 0:
        return "-"
    return f"{percent:.1f}%"


def _env_sort_key(item: JsonDict) -> tuple[int, int, str]:
    key = str(item.get("key") or "")
    if key in ADMIN_ENV_PRIORITY_KEYS:
        return (0, ADMIN_ENV_PRIORITY_KEYS.index(key), key)
    if key.startswith("LLM_"):
        return (1, 0, key)
    if key.startswith("SYSTEM_"):
        return (2, 0, key)
    return (3, 0, key)


def _env_lookup(items: list[JsonDict], key: str) -> JsonDict:
    for item in items:
        if str(item.get("key") or "") == key:
            return item
    return {}


def render_system_pressure_summary(runtime_snapshot: JsonDict) -> None:
    cpu = cast(JsonDict, runtime_snapshot.get("cpu") or {})
    memory = cast(JsonDict, runtime_snapshot.get("memory") or {})
    disk = cast(JsonDict, runtime_snapshot.get("disk") or {})
    guard = cast(JsonDict, runtime_snapshot.get("guard") or {})
    policy = cast(JsonDict, runtime_snapshot.get("policy") or {})
    blocked = bool(guard.get("blocked"))

    st.markdown("#### 当前计算压力")
    render_stat_cards(
        [
            {
                "icon": "settings",
                "label": "CPU 使用率",
                "value": _format_percent_text(cpu.get("percent")),
                "note": f"逻辑核 {cpu.get('logical_cores') or '-'} / 物理核 {cpu.get('physical_cores') or '-'}",
                "tone": "#D96B3B" if blocked else "#052659",
            },
            {
                "icon": "dashboard",
                "label": "内存使用率",
                "value": _format_percent_text(memory.get("percent")),
                "note": f"已用 {_format_mb_or_gb(memory.get('used_mb'))} / 总计 {_format_mb_or_gb(memory.get('total_mb'))}",
                "tone": "#DCEBFA",
            },
            {
                "icon": "stream",
                "label": "可用内存",
                "value": _format_mb_or_gb(memory.get("available_mb")),
                "note": f"保留阈值 {policy.get('memory_soft_reserve_mb') or '-'} MB",
                "tone": "#E7EFF8",
            },
            {
                "icon": "file",
                "label": "磁盘空闲",
                "value": _format_gb_text(disk.get("free_gb")),
                "note": f"数据目录占用 {_format_percent_text(disk.get('percent'))}",
                "tone": "#F3E1A6",
            },
            {
                "icon": "alert",
                "label": "新任务调度",
                "value": "延迟派发" if blocked else "允许派发",
                "note": f"CPU 软阈值 {policy.get('cpu_soft_limit_percent') or '-'}% / 内存软阈值 {policy.get('memory_soft_limit_percent') or '-'}%",
                "tone": "#D96B3B" if blocked else "#0B5CAD",
            },
        ]
    )
    if blocked:
        st.warning(str(guard.get("summary") or "当前资源压力较高，新任务会延迟调度。"))
    else:
        st.caption(str(guard.get("summary") or "当前资源状态正常。"))
    st.caption(f"采样时间: {_format_datetime_text(runtime_snapshot.get('collected_at'))}")


def _render_upload_perf_controls(*, key_prefix: str) -> JsonDict:
    cpu_cap = max(1, os.cpu_count() or 4)
    with st.expander("Performance tuning", expanded=False):
        st.caption("These options apply to the current upload task only.")
        c1, c2 = st.columns(2, gap="medium")
        max_workers = c1.number_input(
            "Max workers",
            min_value=1,
            max_value=cpu_cap,
            value=min(32, cpu_cap),
            step=1,
            key=f"{key_prefix}_max_workers",
        )
        file_level_workers = c2.number_input(
            "File-level workers",
            min_value=1,
            max_value=cpu_cap,
            value=min(16, cpu_cap),
            step=1,
            key=f"{key_prefix}_file_level_workers",
        )
        c3, c4 = st.columns(2, gap="medium")
        chunk_size_mb = c3.number_input(
            "Chunk size (MB)",
            min_value=1,
            max_value=1024,
            value=16,
            step=1,
            key=f"{key_prefix}_chunk_size_mb",
        )
        db_batch_size = c4.number_input(
            "DB batch size",
            min_value=100,
            max_value=200000,
            value=5000,
            step=100,
            key=f"{key_prefix}_db_batch_size",
        )
        c5, c6 = st.columns(2, gap="medium")
        max_parse_chunks_per_file = c5.number_input(
            "Max chunks / file",
            min_value=1,
            max_value=256,
            value=64,
            step=1,
            key=f"{key_prefix}_max_parse_chunks_per_file",
        )
        enable_process_pool = c6.checkbox(
            "Enable process pool",
            value=True,
            key=f"{key_prefix}_enable_process_pool",
        )
        enable_streaming_parse = st.checkbox(
            "Enable chunked streaming parse",
            value=True,
            key=f"{key_prefix}_enable_streaming_parse",
        )

    return {
        "max_workers": int(max_workers),
        "file_level_workers": min(int(file_level_workers), int(max_workers)),
        "streaming_parse_chunk_bytes": int(chunk_size_mb) * 1024 * 1024,
        "max_parse_chunks_per_file": int(max_parse_chunks_per_file),
        "db_batch_size": int(db_batch_size),
        "enable_process_pool": str(bool(enable_process_pool)).lower(),
        "enable_streaming_parse": str(bool(enable_streaming_parse)).lower(),
    }


def render_dashboard_upload_panel(*, panel_key: str = "dashboard") -> None:
    default_cpu_cores = min(32, max(1, os.cpu_count() or 4))
    st.markdown("#### 文件上传")
    st.caption("上传入口已并入仪表盘，前端不再额外限制业务上传大小。")
    with st.form(f"{panel_key}_upload_form"):
        uploaded = st.file_uploader(
            "支持多文件与压缩包上传(zip / 7z / tar)",
            accept_multiple_files=True,
            key=f"{panel_key}_file_uploader",
            help="如仍遇到 Streamlit 上传限制，请同步调整 server.maxUploadSize。",
        )
        cpu_cores = st.number_input(
            "并行处理 CPU 核心数",
            min_value=1,
            max_value=max(1, os.cpu_count() or 4),
            value=default_cpu_cores,
            step=1,
            key=f"{panel_key}_cpu_cores",
        )
        perf_controls = _render_upload_perf_controls(key_prefix=f"{panel_key}_upload")
        submitted = st.form_submit_button("开始批量分析并上传", use_container_width=True)

    if not submitted:
        return
    if not uploaded:
        st.warning("请先选择至少一个文件。")
        return

    with st.spinner("正在上传并提交后台任务，请勿重复点击..."):
        files_payload = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in uploaded]
        ok, result = api_post("/tasks/upload", files=files_payload, data={"cpu_cores": int(cpu_cores), **perf_controls})
    if ok:
        st.session_state["latest_task_uuid"] = result.get("task_uuid", "")
        st.session_state["dashboard_upload_notice"] = result.get("message") or "任务已提交。"
        clear_cached_api_get()
        st.rerun()
    else:
        st.error(result)


def render_admin_env_config_panel(llm_cfg: JsonDict) -> None:
    st.markdown("#### Env 配置")
    st.caption("仅管理员可编辑。修改会直接写入项目根目录 `.env`，后续接口读取将使用新值。")

    ok_env, env_payload = api_get("/config/env", live=True)
    if not ok_env:
        st.error(env_payload)
        return
    ok_runtime, runtime_payload = api_get("/system/runtime", live=True)
    items = sorted(
        [cast(JsonDict, row) for row in cast(list[Any], env_payload.get("items") or []) if isinstance(row, dict)],
        key=_env_sort_key,
    )
    if not items:
        st.info("当前未读取到可编辑的 env 项。")
        return

    llm_enabled_item = _env_lookup(items, "LLM_ENABLED")
    llm_base_url_item = _env_lookup(items, "LLM_BASE_URL")
    llm_api_key_item = _env_lookup(items, "LLM_API_KEY")
    llm_model_item = _env_lookup(items, "LLM_MODEL")
    render_info_tiles(
        [
            {
                "label": "LLM 调用状态",
                "value": llm_enabled_item.get("display_value") if llm_enabled_item else llm_cfg.get("enabled"),
                "note": "对应 `LLM_ENABLED`，用于控制是否真正触发大模型调用",
            },
            {
                "label": "LLM URL",
                "value": llm_base_url_item.get("value") if llm_base_url_item else llm_cfg.get("base_url"),
                "note": "对应 `LLM_BASE_URL`",
            },
            {
                "label": "LLM API Key",
                "value": llm_api_key_item.get("display_value") if llm_api_key_item else "",
                "note": "对应 `LLM_API_KEY`，敏感字段以掩码展示",
            },
            {
                "label": "LLM 模型",
                "value": llm_model_item.get("value") if llm_model_item else llm_cfg.get("model"),
                "note": "对应 `LLM_MODEL`",
            },
            {
                "label": "Env 总项数",
                "value": len(items),
                "note": "支持在下方搜索、编辑和恢复默认值",
            },
            {
                "label": "运行时状态",
                "value": "资源健康" if ok_runtime and not bool((runtime_payload.get("guard") or {}).get("blocked")) else "存在压力",
                "note": "用于辅助判断 LLM 与任务并发是否受资源影响",
            },
        ],
        columns=3,
    )

    if ok_runtime and isinstance(runtime_payload, dict):
        with st.expander("查看当前运行时资源状态", expanded=False):
            render_system_pressure_summary(cast(JsonDict, runtime_payload))

    search_text = st.text_input("搜索 env 键", key="admin_env_search", placeholder="例如 LLM_ / SYSTEM_ / SMTP_")
    filtered_items = [
        item for item in items
        if not search_text or search_text.lower() in str(item.get("key") or "").lower()
    ]
    if not filtered_items:
        st.info("没有匹配的 env 键。")
        return

    picked_key = st.selectbox(
        "选择要编辑的 env 键",
        [str(item.get("key") or "") for item in filtered_items],
        key="admin_env_selected_key",
    )
    selected_item = next(item for item in filtered_items if str(item.get("key") or "") == picked_key)

    render_info_tiles(
        [
            {"label": "当前值", "value": selected_item.get("display_value") if selected_item.get("is_sensitive") else selected_item.get("value")},
            {"label": "默认值", "value": selected_item.get("default_display_value") if selected_item.get("is_sensitive") else selected_item.get("default_value")},
            {"label": "已偏离默认", "value": selected_item.get("is_modified"), "note": "可通过恢复默认快速回滚"},
        ],
        columns=3,
    )

    with st.form(f"admin_env_edit_form::{picked_key}"):
        if bool(selected_item.get("is_sensitive")):
            edited_value = st.text_input("新的值", value=str(selected_item.get("value") or ""), type="password")
        else:
            edited_value = st.text_area("新的值", value=str(selected_item.get("value") or ""), height=120)
        save_clicked = st.form_submit_button("保存当前 env 项", type="primary")
        reset_clicked = st.form_submit_button("恢复默认值", disabled=not bool(selected_item.get("has_default")))

    if save_clicked:
        ok_save, save_resp = api_put(f"/config/env/{picked_key}", {"value": edited_value})
        if ok_save:
            st.success(f"{picked_key} 已更新。")
            clear_cached_api_get()
            st.rerun()
        else:
            st.error(save_resp)
    if reset_clicked:
        ok_reset, reset_resp = api_post(f"/config/env/{picked_key}/reset", json={}, timeout=30)
        if ok_reset:
            st.success(f"{picked_key} 已恢复默认值。")
            clear_cached_api_get()
            st.rerun()
        else:
            st.error(reset_resp)

    safe_dataframe(
        [
            {
                "key": item.get("key"),
                "current_value": item.get("display_value") if item.get("is_sensitive") else item.get("value"),
                "default_value": item.get("default_display_value") if item.get("is_sensitive") else item.get("default_value"),
                "is_modified": item.get("is_modified"),
                "is_sensitive": item.get("is_sensitive"),
            }
            for item in filtered_items
        ],
        use_container_width=True,
        height=320,
        key="admin_env_items_table",
    )


def _is_task_active(status: JsonDict) -> bool:
    return str(status.get("status") or "").lower() in {"uploaded", "queued", "processing"}


def _streamlit_version_tuple() -> tuple[int, ...]:
    raw_version = str(getattr(st, "__version__", "") or "").strip()
    parts: list[int] = []
    for piece in raw_version.split("."):
        match = re.match(r"(\d+)", piece)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts)


def _use_fragment_progress_refresh() -> bool:
    env_value = str(os.getenv("STREAMLIT_ENABLE_FRAGMENT_PROGRESS", "")).strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False
    return _streamlit_version_tuple() >= (1, 41, 0)


def _render_dashboard_progress_card_content(task_uuid: str, status: JsonDict) -> None:
    progress_value = max(0, min(100, int(status.get("progress_percent") or 0)))
    runtime_snapshot = status.get("runtime_snapshot") if isinstance(status.get("runtime_snapshot"), dict) else {}
    history = status.get("progress_history") if isinstance(status.get("progress_history"), list) else []
    file_label = status.get("filename") or task_uuid
    current_stage = status.get("current_stage") or "-"
    elapsed_seconds = status.get("elapsed_seconds")
    eta_seconds = status.get("estimated_remaining_seconds")
    finish_at = status.get("estimated_finish_at")

    st.markdown("#### 实时文件处理进度")
    left, right = st.columns([1.35, 1.0], gap="large")
    with left:
        st.caption(f"任务 / 文件: {file_label}")
        st.progress(progress_value)
        stage_cols = st.columns(2, gap="medium")
        stage_cols[0].metric("当前阶段", current_stage)
        stage_cols[1].metric("处理状态", status.get("status", "-"))
        if status.get("message"):
            st.caption(str(status.get("message")))
    with right:
        metric_cols = st.columns(2, gap="small")
        metric_cols[0].metric("已用时间", _format_duration_text(elapsed_seconds))
        metric_cols[1].metric("预计剩余", _format_duration_text(eta_seconds))
        metric_cols = st.columns(2, gap="small")
        metric_cols[0].metric("预计结束", _format_datetime_text(finish_at))
        metric_cols[1].metric("进度", f"{progress_value}%")
        cpu_percent = ((runtime_snapshot.get("cpu") or {}).get("percent")) if runtime_snapshot else None
        mem_percent = ((runtime_snapshot.get("memory") or {}).get("percent")) if runtime_snapshot else None
        if cpu_percent is not None or mem_percent is not None:
            st.caption(
                f"Runtime snapshot: CPU {cpu_percent if cpu_percent is not None else '-'}% | "
                f"Memory {mem_percent if mem_percent is not None else '-'}%"
            )

    if history:
        history_rows = []
        for row in reversed(history[-10:]):
            history_rows.append(
                {
                    "时间": _format_datetime_text(row.get("timestamp")),
                    "阶段": row.get("current_stage") or "-",
                    "状态": row.get("status") or "-",
                    "进度": f"{int(row.get('progress_percent') or 0)}%",
                    "说明": row.get("message") or "",
                }
            )
        with st.expander("处理历史", expanded=not _is_task_active(status)):
            safe_dataframe(pd.DataFrame(history_rows), use_container_width=True, height=240)


def _normalize_progress_stage(status: JsonDict) -> str:
    raw_stage = str(status.get("current_stage") or "").strip().lower()
    runtime_status = str(status.get("status") or "").strip().lower()
    progress_value = max(0, min(100, int(status.get("progress_percent") or 0)))

    if runtime_status == "completed" or progress_value >= 100:
        return "completed"

    for stage_key, meta in PROGRESS_STAGE_META.items():
        if stage_key == "completed":
            continue
        aliases = cast(tuple[str, ...], meta.get("aliases") or ())
        if any(alias in raw_stage for alias in aliases):
            return stage_key

    if runtime_status in {"uploaded", "queued"} or progress_value < 20:
        return "uploaded"
    if progress_value < 68:
        return "parsing"
    if progress_value < 84:
        return "summary"
    return "postprocess"


def _progress_stage_label(stage_key: str) -> str:
    meta = PROGRESS_STAGE_META.get(stage_key) or {}
    return str(meta.get("label") or stage_key or "-")


def _compact_stage_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return re.sub(r"[_\s]+", " ", text)


def _detect_active_file_label(task_uuid: str, status: JsonDict) -> str:
    fallback = str(status.get("filename") or task_uuid or "-").strip() or "-"
    message = str(status.get("message") or "").strip()
    if not message:
        return fallback

    explicit_patterns = [
        r"checking archive/file:\s*(?P<name>.+)$",
        r"^(?P<name>.+?)\s*\[[^\]]+\]$",
        r"^(?P<name>.+?)\s+retried serially$",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            value = str(match.group("name") or "").strip(" .")
            if value:
                return value

    file_match = re.search(r"([^\s\\/:*?\"<>|]+?\.(?:csv|log|txt|zip|7z|tar|jsonl?|gz|tsv|xlsx?))", message, re.IGNORECASE)
    if file_match:
        value = str(file_match.group(1) or "").strip()
        if value:
            return value
    return fallback


def _render_dashboard_progress_card_content(task_uuid: str, status: JsonDict) -> None:
    progress_value = max(0, min(100, int(status.get("progress_percent") or 0)))
    runtime_snapshot = status.get("runtime_snapshot") if isinstance(status.get("runtime_snapshot"), dict) else {}
    history = status.get("progress_history") if isinstance(status.get("progress_history"), list) else []
    current_stage_key = _normalize_progress_stage(status)
    current_stage_label = _progress_stage_label(current_stage_key)
    current_stage = _compact_stage_text(status.get("current_stage"))
    active_file = _detect_active_file_label(task_uuid, status)
    elapsed_seconds = status.get("elapsed_seconds")
    eta_seconds = status.get("estimated_remaining_seconds")
    started_at = status.get("started_at") or status.get("created_at")
    finished_at = status.get("finished_at")
    finish_at = status.get("estimated_finish_at")
    status_text = str(status.get("status") or "-").strip() or "-"
    message_text = str(status.get("message") or "").strip() or "系统正在持续刷新任务状态。"
    cpu_percent = ((runtime_snapshot.get("cpu") or {}).get("percent")) if runtime_snapshot else None
    mem_percent = ((runtime_snapshot.get("memory") or {}).get("percent")) if runtime_snapshot else None

    stage_items: list[str] = []
    active_index = PROGRESS_STAGE_FLOW.index(current_stage_key) if current_stage_key in PROGRESS_STAGE_FLOW else 0
    for index, stage_key in enumerate(PROGRESS_STAGE_FLOW):
        state = "pending"
        if index < active_index:
            state = "completed"
        elif stage_key == current_stage_key:
            state = "active"
        stage_items.append(
            _html_block(
                f"""
                <div class="dashboard-stage-pill {state}">
                    <span class="dashboard-stage-index">{index + 1}</span>
                    <span class="dashboard-stage-name">{escape(_progress_stage_label(stage_key))}</span>
                </div>
                """
            )
        )

    metric_cards = [
        ("当前处理文件名", active_file),
        ("当前处理阶段", current_stage_label),
        ("已用时间", _format_duration_text(elapsed_seconds)),
        ("预计剩余时间", _format_duration_text(eta_seconds)),
        ("预计结束时间", _format_datetime_text(finish_at)),
        ("任务状态", status_text),
    ]
    metric_cards = [
        ("任务状态", status_text),
        ("当前阶段", current_stage_label),
        ("开始时间", _format_datetime_text(started_at)),
        ("预计结束时间", _format_datetime_text(finish_at if _is_task_active(status) else (finished_at or finish_at))),
        ("实际用时", _format_duration_text(elapsed_seconds)),
        ("预计剩余时间", _format_duration_text(eta_seconds)),
    ]
    metric_html = "".join(
        _html_block(
            f"""
            <article class="dashboard-progress-stat-card">
                <div class="dashboard-progress-stat-label">{escape(label)}</div>
                <div class="dashboard-progress-stat-value">{escape(value)}</div>
            </article>
            """
        )
        for label, value in metric_cards
    )

    history_html = ""
    if history:
        history_items: list[str] = []
        for row in reversed(history[-5:]):
            row_payload = cast(JsonDict, row if isinstance(row, dict) else {})
            row_stage = _progress_stage_label(_normalize_progress_stage(row_payload))
            history_items.append(
                _html_block(
                    f"""
                    <article class="dashboard-progress-history-card">
                        <div class="dashboard-progress-history-top">
                            <span>{escape(_format_datetime_text(row_payload.get("timestamp")))}</span>
                            <strong>{escape(f"{int(row_payload.get('progress_percent') or 0)}%")}</strong>
                        </div>
                        <div class="dashboard-progress-history-stage">{escape(row_stage)}</div>
                        <div class="dashboard-progress-history-note">{escape(_compact_stage_text(row_payload.get("message") or row_payload.get("current_stage") or "-"))}</div>
                    </article>
                    """
                )
            )
        history_html = (
            '<div class="dashboard-progress-history-shell">'
            '<div class="dashboard-progress-history-title">最近处理轨迹</div>'
            f'<div class="dashboard-progress-history-grid">{"".join(history_items)}</div>'
            "</div>"
        )

    runtime_caption = ""
    if cpu_percent is not None or mem_percent is not None:
        runtime_caption = (
            f"CPU {cpu_percent if cpu_percent is not None else '-'}% · "
            f"Memory {mem_percent if mem_percent is not None else '-'}%"
        )

    html = "".join(
        [
            '<section class="dashboard-progress-panel">',
            '<div class="dashboard-progress-hero">',
            '<div class="dashboard-progress-topline">实时文件处理进度</div>',
            '<div class="dashboard-progress-heading-row">',
            f'<div class="dashboard-progress-heading">{escape(active_file)}</div>',
            f'<div class="dashboard-progress-badge">{progress_value}%</div>',
            "</div>",
            f'<div class="dashboard-progress-subline">阶段：{escape(current_stage_label)}<span>{escape(current_stage)}</span></div>',
            '<div class="dashboard-progress-track-shell">',
            f'<div class="dashboard-progress-track-fill" style="width: {progress_value}%"></div>',
            "</div>",
            f'<div class="dashboard-progress-message-rich">{escape(message_text)}</div>',
            f'<div class="dashboard-progress-stage-row">{"".join(stage_items)}</div>',
            "</div>",
            f'<div class="dashboard-progress-stats-grid">{metric_html}</div>',
            f'<div class="dashboard-progress-runtime">{escape(runtime_caption or "等待资源状态快照...")}</div>',
            history_html,
            "</section>",
        ]
    )
    st.markdown("#### 实时文件处理进度")
    st.markdown(html, unsafe_allow_html=True)


def render_dashboard_progress_card(task_uuid: str, status: JsonDict) -> None:
    refresh_seconds = max(2, int(os.getenv("STREAMLIT_PROGRESS_REFRESH_SECONDS", "3")))
    auto_refresh_key = f"dashboard_progress_auto::{task_uuid}"
    st.session_state[auto_refresh_key] = _is_task_active(status)
    fragment_fn = getattr(st, "fragment", None)
    allow_fragment_refresh = callable(fragment_fn) and _use_fragment_progress_refresh()

    if allow_fragment_refresh:
        @fragment_fn(run_every=refresh_seconds if st.session_state.get(auto_refresh_key) else None)
        def _fragment() -> None:
            ok_live, live_status = api_get(f"/tasks/{task_uuid}/status", live=True)
            payload = live_status if ok_live and isinstance(live_status, dict) else status
            active_now = _is_task_active(payload)
            if st.session_state.get(auto_refresh_key) != active_now:
                st.session_state[auto_refresh_key] = active_now
                st.rerun()
            _render_dashboard_progress_card_content(task_uuid, cast(JsonDict, payload))

        _fragment()
        return

    payload = status
    if _is_task_active(status):
        ok_live, live_status = api_get(f"/tasks/{task_uuid}/status", live=True)
        if ok_live and isinstance(live_status, dict):
            payload = cast(JsonDict, live_status)

    _render_dashboard_progress_card_content(task_uuid, payload)
    if _is_task_active(payload) and not allow_fragment_refresh:
        st.caption(
            "Auto refresh is disabled on this Streamlit version to avoid fragment DOM errors. "
            "Use the refresh button while the task is running."
        )
    if st.button("刷新进度", key=f"progress_refresh::{task_uuid}"):
        clear_cached_api_get()
        st.rerun()


def _api_base() -> str:
    return st.session_state.get("api_base", DEFAULT_API_BASE)


def _request_api_get(path: str, params_json: str = "") -> Any:
    params = json.loads(params_json) if params_json else {}
    resp = requests.get(f"{_api_base()}{path}", params=params, headers=_auth_headers(), timeout=120)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner=False, ttl=15)
def cached_api_get(path: str, params_json: str = "") -> Any:
    return _request_api_get(path, params_json)


def clear_cached_api_get() -> None:
    cast(Any, cached_api_get).clear()


def api_get(path: str, live: bool = False, **params: Any) -> tuple[bool, Any]:
    try:
        params = {**_ACTIVE_SCOPE_PARAMS, **params}
        key = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
        return True, (_request_api_get(path, key) if live else cached_api_get(path, key))
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        return False, f"GET {path} 失败: HTTP {exc.response.status_code} | {detail}"
    except Exception as exc:
        return False, f"GET {path} 失败: {exc}"


def _query_params_for_link(params: dict[str, Any] | None = None) -> str:
    cleaned: dict[str, str] = {}
    for key, value in (params or {}).items():
        if value in (None, "", [], ()):
            continue
        if isinstance(value, (list, tuple, set)):
            text = ",".join(str(item) for item in value if item not in (None, ""))
            if not text:
                continue
            cleaned[key] = text
        else:
            cleaned[key] = str(value)
    token = str(st.session_state.get("auth_token") or "").strip()
    if token:
        cleaned["access_token"] = token
    return urlencode(cleaned, doseq=False)


def _scope_catalog(task_uuid: str) -> dict[str, Any]:
    ok, payload = api_get(f"/tasks/{task_uuid}/scope-catalog")
    if ok and isinstance(payload, dict):
        return payload
    return {}


def render_scope_filter_panel(task_uuid: str, key_prefix: str) -> dict[str, Any]:
    global _ACTIVE_SCOPE_PARAMS
    catalog = _scope_catalog(task_uuid)
    sides = [item for item in catalog.get("sides", []) if isinstance(item, dict)]
    chips = [item for item in catalog.get("chips", []) if isinstance(item, dict)]
    if not sides and not chips:
        st.caption("当前任务尚未识别到可用的运行边位或芯片，将按整机显示。")
        return {}

    side_value_to_label = {str(item.get("value")): str(item.get("label") or item.get("value") or "") for item in sides}
    chip_value_to_label = {str(item.get("value")): str(item.get("label") or item.get("value") or "") for item in chips}
    side_values = list(side_value_to_label.keys())
    chip_values = list(chip_value_to_label.keys())
    side_default = [value for value in side_values if value != "__UNASSIGNED__"] or side_values
    chip_default = [value for value in chip_values if value != "__UNASSIGNED__"] or chip_values

    st.markdown("### 运行范围筛选")
    mode = st.radio(
        "选择查看范围",
        ["whole", "side", "chip"],
        horizontal=True,
        key=f"{key_prefix}_scope_mode",
        format_func=lambda value: {"whole": "整机", "side": "按边位", "chip": "按芯片"}.get(value, value),
    )

    params: dict[str, Any] = {}
    c1, c2 = st.columns([1.3, 2.7], gap="medium")
    with c1:
        instrument_scope = catalog.get("instrument_scope") or "Whole Instrument"
        st.caption(f"Instrument: {instrument_scope}")
        st.caption(f"已识别 {len(side_values)} 个边位 / {len(chip_values)} 个芯片")
    with c2:
        if mode == "side":
            selected_sides = st.multiselect(
                "边位多选",
                side_values,
                default=st.session_state.get(f"{key_prefix}_side_values", side_default),
                key=f"{key_prefix}_side_values",
                format_func=lambda value: side_value_to_label.get(str(value), str(value)),
            )
            if selected_sides:
                params["side_scope"] = ",".join(str(value) for value in selected_sides)
        elif mode == "chip":
            selected_chips = st.multiselect(
                "芯片多选",
                chip_values,
                default=st.session_state.get(f"{key_prefix}_chip_values", chip_default),
                key=f"{key_prefix}_chip_values",
                format_func=lambda value: chip_value_to_label.get(str(value), str(value)),
            )
            if selected_chips:
                params["chip_name"] = ",".join(str(value) for value in selected_chips)
        else:
            st.caption("整机模式下将同时显示全部边位和芯片。")
    st.session_state[f"{key_prefix}_scope_params"] = params
    _ACTIVE_SCOPE_PARAMS = dict(params)
    return params


def _auth_headers(headers: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(headers or {})
    token = str(st.session_state.get("auth_token") or "").strip()
    if token:
        merged["Authorization"] = f"Bearer {token}"
    return merged


def _auth_query_suffix() -> str:
    token = str(st.session_state.get("auth_token") or "").strip()
    return f"&access_token={token}" if token else ""


def api_post(path: str, timeout: int = 180, **kwargs: Any) -> tuple[bool, Any]:
    try:
        kwargs["headers"] = _auth_headers(kwargs.get("headers"))
        resp = requests.post(f"{_api_base()}{path}", timeout=timeout, **kwargs)
        resp.raise_for_status()
        clear_cached_api_get()
        return True, resp.json()
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        return False, f"POST {path} 失败: HTTP {exc.response.status_code} | {detail}"
    except Exception as exc:
        return False, f"POST {path} 失败: {exc}"


def api_put(path: str, payload: JsonDict) -> tuple[bool, Any]:
    try:
        resp = requests.put(f"{_api_base()}{path}", json=payload, headers=_auth_headers(), timeout=120)
        resp.raise_for_status()
        clear_cached_api_get()
        return True, resp.json()
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        return False, f"PUT {path} 失败: HTTP {exc.response.status_code} | {detail}"
    except Exception as exc:
        return False, f"PUT {path} 失败: {exc}"


def api_delete(path: str) -> tuple[bool, Any]:
    try:
        resp = requests.delete(f"{_api_base()}{path}", headers=_auth_headers(), timeout=120)
        resp.raise_for_status()
        clear_cached_api_get()
        return True, resp.json() if resp.text else {"success": True}
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        return False, f"DELETE {path} 失败: HTTP {exc.response.status_code} | {detail}"
    except Exception as exc:
        return False, f"DELETE {path} 失败: {exc}"


def check_api_health() -> tuple[bool, str]:
    try:
        resp = requests.get(f"{_api_base()}/health", timeout=5)
        resp.raise_for_status()
        return True, resp.json().get("status", "ok")
    except Exception as exc:
        return False, str(exc)


def post_review_action(path: str, review_status: str, reviewer: str | None = None, notes: str | None = None, extra_payload: dict | None = None):
    payload = {"review_status": review_status, "reviewer": reviewer, "notes": notes}
    if extra_payload:
        payload.update(extra_payload)
    return api_post(path, json=payload, timeout=60)


def render_review_actions(entity_label: str, review_path: str, *, reviewer_key: str, notes_key: str, extra_payload: dict | None = None):
    reviewer = st.text_input(f"{entity_label} reviewer", key=reviewer_key)
    notes = st.text_area(f"{entity_label} review notes", key=notes_key, height=80)
    c1, c2, c3, c4 = st.columns(4)
    actions = [(c1, "提交审核", "submitted_for_review"), (c2, "批准", "approved"), (c3, "驳回", "rejected"), (c4, "忽略", "ignored")]
    for col, label, status in actions:
        if col.button(label, key=f"{review_path}_{status}"):
            ok, resp = post_review_action(review_path, status, reviewer=reviewer or None, notes=notes or None, extra_payload=extra_payload)
            if ok:
                st.success(f"已更新为 {status}")
                clear_cached_api_get()
                st.rerun()
            else:
                st.error(resp)


def _safe_cell(value: Any):
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text and ("T" in text or text.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", text)):
            parsed = _parse_iso_text(text)
            if parsed is not None:
                return _display_datetime_text(parsed, fallback=value)
        return value
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _display_datetime_text(value)
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)
    return str(value)


def _auto_widget_key(prefix: str) -> str:
    frame = inspect.currentframe()
    caller = frame.f_back.f_back if frame and frame.f_back and frame.f_back.f_back else None
    signature = f"{prefix}:unknown"
    if caller is not None:
        signature = f"{prefix}:{caller.f_code.co_filename}:{caller.f_lineno}"
    count = _SAFE_DATAFRAME_CALL_COUNTS.get(signature, 0) + 1
    _SAFE_DATAFRAME_CALL_COUNTS[signature] = count
    return f"{prefix}:{hashlib.sha1(f'{signature}:{count}'.encode('utf-8')).hexdigest()[:12]}"


def _apply_dataframe_filters(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df

    filtered = df
    if len(df) <= 2000:
        with st.expander("表格工具", expanded=False):
            search_col, field_col, value_col = st.columns([1.35, 1.0, 1.05], gap="small")
            search_text = str(search_col.text_input("搜索", key=f"{key}::search", placeholder="全文搜索当前表格")).strip()
            column_options = ["全部列"] + [str(col) for col in df.columns]
            filter_column = str(field_col.selectbox("筛选列", column_options, key=f"{key}::filter_col"))
            filter_value = str(value_col.text_input("筛选值", key=f"{key}::filter_value", placeholder="按列包含匹配")).strip()

        if search_text:
            search_mask = pd.Series(False, index=filtered.index)
            for column in filtered.columns:
                series = filtered[column].astype(str)
                search_mask = search_mask | series.str.contains(re.escape(search_text), case=False, na=False)
            filtered = filtered.loc[search_mask]

        if filter_column != "全部列" and filter_value:
            filtered = filtered.loc[
                filtered[filter_column].astype(str).str.contains(re.escape(filter_value), case=False, na=False)
            ]

    st.caption(f"显示 {len(filtered):,} / {len(df):,} 行，支持列头排序、滚动、搜索和按列过滤。")
    return filtered


def safe_dataframe(data, *, use_container_width=True, height=None, key: str | None = None, enable_toolbar: bool = True):
    try:
        df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data).copy()
    except Exception:
        st.code(str(data))
        return
    for col in df.columns:
        try:
            df[col] = df[col].map(_safe_cell)
        except Exception:
            df[col] = df[col].astype(str)
    widget_key = key or _auto_widget_key("df")
    view_df = _apply_dataframe_filters(df, widget_key) if enable_toolbar else df
    st.dataframe(view_df, use_container_width=use_container_width, height=height, hide_index=True)


def safe_json(data):
    try:
        st.json(json.loads(json.dumps(data, ensure_ascii=False, default=str)))
    except Exception:
        st.code(str(data))


def _has_display_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _display_config_value(
    value: Any,
    empty_text: str = "未配置",
    *,
    true_text: str = "已启用",
    false_text: str = "未启用",
) -> str:
    if not _has_display_value(value):
        return empty_text
    if isinstance(value, bool):
        return true_text if value else false_text
    if isinstance(value, (int, float)):
        return _format_metric_value(value)
    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value if _has_display_value(item)]
        if not items:
            return empty_text
        if len(items) > 4:
            return f"{'、'.join(items[:4])} 等 {len(items)} 项"
        return "、".join(items)
    if isinstance(value, dict):
        return f"{len(value)} 项"
    return str(value)


def _preview_config_text(value: Any, *, limit: int = 220, empty_text: str = "暂无说明") -> str:
    if not _has_display_value(value):
        return empty_text
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _rows_from_mapping(mapping: Any, key_field: str, value_field: str) -> list[dict[str, Any]]:
    if not isinstance(mapping, dict):
        return []
    return [{key_field: key, value_field: value} for key, value in mapping.items()]


def _rows_from_nested_mapping(mapping: Any, group_field: str, key_field: str, value_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(mapping, dict):
        return rows
    for group_name, child_mapping in mapping.items():
        if not isinstance(child_mapping, dict):
            continue
        for item_name, value in child_mapping.items():
            rows.append({group_field: group_name, key_field: item_name, value_field: value})
    return rows


def _editor_rows_to_records(rows: Any) -> list[dict[str, Any]]:
    def _normalize_records(records: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not isinstance(records, list):
            return normalized
        for record in records:
            if not isinstance(record, dict):
                continue
            normalized.append({str(key): value for key, value in record.items()})
        return normalized

    if isinstance(rows, pd.DataFrame):
        return _normalize_records(rows.to_dict(orient="records"))
    if isinstance(rows, list):
        return _normalize_records(rows)
    try:
        return _normalize_records(pd.DataFrame(rows).to_dict(orient="records"))
    except Exception:
        return []


def _coerce_numeric_value(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    if numeric.is_integer():
        return int(numeric)
    return round(numeric, 4)


def _mapping_from_editor_rows(rows: Any, key_field: str, value_field: str) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for row in _editor_rows_to_records(rows):
        key = str(row.get(key_field) or "").strip()
        value = _coerce_numeric_value(row.get(value_field))
        if not key or value is None:
            continue
        result[key] = value
    return result


def _nested_mapping_from_editor_rows(rows: Any, group_field: str, key_field: str, value_field: str) -> dict[str, dict[str, int | float]]:
    result: dict[str, dict[str, int | float]] = {}
    for row in _editor_rows_to_records(rows):
        group_name = str(row.get(group_field) or "").strip()
        key = str(row.get(key_field) or "").strip()
        value = _coerce_numeric_value(row.get(value_field))
        if not group_name or not key or value is None:
            continue
        result.setdefault(group_name, {})[key] = value
    return result


def render_info_tiles(items: list[dict[str, Any]], *, columns: int = 3):
    visible_items = [item for item in items if item.get("show_empty") or _has_display_value(item.get("value"))]
    if not visible_items:
        st.info("暂无可展示的配置项。")
        return

    cards: list[str] = []
    column_count = max(1, min(columns, 4))
    for item in visible_items:
        value_text = _display_config_value(
            item.get("value"),
            item.get("empty_text", "未配置"),
            true_text=item.get("true_text", "已启用"),
            false_text=item.get("false_text", "未启用"),
        )
        note_html = ""
        if item.get("note"):
            note_html = f'<div class="config-info-note">{escape(_preview_config_text(item.get("note"), limit=160, empty_text=""))}</div>'
        cards.append(
            _html_block(
                f"""
                <article class="config-info-card">
                    <div class="config-info-label">{escape(str(item.get("label", "")))}</div>
                    <div class="config-info-value">{escape(value_text)}</div>
                    {note_html}
                </article>
                """
            )
        )
    st.markdown(
        f'<div class="config-info-grid" style="grid-template-columns: repeat({column_count}, minmax(0, 1fr));">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def render_tag_cloud(values: Any, *, empty_text: str = "暂无标签"):
    tags = [str(item).strip() for item in (values or []) if _has_display_value(item)]
    if not tags:
        tags = [empty_text]
    tag_html = "".join(f'<span class="config-chip">{escape(tag)}</span>' for tag in tags)
    st.markdown(f'<div class="config-chip-row">{tag_html}</div>', unsafe_allow_html=True)


def render_text_panels(items: list[dict[str, Any]], *, columns: int = 2):
    visible_items = [item for item in items if item.get("show_empty") or _has_display_value(item.get("body")) or _has_display_value(item.get("title"))]
    if not visible_items:
        st.info("暂无说明内容。")
        return

    panels: list[str] = []
    column_count = max(1, min(columns, 4))
    for item in visible_items:
        badge = item.get("badge")
        badge_html = f'<div class="config-panel-badge">{escape(str(badge))}</div>' if _has_display_value(badge) else ""
        note = item.get("note")
        note_html = f'<div class="config-panel-note">{escape(_preview_config_text(note, limit=260, empty_text=""))}</div>' if _has_display_value(note) else ""
        panels.append(
            _html_block(
                f"""
                <article class="config-panel-card">
                    {badge_html}
                    <div class="config-panel-title">{escape(str(item.get("title", "")))}</div>
                    <div class="config-panel-body">{escape(_preview_config_text(item.get("body"), limit=320))}</div>
                    {note_html}
                </article>
                """
            )
        )
    st.markdown(
        f'<div class="config-panel-grid" style="grid-template-columns: repeat({column_count}, minmax(0, 1fr));">{"".join(panels)}</div>',
        unsafe_allow_html=True,
    )


def enrich_error_family_frame(data) -> pd.DataFrame:
    try:
        df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data).copy()
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    raw_family = df["error_family"].fillna("unknown").astype(str) if "error_family" in df.columns else pd.Series(["unknown"] * len(df), index=df.index)
    if "error_family_display" in df.columns:
        df["error_family_display"] = df["error_family_display"].fillna(raw_family).astype(str)
    else:
        df["error_family_display"] = raw_family
    if "error_family_description" in df.columns:
        df["error_family_description"] = df["error_family_description"].fillna("").astype(str)
    else:
        df["error_family_description"] = ""
    return df


def _chart_theme(mode: str | None) -> dict[str, str]:
    theme = get_design_tokens(mode)
    chart_surface = "#FFFFFF" if theme.name == "light" else theme.surface_strong
    return {
        "template": "plotly_dark" if theme.name == "dark" else "plotly_white",
        "paper_bgcolor": chart_surface,
        "plot_bgcolor": chart_surface,
        "hover_bgcolor": theme.surface_solid,
        "map_style": "carto-darkmatter" if theme.name == "dark" else "carto-positron",
    }


def _axis_values_from_traces(fig, axis_name: str) -> list[Any]:
    values: list[Any] = []
    for trace in fig.data:
        trace_axis = str(getattr(trace, f"{axis_name}axis", None) or axis_name)
        if trace_axis != axis_name:
            continue
        raw_values = getattr(trace, axis_name, None)
        if raw_values is None:
            continue
        if isinstance(raw_values, (str, bytes)):
            values.append(raw_values)
            continue
        try:
            values.extend(list(raw_values))
        except TypeError:
            values.append(raw_values)
    return [value for value in values if value is not None and not (isinstance(value, float) and math.isnan(value))]


def _category_axis_labels(values: list[Any]) -> list[str]:
    labels: list[str] = []
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text and text not in labels:
            labels.append(text)
    return labels


def _apply_axis_density(fig, *, theme, height: int | None) -> None:
    chart_height = height or 460
    x_values = _axis_values_from_traces(fig, "x")
    y_values = _axis_values_from_traces(fig, "y")
    x_axis = getattr(fig.layout, "xaxis", None)
    y_axis = getattr(fig.layout, "yaxis", None)

    if x_axis is not None:
        x_type = str(getattr(x_axis, "type", "") or "").lower()
        x_labels = _category_axis_labels(x_values)
        if x_type == "date":
            fig.update_xaxes(
                nticks=max(5, min(12, math.ceil(chart_height / 52))),
                tickformatstops=[
                    dict(dtickrange=[None, 1000], value="%H:%M:%S.%L"),
                    dict(dtickrange=[1000, 60000], value="%H:%M:%S"),
                    dict(dtickrange=[60000, 3600000], value="%H:%M"),
                    dict(dtickrange=[3600000, 86400000], value="%m-%d %H:%M"),
                    dict(dtickrange=[86400000, None], value="%Y-%m-%d"),
                ],
            )
        elif x_labels:
            max_labels = 10
            tick_step = max(1, math.ceil(len(x_labels) / max_labels))
            longest_label = max(len(label) for label in x_labels)
            tick_angle = -45 if longest_label > 16 or len(x_labels) > max_labels else (-25 if longest_label > 9 else 0)
            fig.update_xaxes(
                ticklabelstep=tick_step,
                tickangle=tick_angle,
                tickfont=dict(color=theme.ink, size=11 if tick_step > 1 else 12),
            )
        else:
            fig.update_xaxes(nticks=max(5, min(11, math.ceil(chart_height / 58))))

    if y_axis is not None:
        y_type = str(getattr(y_axis, "type", "") or "").lower()
        y_labels = _category_axis_labels(y_values)
        if y_type == "category" or y_labels:
            max_labels = max(5, min(22, math.floor(chart_height / 28)))
            tick_step = max(1, math.ceil(len(y_labels) / max_labels)) if y_labels else 1
            longest_label = max((len(label) for label in y_labels), default=0)
            fig.update_yaxes(
                ticklabelstep=tick_step,
                tickangle=0 if longest_label <= 30 else -18,
                tickfont=dict(color=theme.ink, size=11 if tick_step > 1 else 12),
            )
        else:
            fig.update_yaxes(nticks=max(5, min(10, math.ceil(chart_height / 60))))


def render_fig(
    fig,
    key: str | None = None,
    height: int | None = None,
    title: str | None = None,
    title_outside: bool = False,
    title_x: float = 0,
    title_y: float = 0.98,
):
    theme = get_design_tokens(st.session_state.get("theme_mode", "light"))
    chart_theme = _chart_theme(st.session_state.get("theme_mode", "light"))
    plotly_template = chart_theme["template"]
    plot_area_bg = chart_theme["plot_bgcolor"]
    paper_bg = chart_theme["paper_bgcolor"]
    title_text = _clean_chart_title(title if title is not None else getattr(getattr(fig.layout, "title", None), "text", None))
    wrapped_title_lines = _wrap_chart_title(title_text) if title_text else []
    if wrapped_title_lines and title_outside:
        st.markdown(f'<div class="chart-frame-title">{"<br>".join(escape(line) for line in wrapped_title_lines)}</div>', unsafe_allow_html=True)
        fig.update_layout(title_text="")
    elif wrapped_title_lines:
        fig.update_layout(title="<br>".join(wrapped_title_lines))
    else:
        fig.update_layout(title_text="")

    legend_entries = 0
    for trace in fig.data:
        if getattr(trace, "showlegend", True) is False:
            continue
        trace_type = str(getattr(trace, "type", "") or "")
        labels = getattr(trace, "labels", None)
        if trace_type in {"pie", "sunburst", "treemap", "funnelarea"} and labels is not None:
            legend_entries += len({str(label) for label in labels if str(label).strip()})
        elif str(getattr(trace, "name", "") or "").strip():
            legend_entries += 1
        elif len(fig.data) > 1:
            legend_entries += 1

    legend_rows = min(3, math.ceil(legend_entries / 4)) if legend_entries else 0
    top_margin = 30 + (len(wrapped_title_lines) * 28 if wrapped_title_lines and not title_outside else 0) + (legend_rows * 22 if legend_rows else 0)
    fig.update_layout(
        autosize=True,
        height=height,
        template=plotly_template,
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_area_bg,
        colorway=PLOTLY_COLOR_SEQUENCE,
        font=dict(family='"Avenir Next", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif', color=theme.ink, size=13),
        title=dict(text="<br>".join(wrapped_title_lines) if wrapped_title_lines and not title_outside else "", font=dict(family='"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif', size=22, color=theme.accent), x=title_x, xanchor="left", y=title_y, yanchor="top", pad=dict(b=18)),
        title_automargin=True,
        margin=dict(l=12, r=18, t=top_margin, b=28),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            title_text="",
            font=dict(color=theme.ink),
            itemclick="toggle",
            itemdoubleclick="toggleothers",
        ),
        uniformtext=dict(minsize=10, mode="hide"),
        hoverlabel=dict(bgcolor=chart_theme["hover_bgcolor"], bordercolor=theme.accent_soft, font=dict(color=theme.ink)),
        hovermode="closest",
        dragmode="pan",
        modebar=dict(bgcolor="rgba(0,0,0,0)", color=theme.ink_muted if hasattr(theme, "ink_muted") else theme.ink, activecolor=theme.accent),
    )
    fig.update_layout(
        polar=dict(
            bgcolor=plot_area_bg,
            radialaxis=dict(gridcolor=theme.line, linecolor=theme.line_strong, tickfont=dict(color=theme.ink)),
            angularaxis=dict(gridcolor=theme.line, linecolor=theme.line_strong, tickfont=dict(color=theme.ink)),
        ),
        ternary=dict(
            bgcolor=plot_area_bg,
            aaxis=dict(gridcolor=theme.line, linecolor=theme.line_strong, tickfont=dict(color=theme.ink)),
            baxis=dict(gridcolor=theme.line, linecolor=theme.line_strong, tickfont=dict(color=theme.ink)),
            caxis=dict(gridcolor=theme.line, linecolor=theme.line_strong, tickfont=dict(color=theme.ink)),
        ),
        geo=dict(
            bgcolor=plot_area_bg,
            lakecolor=plot_area_bg,
            landcolor=plot_area_bg,
            showlakes=False,
            showland=False,
        ),
        mapbox=dict(style=chart_theme["map_style"]),
    )
    fig.update_annotations(font=dict(color=theme.ink))
    fig.update_xaxes(
        automargin=True,
        title_standoff=14,
        gridcolor=theme.line,
        linecolor=theme.line_strong,
        zeroline=False,
        tickfont=dict(color=theme.ink),
        title_font=dict(color=theme.ink),
        fixedrange=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
    )
    fig.update_yaxes(
        automargin=True,
        title_standoff=14,
        gridcolor=theme.line,
        linecolor=theme.line_strong,
        zeroline=False,
        tickfont=dict(color=theme.ink),
        title_font=dict(color=theme.ink),
        fixedrange=False,
    )
    _apply_axis_density(fig, theme=theme, height=height)
    for trace in fig.data:
        trace_type = str(getattr(trace, "type", "") or "")
        if trace_type in {"pie", "sunburst", "treemap", "funnelarea"}:
            marker_colors = getattr(getattr(trace, "marker", None), "colors", None)
            color_values = list(marker_colors) if marker_colors is not None and not isinstance(marker_colors, str) else []
            if not color_values:
                labels = getattr(trace, "labels", None)
                label_count = len(labels) if labels is not None else 1
                color_values = [PLOTLY_COLOR_SEQUENCE[index % len(PLOTLY_COLOR_SEQUENCE)] for index in range(max(1, label_count))]
            inside_text_colors = [_pick_contrast_text(_normalize_color_hex(color) or theme.accent) for color in color_values]
            trace.update(
                textfont=dict(color=theme.ink),
                insidetextfont=dict(color=inside_text_colors),
                outsidetextfont=dict(color=theme.ink),
            )
        else:
            trace.update(textfont=dict(color=theme.ink))
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=key,
        config={
            "responsive": True,
            "displayModeBar": "hover",
            "displaylogo": False,
            "scrollZoom": True,
            "doubleClick": "reset+autosize",
        },
    )


def _resolve_low_value_reference(df: pd.DataFrame, preference: str) -> tuple[str | None, float | None]:
    expected_value = None
    threshold_value = None
    if "expected_value" in df.columns:
        expected_series = pd.to_numeric(df["expected_value"], errors="coerce").dropna()
        if not expected_series.empty:
            expected_value = float(expected_series.iloc[0])
    if "threshold_value" in df.columns:
        threshold_series = pd.to_numeric(df["threshold_value"], errors="coerce").dropna()
        if not threshold_series.empty:
            threshold_value = float(threshold_series.iloc[0])

    if preference == "优先阈值":
        if threshold_value is not None:
            return "阈值", threshold_value
        if expected_value is not None:
            return "期望值", expected_value
        return None, None

    if expected_value is not None:
        return "期望值", expected_value
    if threshold_value is not None:
        return "阈值", threshold_value
    return None, None


def build_parameter_trend_figure(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    series_col: str = "series_name",
    x_sort_col: str = "x_axis_sort_value",
    low_value_preference: str,
    highlight_low_points: bool,
    hide_low_points: bool,
) -> tuple[go.Figure | None, dict[str, Any]]:
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    if x_sort_col in plot_df.columns:
        plot_df[x_sort_col] = pd.to_numeric(plot_df[x_sort_col], errors="coerce")
    else:
        plot_df[x_sort_col] = plot_df.reset_index().index.astype(float)
    if series_col not in plot_df.columns:
        plot_df[series_col] = "Default"
    plot_df = _dropna_frame(plot_df, x_col, y_col)
    if plot_df.empty:
        return None, {"hidden_low_count": 0, "low_reference_label": None, "low_reference_value": None}
    plot_df[x_col] = plot_df[x_col].astype(str)

    agg_map: dict[str, Any] = {
        y_col: "mean",
    }
    for field in ["threshold_value", "expected_value", "duration_unit", "time_epoch_ms"]:
        if field in plot_df.columns:
            agg_map[field] = "first"
    plot_df = (
        plot_df.sort_values(by=[x_sort_col, series_col, x_col], na_position="last")
        .groupby([series_col, x_sort_col, x_col], dropna=False, as_index=False)
        .agg(agg_map)
    )

    low_reference_label, low_reference_value = _resolve_low_value_reference(plot_df, low_value_preference)
    hidden_low_count = 0
    if hide_low_points and low_reference_value is not None:
        original_count = len(plot_df)
        plot_df = plot_df[plot_df[y_col] >= low_reference_value].copy()
        hidden_low_count = max(0, original_count - len(plot_df))
        if plot_df.empty:
            return None, {
                "hidden_low_count": hidden_low_count,
                "low_reference_label": low_reference_label,
                "low_reference_value": low_reference_value,
            }

    fig = go.Figure()
    unique_series = plot_df[series_col].nunique(dropna=False)
    tick_df = plot_df[[x_sort_col, x_col]].drop_duplicates().sort_values(by=x_sort_col, na_position="last")
    tick_vals = tick_df[x_sort_col].tolist()
    tick_text = tick_df[x_col].tolist()
    if len(tick_vals) > 14:
        step = max(1, math.ceil(len(tick_vals) / 14))
        tick_vals = tick_vals[::step]
        tick_text = tick_text[::step]

    for index, (series_name, series_df) in enumerate(plot_df.groupby(series_col, dropna=False, sort=False)):
        marker_colors = None
        if highlight_low_points and low_reference_value is not None:
            marker_colors = ["#D94841" if value < low_reference_value else PLOTLY_COLOR_SEQUENCE[index % len(PLOTLY_COLOR_SEQUENCE)] for value in series_df[y_col].tolist()]
        duration_unit_values = series_df[["duration_unit"]].fillna("").to_numpy() if "duration_unit" in series_df.columns else None
        fig.add_trace(
            go.Scatter(
                x=series_df[x_sort_col],
                y=series_df[y_col],
                mode="lines+markers",
                name=str(series_name or "Default"),
                line=dict(color=PLOTLY_COLOR_SEQUENCE[index % len(PLOTLY_COLOR_SEQUENCE)], width=2.5),
                marker=dict(
                    size=9,
                    color=marker_colors or PLOTLY_COLOR_SEQUENCE[index % len(PLOTLY_COLOR_SEQUENCE)],
                    line=dict(color="white", width=0.8),
                ),
                customdata=duration_unit_values,
                hovertemplate="%{text}<br>%{y:.4f}%{customdata[0]}<extra>%{fullData.name}</extra>" if "duration_unit" in series_df.columns else "%{text}<br>%{y:.4f}<extra>%{fullData.name}</extra>",
                text=series_df[x_col],
                showlegend=unique_series > 1,
            )
        )

    if "threshold_value" in plot_df.columns:
        threshold_series = pd.to_numeric(plot_df["threshold_value"], errors="coerce").dropna()
        if not threshold_series.empty:
            fig.add_hline(y=float(threshold_series.iloc[0]), line_dash="dash", line_color="#D94841")
    if "expected_value" in plot_df.columns:
        expected_series = pd.to_numeric(plot_df["expected_value"], errors="coerce").dropna()
        if not expected_series.empty:
            fig.add_hline(y=float(expected_series.iloc[0]), line_dash="dot", line_color="#1E8E6A")

    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_text,
        type="linear",
    )

    return fig, {
        "hidden_low_count": hidden_low_count,
        "low_reference_label": low_reference_label,
        "low_reference_value": low_reference_value,
    }


def render_substep_cycle_facets(df: pd.DataFrame, value_col: str = "duration_value", facet_wrap: int = 2, key: str | None = None):
    if "cycle_no" not in df.columns and "cycle" in df.columns:
        df = df.copy()
        df["cycle_no"] = df["cycle"]
    required_cols = {"cycle_no", "sub_step", value_col}
    missing = required_cols - set(df.columns)
    if missing:
        st.warning(f"无法绘制分面图，缺少字段: {', '.join(sorted(missing))}")
        return
    plot_df = _dropna_frame(df[["cycle_no", "sub_step", value_col]].copy(), "cycle_no", "sub_step", value_col)
    if plot_df.empty:
        st.info("当前筛选条件下没有可用于绘制 Substep-Cycle 趋势图的数据。")
        return
    plot_df["cycle_no"] = pd.to_numeric(plot_df["cycle_no"], errors="coerce")
    plot_df[value_col] = pd.to_numeric(plot_df[value_col], errors="coerce")
    plot_df = _dropna_frame(plot_df, "cycle_no", value_col).sort_values(by=["sub_step", "cycle_no"])
    top_substeps_df = (
        plot_df.groupby("sub_step", as_index=False)
        .agg(**{value_col: (value_col, "mean")})
        .sort_values(by=value_col, ascending=False)
        .head(12)
    )
    top_substeps = top_substeps_df["sub_step"].tolist()
    plot_df = plot_df[plot_df["sub_step"].isin(top_substeps)]
    fig = px.line(plot_df, x="cycle_no", y=value_col, color="sub_step", markers=True)
    render_fig(fig, key=key, height=480, title="Substep-Cycle 趋势", title_x=0.02, title_y=0.965)


def _timeline_base_track(value: Any) -> str:
    return re.sub(r"\s+\|\s+lane\s+\d+$", "", str(value or "").strip(), flags=re.IGNORECASE)


def _timeline_lane_index(value: Any) -> int:
    match = re.search(r"\|\s+lane\s+(\d+)$", str(value or "").strip(), re.IGNORECASE)
    return int(match.group(1)) if match else 1


def _stable_timeline_color(value: Any) -> str:
    text = str(value or "").strip() or "timeline"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return TIMELINE_COLOR_SEQUENCE[int(digest[:8], 16) % len(TIMELINE_COLOR_SEQUENCE)]


def _build_timeline_track_order(df: pd.DataFrame, order_mode: str) -> list[str]:
    if df.empty:
        return []
    sort_columns = ["start", "component_display", "sub_step", "track"]
    if order_mode == "cycle":
        sort_columns = ["cycle_no", "component_display", "track_lane", "start", "sub_step", "track"]
    order_df = df.sort_values(sort_columns, na_position="last").copy()
    return list(dict.fromkeys(order_df["track"].astype(str).tolist()))


def _align_timeline_error_tracks(timeline_df: pd.DataFrame, error_df: pd.DataFrame) -> pd.DataFrame:
    if timeline_df.empty or error_df.empty:
        return error_df

    candidates = timeline_df[["track", "base_track", "component_display", "cycle_no", "start", "end"]].copy()
    aligned_tracks: list[str] = []
    for row in error_df.itertuples(index=False):
        same_cycle = candidates[
            (candidates["component_display"].astype(str) == str(getattr(row, "component_display", "")))
            & (candidates["cycle_no"].fillna(-1) == (getattr(row, "cycle_no", None) if getattr(row, "cycle_no", None) is not None else -1))
        ]
        if same_cycle.empty:
            same_cycle = candidates[candidates["base_track"].astype(str) == str(getattr(row, "base_track", ""))]
        if same_cycle.empty:
            aligned_tracks.append(str(getattr(row, "track", "") or ""))
            continue

        hit = same_cycle[(same_cycle["start"] <= row.time) & (same_cycle["end"] >= row.time)]
        if not hit.empty:
            aligned_tracks.append(str(hit.sort_values(["start", "track"]).iloc[0]["track"]))
            continue

        distances = same_cycle.copy()
        distances["_distance"] = distances.apply(
            lambda item: min(abs((item["start"] - row.time).total_seconds()), abs((item["end"] - row.time).total_seconds())),
            axis=1,
        )
        aligned_tracks.append(str(distances.sort_values(["_distance", "start", "track"]).iloc[0]["track"]))

    output = error_df.copy()
    output["track"] = aligned_tracks
    return output


def build_movement_timeline_figure(df: pd.DataFrame, error_df: pd.DataFrame, *, order_mode: str, show_error_points: bool):
    working_df = df.copy()
    working_df["component_display"] = working_df["component"].fillna("未知组件").astype(str)
    working_df["track"] = working_df["track"].fillna("未知轨道").astype(str)
    working_df["base_track"] = working_df["track"].map(_timeline_base_track)
    working_df["track_lane"] = working_df["track"].map(_timeline_lane_index)
    working_df = working_df.sort_values(["cycle_no", "component_display", "track_lane", "start", "end"], na_position="last")
    track_order = _build_timeline_track_order(working_df, order_mode)

    fig = px.timeline(
        working_df,
        x_start="start",
        x_end="end",
        y="track",
        color="component_display",
        category_orders={"track": track_order},
        custom_data=["component_display", "sub_step", "cycle_no", "start_time_sec", "end_time_sec", "duration_ms", "message", "track"],
    )
    fig.update_traces(
        selector=dict(type="bar"),
        opacity=0.92,
        marker_line_width=1,
        marker_line_color="rgba(255,255,255,0.32)",
        hovertemplate=(
            "组件: %{customdata[0]}<br>"
            "子步骤: %{customdata[1]}<br>"
            "Cycle: %{customdata[2]}<br>"
            "开始: %{customdata[3]}<br>"
            "结束: %{customdata[4]}<br>"
            "时长(ms): %{customdata[5]}<br>"
            "轨道: %{customdata[7]}<br>"
            "说明: %{customdata[6]}<extra></extra>"
        ),
    )
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(track_order)), autorange="reversed")
    fig.update_layout(legend_title_text="", bargap=0.24)

    error_output = error_df.copy()
    if show_error_points and not error_output.empty:
        error_output["component_display"] = error_output["component"].fillna("未知组件").astype(str)
        error_output["base_track"] = error_output["track"].map(_timeline_base_track)
        error_output = _align_timeline_error_tracks(working_df, error_output)
        for severity_value, severity_group in error_output.groupby("severity", dropna=False):
            severity_text = str(severity_value or "unknown")
            fig.add_trace(
                go.Scatter(
                    x=severity_group["time"],
                    y=severity_group["track"],
                    mode="markers",
                    name=f"错误点 · {severity_text}",
                    marker={
                        "size": 11,
                        "symbol": "diamond",
                        "color": ERROR_SEVERITY_COLORS.get(severity_text.lower(), ERROR_SEVERITY_COLORS["unknown"]),
                        "line": {"width": 1, "color": "#FFFFFF"},
                    },
                    customdata=severity_group[["time_text", "normalized_signature", "error_family_display", "severity", "component_display", "message", "track"]].to_numpy(),
                    hovertemplate=(
                        "时间: %{customdata[0]}<br>"
                        "错误签名: %{customdata[1]}<br>"
                        "错误家族: %{customdata[2]}<br>"
                        "严重级别: %{customdata[3]}<br>"
                        "组件: %{customdata[4]}<br>"
                        "轨道: %{customdata[6]}<br>"
                        "消息: %{customdata[5]}<extra></extra>"
                    ),
                )
            )
    return fig, error_output, track_order


def build_movement_timeline_figure(df: pd.DataFrame, error_df: pd.DataFrame, *, order_mode: str, show_error_points: bool):
    working_df = df.copy()
    working_df["component_display"] = working_df.get("component", pd.Series(dtype=object)).fillna("未知组件").astype(str)
    render_side_series = working_df.get("render_side_scope", pd.Series(index=working_df.index, dtype=object)).replace("", pd.NA)
    raw_side_series = working_df.get("side_scope", pd.Series(index=working_df.index, dtype=object)).replace("", pd.NA)
    working_df["side_display"] = render_side_series.fillna(raw_side_series).fillna("Unassigned").astype(str)
    working_df["chip_display"] = working_df.get("chip_name", pd.Series(dtype=object)).fillna("Unassigned").astype(str)
    working_df["track"] = working_df["track"].fillna("未知轨道").astype(str)
    working_df["base_track"] = working_df["track"].map(_timeline_base_track)
    working_df["track_lane"] = working_df["track"].map(_timeline_lane_index)
    working_df["chuck_no"] = working_df.get("chuck_no", pd.Series(dtype=object)).fillna("").astype(str)
    working_df["source_file"] = working_df.get("source_file", pd.Series(dtype=object)).fillna("").astype(str)
    working_df["timeline_color_key"] = working_df["side_display"] + " | " + working_df["component_display"]
    working_df = working_df.sort_values(["cycle_no", "side_display", "component_display", "track_lane", "start", "end"], na_position="last")
    track_order = _build_timeline_track_order(working_df, order_mode)
    color_map = {
        key: _stable_timeline_color(key)
        for key in working_df["timeline_color_key"].dropna().astype(str).unique().tolist()
    }

    fig = px.timeline(
        working_df,
        x_start="start",
        x_end="end",
        y="track",
        color="timeline_color_key",
        color_discrete_map=color_map,
        category_orders={"track": track_order},
        custom_data=[
            "component_display",
            "side_display",
            "chip_display",
            "sub_step",
            "cycle_no",
            "start_time_sec",
            "end_time_sec",
            "duration_ms",
            "chuck_no",
            "source_file",
            "message",
            "track",
        ],
    )
    fig.update_traces(
        selector=dict(type="bar"),
        opacity=0.92,
        marker_line_width=1,
        marker_line_color="rgba(255,255,255,0.32)",
        hovertemplate=(
            "组件: %{customdata[0]}<br>"
            "边位: %{customdata[1]}<br>"
            "芯片: %{customdata[2]}<br>"
            "子步骤: %{customdata[3]}<br>"
            "Cycle: %{customdata[4]}<br>"
            "开始: %{customdata[5]}<br>"
            "结束: %{customdata[6]}<br>"
            "时长(ms): %{customdata[7]}<br>"
            "Chuck: %{customdata[8]}<br>"
            "Source: %{customdata[9]}<br>"
            "轨道: %{customdata[11]}<br>"
            "消息: %{customdata[10]}<extra></extra>"
        ),
    )
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(track_order)), autorange="reversed")
    fig.update_layout(legend_title_text="", bargap=0.24)

    error_output = error_df.copy()
    if show_error_points and not error_output.empty:
        error_output["component_display"] = error_output.get("component", pd.Series(dtype=object)).fillna("未知组件").astype(str)
        render_error_side_series = error_output.get("render_side_scope", pd.Series(index=error_output.index, dtype=object)).replace("", pd.NA)
        raw_error_side_series = error_output.get("side_scope", pd.Series(index=error_output.index, dtype=object)).replace("", pd.NA)
        error_output["side_display"] = render_error_side_series.fillna(raw_error_side_series).fillna("Unassigned").astype(str)
        error_output["chip_display"] = error_output.get("chip_name", pd.Series(dtype=object)).fillna("Unassigned").astype(str)
        error_output["chuck_no"] = error_output.get("chuck_no", pd.Series(dtype=object)).fillna("").astype(str)
        error_output["source_file"] = error_output.get("source_file", pd.Series(dtype=object)).fillna("").astype(str)
        error_output["base_track"] = error_output["track"].map(_timeline_base_track)
        error_output = _align_timeline_error_tracks(working_df, error_output)
        for severity_value, severity_group in error_output.groupby("severity", dropna=False):
            severity_text = str(severity_value or "unknown")
            fig.add_trace(
                go.Scatter(
                    x=severity_group["time"],
                    y=severity_group["track"],
                    mode="markers",
                    name=f"错误点 · {severity_text}",
                    marker={
                        "size": 11,
                        "symbol": "diamond",
                        "color": ERROR_SEVERITY_COLORS.get(severity_text.lower(), ERROR_SEVERITY_COLORS["unknown"]),
                        "line": {"width": 1, "color": "#FFFFFF"},
                    },
                    customdata=severity_group[
                        [
                            "time_text",
                            "normalized_signature",
                            "error_family_display",
                            "severity",
                            "component_display",
                            "side_display",
                            "chip_display",
                            "chuck_no",
                            "source_file",
                            "message",
                            "track",
                        ]
                    ].to_numpy(),
                    hovertemplate=(
                        "时间: %{customdata[0]}<br>"
                        "错误签名: %{customdata[1]}<br>"
                        "错误家族: %{customdata[2]}<br>"
                        "严重级别: %{customdata[3]}<br>"
                        "组件: %{customdata[4]}<br>"
                        "边位: %{customdata[5]}<br>"
                        "芯片: %{customdata[6]}<br>"
                        "Chuck: %{customdata[7]}<br>"
                        "Source: %{customdata[8]}<br>"
                        "轨道: %{customdata[10]}<br>"
                        "消息: %{customdata[9]}<extra></extra>"
                    ),
                )
            )
    return fig, error_output, track_order


def paged_table(path: str, *, params: dict | None = None, page_key: str, page_size_key: str, title: str, default_page_size: int = 100, max_page_size: int = 500):
    params = params or {}
    c1, c2, c3 = st.columns([1, 1, 2], gap="medium")
    page_size = c1.selectbox("每页行数", [50, 100, 200, 500], index=[50,100,200,500].index(default_page_size) if default_page_size in [50,100,200,500] else 1, key=page_size_key)
    page = c2.number_input("页码", min_value=1, value=int(st.session_state.get(page_key, 1)), step=1, key=page_key)
    params = {**params, "limit": min(int(page_size), max_page_size), "offset": (int(page) - 1) * int(page_size)}
    ok, data = api_get(path, **params)
    if not ok:
        st.error(data)
        return
    items = data.get("items", data)
    total = data.get("total", len(items))
    st.caption(f"{title}: 共 {total} 条，当前第 {page} 页")
    safe_dataframe(items, use_container_width=True, height=420)


def load_tasks_page(page: int = 1, page_size: int = 50) -> JsonDict:
    ok, data = api_get("/tasks", page=page, page_size=page_size)
    return cast(JsonDict, data) if ok and isinstance(data, dict) else {"items": [], "total": 0}


def _set_logged_in_user(token: str, user: dict[str, Any]) -> None:
    st.session_state["auth_token"] = token
    st.session_state["current_user"] = user
    clear_cached_api_get()


def _clear_login_state() -> None:
    st.session_state["auth_token"] = ""
    st.session_state["current_user"] = None
    clear_cached_api_get()


def _refresh_current_user() -> dict[str, Any] | None:
    token = str(st.session_state.get("auth_token") or "").strip()
    if not token:
        return None
    try:
        resp = requests.get(f"{_api_base()}/auth/me", headers=_auth_headers(), timeout=15)
        resp.raise_for_status()
        user = resp.json()
        st.session_state["current_user"] = user
        return user
    except Exception:
        _clear_login_state()
        return None


def render_login_portal() -> None:
    theme = get_design_tokens(str(st.session_state.get("theme_mode", "light")))
    if theme.name == "dark":
        page_background = """
                radial-gradient(circle at 15% 15%, rgba(78, 141, 255, 0.18), transparent 28%),
                radial-gradient(circle at 85% 12%, rgba(0, 215, 180, 0.12), transparent 24%),
                linear-gradient(180deg, #0b1422 0%, #121f31 42%, #0e1826 100%)
        """
        card_border = "rgba(194, 220, 255, 0.14)"
        card_background = "linear-gradient(180deg, rgba(12, 22, 35, 0.86) 0%, rgba(15, 28, 43, 0.92) 100%)"
        card_shadow = "0 28px 80px rgba(0, 0, 0, 0.34), 0 0 0 1px rgba(90, 144, 214, 0.10) inset"
        headline_color = "#f7fbff"
        subtitle_color = "rgba(226, 238, 255, 0.74)"
        chip_border = "rgba(190, 214, 255, 0.16)"
        chip_background = "rgba(18, 37, 58, 0.72)"
        chip_color = "#d8e9ff"
        form_background = "linear-gradient(180deg, rgba(11, 22, 38, 0.88) 0%, rgba(14, 28, 46, 0.94) 100%)"
        form_border = "rgba(194, 220, 255, 0.14)"
    else:
        page_background = f"""
                radial-gradient(circle at 15% 15%, {theme.page_glow_primary} 0%, transparent 30%),
                radial-gradient(circle at 85% 12%, {theme.page_glow_secondary} 0%, transparent 24%),
                linear-gradient(180deg, {theme.bg_top} 0%, {theme.bg_mid} 42%, {theme.bg_bottom} 100%)
        """
        card_border = "rgba(84, 131, 179, 0.18)"
        card_background = "linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(237, 247, 255, 0.92) 100%)"
        card_shadow = "0 28px 80px rgba(2, 16, 36, 0.12), 0 0 0 1px rgba(193, 232, 255, 0.42) inset"
        headline_color = theme.ink
        subtitle_color = theme.muted
        chip_border = "rgba(84, 131, 179, 0.18)"
        chip_background = "rgba(193, 232, 255, 0.36)"
        chip_color = theme.ink
        form_background = "linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(241, 249, 255, 0.94) 100%)"
        form_border = "rgba(84, 131, 179, 0.18)"

    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background:
                {page_background};
        }}
        .block-container {{
            max-width: 1240px;
            padding-top: 0.9rem;
            padding-bottom: 1.5rem;
        }}
        .auth-page-note {{
            color: {subtitle_color};
            font-size: 0.96rem;
            line-height: 1.65;
            margin: 0 0 0.9rem 0;
        }}
        .auth-layout-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child > div[data-testid="stVerticalBlock"] {{
            border: 1px solid {form_border};
            border-radius: 28px;
            background: {form_background};
            box-shadow: {card_shadow};
            padding: 1.15rem 1.15rem 1rem;
        }}
        .auth-shell {{
            padding: 0.15rem 0 0.75rem;
        }}
        .auth-card {{
            width: 100%;
            padding: 1.45rem 1.5rem;
            border-radius: 28px;
            border: 1px solid {card_border};
            background: {card_background};
            box-shadow: {card_shadow};
            backdrop-filter: blur(14px);
        }}
        .auth-headline {{
            color: {headline_color};
            font-size: clamp(1.6rem, 2.5vw, 2.25rem);
            font-family: "Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif;
            margin-bottom: 0.3rem;
        }}
        .auth-subtitle {{
            color: {subtitle_color};
            line-height: 1.72;
            margin-bottom: 0.95rem;
        }}
        .auth-chip-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.8rem;
            margin-bottom: 0;
        }}
        .auth-chip {{
            display: inline-flex;
            align-items: center;
            padding: 0.38rem 0.74rem;
            border-radius: 999px;
            border: 1px solid {chip_border};
            background: {chip_background};
            color: {chip_color};
            font-size: 0.84rem;
        }}
        @media (max-width: 900px) {{
            .block-container {{
                padding-top: 0.7rem;
                padding-bottom: 1.2rem;
            }}
            .auth-card {{
                padding: 1.2rem 1.1rem;
                border-radius: 24px;
            }}
            .auth-layout-anchor + div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child > div[data-testid="stVerticalBlock"] {{
                padding: 0.95rem 0.9rem 0.9rem;
                border-radius: 24px;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="auth-layout-anchor"></div>', unsafe_allow_html=True)
    hero_col, form_col = st.columns([1.02, 0.98], gap="medium")
    with hero_col:
        st.markdown(
            """
            <div class="auth-shell">
                <div class="auth-card">
                    <div class="auth-headline">Sequencer Log Platform</div>
                    <div class="auth-subtitle">统一登录、注册审核与全局方案知识库入口。如果有任何问题，请联系liuyanbo1@genomics.cn。</div>
                    <div class="auth-chip-row">
                        <span class="auth-chip">FastAPI + Streamlit</span>
                        <span class="auth-chip">角色权限</span>
                        <span class="auth-chip">Admin Review</span>
                        <span class="auth-chip">方案库索引</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<p class="auth-page-note">管理员、审核人和普通用户共用同一个登录入口。</p>', unsafe_allow_html=True)
        st.markdown("### 登录说明")
        st.markdown(
            """
            - `admin`: 用户管理、审核、方案库维护
            - `reviewer`: 方案审核、注册审核、模块与任务簇维护
            - `submitter`: 提交方案、查看授权数据、发起注册申请
            """
        )
        st.info("默认管理员首次启动后自动创建，首次登录建议立即修改密码。")

        render_announcement_feed(limit=24)

    with form_col:
        st.markdown("### 登录入口")
        login_tab, register_tab = st.tabs(["登录", "注册"])
        with login_tab:
            login_name = st.text_input("用户名或邮箱", key="auth_login_name")
            password = st.text_input("密码", type="password", key="auth_login_password")
            if st.button("登录系统", type="primary", use_container_width=True, key="auth_login_button"):
                ok, resp = api_post("/auth/login", json={"login_name": login_name, "password": password}, timeout=30)
                if ok:
                    _set_logged_in_user(str(resp.get("token") or ""), resp.get("user") or {})
                    st.success("登录成功，正在进入系统。")
                    st.rerun()
                else:
                    st.error(resp)

        with register_tab:
            username = st.text_input("用户名", key="register_username")
            email = st.text_input("邮箱", key="register_email")
            password = st.text_input("密码", type="password", key="register_password")
            confirm_password = st.text_input("确认密码", type="password", key="register_password_confirm")
            registration_note = st.text_area("注册备注（可选）", key="register_note", height=90, placeholder="可填写部门、使用场景或补充说明")

            st.caption("注册申请提交后会直接进入管理员审核，无需再做邮箱验证。")
            st.info("请填写可用邮箱并提交申请，管理员审批通过后即可使用该账号登录。")

            if st.button("提交注册申请", use_container_width=True, key="register_submit_button"):
                if password != confirm_password:
                    st.error("两次输入的密码不一致。")
                else:
                    ok, resp = api_post(
                        "/auth/register",
                        json={"username": username, "email": email, "password": password, "registration_note": registration_note},
                        timeout=30,
                    )
                    if ok:
                        st.success("注册申请已提交，等待管理员审核。")
                    else:
                        st.error(resp)

        st.markdown("### 忘记密码")
        forgot_username = st.text_input("用户名", key="forgot_username")
        forgot_email = st.text_input("邮箱", key="forgot_email")
        forgot_new_password = st.text_input("新密码", type="password", key="forgot_new_password")
        forgot_confirm_password = st.text_input("确认新密码", type="password", key="forgot_confirm_password")
        st.caption("当用户名和邮箱同时匹配时，可直接重置密码。")
        if st.button("重置密码", use_container_width=True, key="forgot_password_button"):
            if forgot_new_password != forgot_confirm_password:
                st.error("两次输入的新密码不一致。")
            else:
                ok, resp = api_post(
                    "/auth/reset-password",
                    json={
                        "username": forgot_username,
                        "email": forgot_email,
                        "new_password": forgot_new_password,
                    },
                    timeout=30,
                )
                if ok:
                    st.success("密码已重置，请使用新密码登录。")
                else:
                    st.error(resp)


def render_account_controls(current_user: dict[str, Any]) -> None:
    with st.sidebar.expander("账户", expanded=True):
        st.caption(f"用户: {current_user.get('username')} | 状态: {current_user.get('status')}")
        st.write(f"角色: {', '.join(current_user.get('roles') or [])}")
        if current_user.get("force_password_change"):
            st.warning("当前账号建议尽快修改初始密码。")
        with st.form("change_password_form", clear_on_submit=True):
            current_password = st.text_input("当前密码", type="password")
            new_password = st.text_input("新密码", type="password")
            confirm_password = st.text_input("确认新密码", type="password")
            submitted = st.form_submit_button("修改密码")
            if submitted:
                if new_password != confirm_password:
                    st.error("两次输入的新密码不一致。")
                else:
                    ok, resp = api_post("/auth/change-password", json={"current_password": current_password, "new_password": new_password}, timeout=30)
                    if ok:
                        st.session_state["current_user"] = resp.get("user")
                        st.success("密码已更新。")
                        st.rerun()
                    else:
                        st.error(resp)
        if st.button("退出登录", use_container_width=True, key="logout_button"):
            api_post("/auth/logout", json={}, timeout=15)
            _clear_login_state()
            st.rerun()

def _announcement_edit_history_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    history = item.get("edit_history")
    if not isinstance(history, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(history, start=1):
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "序号": index,
                "编辑人": str(entry.get("editor") or entry.get("updated_by") or "系统发布").strip() or "系统发布",
                "编辑时间": _display_datetime_text(entry.get("edited_at") or entry.get("updated_at") or entry.get("created_at")),
                "标题": str(entry.get("title") or "").strip(),
                "摘要": str(entry.get("summary") or "").strip(),
            }
        )
    return rows


def _announcement_last_edit_meta(item: dict[str, Any]) -> tuple[str, str, int]:
    history_rows = _announcement_edit_history_rows(item)
    if history_rows:
        latest = history_rows[-1]
        return (
            str(latest.get("编辑人") or "系统发布").strip() or "系统发布",
            str(latest.get("编辑时间") or "-").strip() or "-",
            len(history_rows),
        )
    editor = str(item.get("updated_by") or "系统发布").strip() or "系统发布"
    edited_at = _display_datetime_text(item.get("updated_at") or item.get("created_at"))
    return editor, edited_at, 0


def render_announcement_feed(limit: int = 6) -> None:
    st.markdown("### 更新公告")
    ok, data = api_get("/announcements", limit=limit)
    if not ok:
        st.info("暂时无法加载更新公告。")
        return
    items = data.get("items", []) if isinstance(data, dict) else []
    if not items:
        st.info("当前还没有更新公告。")
        return

    pinned_item = next((item for item in items if item.get("is_pinned")), None)
    latest_item = next(
        (
            item
            for item in items
            if pinned_item is None or str(item.get("id")) != str(pinned_item.get("id"))
        ),
        None,
    )
    featured_entries: list[tuple[dict[str, Any], str]] = []
    if pinned_item is not None:
        featured_entries.append((pinned_item, "置顶公告"))
    if latest_item is not None:
        featured_entries.append((latest_item, "最新公告"))
    elif pinned_item is None and items:
        featured_entries.append((items[0], "最新公告"))

    featured_ids = {str(item.get("id")) for item, _ in featured_entries}
    history_items = [item for item in items if str(item.get("id")) not in featured_ids]

    def _render_announcement_card(item: dict[str, Any], *, tag: str, compact: bool = False) -> str:
        title = escape(str(item.get("title") or ("置顶公告" if item.get("is_pinned") else "更新公告")).strip())
        summary_text = str(item.get("summary") or "").strip() or "暂无摘要"
        summary = escape(summary_text).replace("\n", "<br>")
        latest_editor, latest_edit_at, edit_count = _announcement_last_edit_meta(item)
        updated_by = escape(latest_editor)
        updated_at = escape(latest_edit_at)
        edit_count_text = f" | 编辑次数: {edit_count}" if edit_count > 0 else ""
        pinned_badge = (
            '<span style="display:inline-flex;align-items:center;padding:2px 10px;border-radius:999px;'
            'background:rgba(11,92,173,0.10);color:#0b5cad;font-size:11px;font-weight:700;">置顶</span>'
            if item.get("is_pinned")
            else ""
        )
        if compact:
            return (
                '<article style="padding:14px 16px;border-radius:18px;border:1px solid rgba(126,184,255,0.20);'
                'background:rgba(255,255,255,0.92);margin-top:10px;">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">'
                f'<div style="font-size:14px;font-weight:700;color:#12324f;line-height:1.5;">{title}</div>'
                f"{pinned_badge}</div>"
                f'<div style="margin-top:8px;font-size:12px;line-height:1.6;color:#4f6478;">{summary}</div>'
                f'<div style="margin-top:8px;font-size:11px;color:#70859b;">最近编辑: {updated_by} | {updated_at}{escape(edit_count_text)}</div>'
                "</article>"
            )
        return (
            '<article style="padding:18px;border-radius:20px;border:1px solid rgba(126,184,255,0.24);'
            'background:linear-gradient(180deg,rgba(255,255,255,0.96),rgba(241,248,255,0.90));margin-bottom:12px;">'
            '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
            f'<span style="display:inline-flex;align-items:center;padding:2px 10px;border-radius:999px;'
            'background:rgba(11,92,173,0.10);color:#0b5cad;font-size:11px;font-weight:700;">'
            f"{escape(tag)}</span>{pinned_badge}</div>"
            f'<div style="margin-top:12px;font-size:15px;font-weight:700;color:#12324f;line-height:1.6;">{title}</div>'
            f'<div style="margin-top:10px;font-size:13px;line-height:1.75;color:#38556f;white-space:normal;">{summary}</div>'
            f'<div style="margin-top:12px;font-size:11px;color:#70859b;">最近编辑: {updated_by} | 编辑时间: {updated_at}{escape(edit_count_text)}</div>'
            "</article>"
        )

    featured_html = "".join(_render_announcement_card(item, tag=tag) for item, tag in featured_entries)
    history_html = "".join(_render_announcement_card(item, tag="历史公告", compact=True) for item in history_items)
    st.markdown(
        f"""
        <div style="border:1px solid rgba(126,184,255,0.22);border-radius:24px;padding:18px 18px 14px 18px;
                    background:linear-gradient(180deg,rgba(255,255,255,0.94),rgba(241,248,255,0.86));">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px;">
                <div>
                    <div style="font-size:15px;font-weight:800;color:#12324f;">公告栏</div>
                    <div style="margin-top:6px;font-size:12px;line-height:1.7;color:#70859b;">
                        默认展示置顶公告和最新公告，下滑滚轮可回看过往公告。
                    </div>
                </div>
                <div style="padding:4px 10px;border-radius:999px;background:rgba(11,92,173,0.08);color:#0b5cad;font-size:11px;font-weight:700;">
                    {len(items)} 条
                </div>
            </div>
            <div style="max-height:420px;overflow-y:auto;padding-right:6px;">
                {featured_html}
                {"<div style='margin:4px 2px 0 2px;font-size:11px;font-weight:700;letter-spacing:0.08em;color:#70859b;'>历史公告</div>" if history_html else ""}
                {history_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_announcement_admin_panel(current_user: dict[str, Any]) -> None:
    if not current_user.get("is_admin"):
        return
    with st.expander("发布更新公告", expanded=False):
        title = st.text_input("公告标题", key="announcement_title")
        summary = st.text_area("更新摘要", key="announcement_summary", height=120, placeholder="填写本次更新摘要")
        is_pinned = st.checkbox("设为置顶消息", key="announcement_is_pinned")
        if st.button("发布公告", key="announcement_publish_button", use_container_width=True):
            ok, resp = api_post(
                "/admin/announcements",
                json={"title": title, "summary": summary, "is_pinned": is_pinned},
                timeout=30,
            )
            if ok:
                st.success("更新公告已发布。")
                clear_cached_api_get()
                st.rerun()
            else:
                st.error(resp)

    with st.expander("管理已有公告", expanded=False):
        ok, data = api_get("/announcements", limit=50)
        if not ok:
            st.error(data)
            return
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            st.info("当前还没有可管理的公告。")
            return

        labels = [
            f"{item['id']} | {'置顶' if item.get('is_pinned') else '更新'} | {str(item.get('title') or '未命名公告').strip()} | {_display_datetime_text(item.get('updated_at'))}"
            for item in items
        ]
        picked_label = st.selectbox("选择公告", labels, key="announcement_manage_pick")
        selected = items[labels.index(picked_label)]
        announcement_id = int(selected["id"])
        title_key = f"announcement_edit_title_{announcement_id}"
        summary_key = f"announcement_edit_summary_{announcement_id}"
        pinned_key = f"announcement_edit_pinned_{announcement_id}"
        confirm_delete_key = f"announcement_delete_confirm_{announcement_id}"

        st.text_input("公告标题", value=str(selected.get("title") or ""), key=title_key)
        st.text_area(
            "更新摘要",
            value=str(selected.get("summary") or ""),
            key=summary_key,
            height=140,
            placeholder="填写本次更新摘要",
        )
        st.checkbox("设为置顶消息", value=bool(selected.get("is_pinned")), key=pinned_key)
        edit_history_rows = _announcement_edit_history_rows(selected)
        latest_editor, latest_edit_at, edit_count = _announcement_last_edit_meta(selected)
        st.caption(f"最近编辑人: {latest_editor} | 编辑时间: {latest_edit_at} | 编辑次数: {edit_count}")
        if edit_history_rows:
            safe_dataframe(pd.DataFrame(edit_history_rows), use_container_width=True, height=220)
        else:
            st.info("当前公告还没有编辑历史，后续修改会在这里显示。")
        if st.checkbox("显示公告原始数据", value=False, key=f"announcement_show_raw_{announcement_id}"):
            safe_json(selected)

        save_col, delete_col = st.columns(2)
        if save_col.button("保存修改", key=f"announcement_save_button_{announcement_id}", use_container_width=True):
            ok_update, resp_update = api_put(
                f"/admin/announcements/{announcement_id}",
                {
                    "title": st.session_state.get(title_key),
                    "summary": st.session_state.get(summary_key),
                    "is_pinned": bool(st.session_state.get(pinned_key)),
                },
            )
            if ok_update:
                st.success("公告已更新。")
                clear_cached_api_get()
                st.rerun()
            else:
                st.error(resp_update)

        confirm_delete = st.checkbox("确认删除该公告", key=confirm_delete_key)
        if delete_col.button("删除公告", key=f"announcement_delete_button_{announcement_id}", use_container_width=True, disabled=not confirm_delete):
            ok_delete, resp_delete = api_delete(f"/admin/announcements/{announcement_id}")
            if ok_delete:
                st.success("公告已删除。")
                clear_cached_api_get()
                st.rerun()
            else:
                st.error(resp_delete)


def render_user_management_page() -> None:
    st.subheader("用户管理")
    st.caption("仅管理员可见，用于处理注册审核、账号启停与角色设置。")
    ok, data = api_get("/admin/users")
    if not ok:
        st.error(data)
        return
    items = data.get("items", [])
    safe_dataframe(pd.DataFrame(items), use_container_width=True, height=320)
    if not items:
        return
    labels = [f"{row['id']} | {row['username']} | {row['status']} | {','.join(row.get('roles') or [])}" for row in items]
    picked = st.selectbox("选择用户", labels, key="admin_user_pick")
    selected = items[labels.index(picked)]
    c1, c2, c3, c4 = st.columns(4)
    actions = [
        (c1, "approve", "通过"),
        (c2, "reject", "拒绝"),
        (c3, "disable", "停用"),
        (c4, "enable", "启用"),
    ]
    for column, action, label in actions:
        if column.button(label, key=f"user_status_{selected['id']}_{action}"):
            ok_status, resp_status = api_post(f"/admin/users/{selected['id']}/status", json={"action": action}, timeout=30)
            if ok_status:
                st.success(f"用户状态已更新为 {action}")
                clear_cached_api_get()
                st.rerun()
            else:
                st.error(resp_status)

    reviewer_flag = st.checkbox("设为 reviewer", value=bool(selected.get("is_reviewer")), key=f"user_reviewer_{selected['id']}")
    admin_flag = st.checkbox("设为 admin", value=bool(selected.get("is_admin")), key=f"user_admin_{selected['id']}")
    if st.button("保存角色设置", key=f"user_roles_{selected['id']}"):
        ok_roles, resp_roles = api_post(
            f"/admin/users/{selected['id']}/roles",
            json={"is_reviewer": reviewer_flag, "is_admin": admin_flag},
            timeout=30,
        )
        if ok_roles:
            st.success("角色设置已保存。")
            clear_cached_api_get()
            st.rerun()
        else:
            st.error(resp_roles)


def render_solution_hub(current_user: dict[str, Any]) -> None:
    st.subheader("全局方案库")
    st.caption("围绕全局可复用方案、检索索引、任务簇管理和审核流的统一入口。")
    ok_cfg, cfg = api_get("/solution-repository/config")
    if not ok_cfg:
        st.error(cfg)
        return
    modules = cfg.get("modules", [])
    task_clusters = cfg.get("task_clusters", [])
    module_map = {f"{item['display_name']} | {item['prefix']}": item for item in modules}
    cluster_names = [item["display_name"] for item in task_clusters]
    is_reviewer = bool(current_user.get("is_reviewer") or current_user.get("is_admin"))

    submit_tab, query_tab, review_tab, taxonomy_tab = st.tabs(["方案提交", "方案检索", "方案审核", "任务簇与模块"])

    with submit_tab:
        module_label = st.selectbox("模块前缀", list(module_map.keys()), key="hub_module_pick")
        selected_module = module_map[module_label]
        selected_clusters = st.multiselect("任务簇", cluster_names, key="hub_clusters")
        new_cluster = st.text_input("新增任务簇候选", key="hub_new_cluster")
        error_name = st.text_input("错误名", key="hub_error_name")
        message = st.text_area("message 关键词 / 现象描述", key="hub_message", height=90)
        message_keywords = st.text_input("message 关键词", key="hub_message_keywords", help="多个关键词用逗号分隔")
        tags = st.text_input("标签", key="hub_tags", help="多个标签用逗号分隔")
        root_cause = st.text_area("根因分析", key="hub_root_cause", height=120)
        verified_solution = st.text_area("已验证解决方案", key="hub_verified_solution", height=120)
        workaround = st.text_area("临时绕过方案", key="hub_workaround", height=90)
        trigger_scenario = st.text_area("触发场景 / 问题簇", key="hub_trigger_scenario", height=100)
        related_task_uuid = st.text_input("关联 task_uuid", key="hub_task_uuid")
        normalized_signature = st.text_input("关联 normalized_signature", key="hub_signature")
        if st.button("提交方案", type="primary", key="hub_submit_review"):
            final_clusters = list(selected_clusters)
            if new_cluster.strip():
                ok_cluster, resp_cluster = api_post(
                    "/solution-repository/task-clusters",
                    json={"display_name": new_cluster.strip(), "description": trigger_scenario},
                    timeout=30,
                )
                if ok_cluster:
                    final_clusters.append(resp_cluster.get("item", {}).get("display_name", new_cluster.strip()))
                else:
                    st.error(resp_cluster)
                    st.stop()
            payload = {
                "module": selected_module["module_key"],
                "error_name": error_name,
                "message": message,
                "message_keywords": [part.strip() for part in message_keywords.split(",") if part.strip()],
                "tags": [part.strip() for part in tags.split(",") if part.strip()],
                "task_clusters": final_clusters,
                "root_cause_analysis": root_cause,
                "verified_solution": verified_solution,
                "workaround": workaround,
                "trigger_scenario": trigger_scenario,
                "task_uuid": related_task_uuid or None,
                "normalized_signature": normalized_signature or None,
                "reusable": True,
                "source": "streamlit_solution_hub",
            }
            endpoint = "/solution-repository/records" if is_reviewer else "/solution-reviews"
            ok_submit, resp_submit = api_post(endpoint, json=payload, timeout=45)
            if ok_submit:
                st.success("方案已提交。")
                safe_json(resp_submit.get("item") or resp_submit)
                clear_cached_api_get()
            else:
                st.error(resp_submit)

    with query_tab:
        q1, q2, q3 = st.columns(3)
        search = q1.text_input("全文检索", key="hub_search")
        module_filter = q2.selectbox("模块过滤", [""] + [item["module_key"] for item in modules], key="hub_query_module")
        cluster_filter = q3.selectbox("任务簇过滤", [""] + cluster_names, key="hub_query_cluster")
        q4, q5, q6 = st.columns(3)
        error_code = q4.text_input("错误码", key="hub_query_error_code")
        error_name_filter = q5.text_input("错误名", key="hub_query_error_name")
        submitter_filter = q6.text_input("提交人", key="hub_query_submitter")
        q7, q8, q9 = st.columns(3)
        keyword_filter = q7.text_input("message 关键词", key="hub_query_keyword")
        review_status_filter = q8.selectbox("审核状态", ["", "approved", "pending_review", "needs_revision", "rejected"], key="hub_query_status")
        reusable_filter = q9.selectbox("可复用", ["", "true", "false"], key="hub_query_reusable")
        params = {
            "search": search or None,
            "module": module_filter or None,
            "task_cluster": cluster_filter or None,
            "error_code": error_code or None,
            "error_name": error_name_filter or None,
            "submitter": submitter_filter or None,
            "message_keyword": keyword_filter or None,
            "review_status": review_status_filter or None,
            "reusable": None if reusable_filter == "" else (reusable_filter == "true"),
            "limit": 200,
        }
        ok_records, records = api_get("/solution-repository/records", **params)
        if ok_records:
            items = records.get("items", [])
            safe_dataframe(pd.DataFrame(items), use_container_width=True, height=320)
            st.markdown(f"[导出 JSON]({_api_base()}/solution-repository/export?format=json{_auth_query_suffix()})")
            st.markdown(f"[导出 CSV]({_api_base()}/solution-repository/export?format=csv{_auth_query_suffix()})")
            st.markdown(f"[导出 Excel]({_api_base()}/solution-repository/export?format=xlsx{_auth_query_suffix()})")
            st.markdown(f"[导出 SQLite]({_api_base()}/solution-repository/export?format=sqlite{_auth_query_suffix()})")
        else:
            st.error(records)

    with review_tab:
        if not is_reviewer:
            st.info("当前账号为 submitter，仅能查看自己提交的审核记录。")
        review_status = st.selectbox("审核列表状态", ["", "pending_review", "approved", "needs_revision", "rejected"], key="hub_review_status")
        ok_reviews, reviews = api_get("/solution-reviews", status=review_status or None, limit=200)
        if ok_reviews:
            items = reviews.get("items", [])
            safe_dataframe(pd.DataFrame(items), use_container_width=True, height=300)
            if is_reviewer and items:
                labels = [f"{row['id']} | {row.get('review_status')} | {row.get('module')} | {row.get('created_by')}" for row in items]
                picked = st.selectbox("选择审核记录", labels, key="hub_review_pick")
                selected = items[labels.index(picked)]
                safe_json(selected)
                notes = st.text_area("审核意见", key="hub_review_notes", height=90)
                r1, r2, r3 = st.columns(3)
                actions = [(r1, "approved", "通过"), (r2, "needs_revision", "退回修改"), (r3, "rejected", "拒绝")]
                for col, status_value, label in actions:
                    if col.button(label, key=f"hub_review_{selected['id']}_{status_value}"):
                        ok_action, resp_action = api_post(
                            f"/solution-reviews/{selected['id']}/manual-review",
                            json={"review_status": status_value, "notes": notes},
                            timeout=45,
                        )
                        if ok_action:
                            st.success(f"已更新为 {status_value}")
                            clear_cached_api_get()
                            st.rerun()
                        else:
                            st.error(resp_action)
        else:
            st.error(reviews)

    with taxonomy_tab:
        st.markdown("#### 任务簇")
        ok_clusters, cluster_resp = api_get("/solution-repository/task-clusters", include_pending=True if is_reviewer else False)
        if ok_clusters:
            cluster_items = cluster_resp.get("items", [])
            safe_dataframe(pd.DataFrame(cluster_items), use_container_width=True, height=220)
            cluster_name = st.text_input("新任务簇名称", key="taxonomy_new_cluster")
            cluster_desc = st.text_area("任务簇说明", key="taxonomy_new_cluster_desc", height=80)
            if st.button("提交任务簇", key="taxonomy_submit_cluster"):
                ok_create, resp_create = api_post(
                    "/solution-repository/task-clusters",
                    json={"display_name": cluster_name, "description": cluster_desc},
                    timeout=30,
                )
                if ok_create:
                    st.success("任务簇已提交。")
                    clear_cached_api_get()
                    st.rerun()
                else:
                    st.error(resp_create)
            if is_reviewer and cluster_items:
                pending_labels = [f"{row['id']} | {row['display_name']} | {row['review_status']}" for row in cluster_items]
                picked = st.selectbox("审核任务簇", pending_labels, key="taxonomy_cluster_review_pick")
                selected = cluster_items[pending_labels.index(picked)]
                c1, c2, c3 = st.columns(3)
                for col, status_value, label in [(c1, "approved", "通过"), (c2, "rejected", "拒绝"), (c3, "disabled", "停用")]:
                    if col.button(label, key=f"taxonomy_cluster_{selected['id']}_{status_value}"):
                        ok_review, resp_review = api_post(
                            f"/solution-repository/task-clusters/{selected['id']}/review",
                            json={"review_status": status_value},
                            timeout=30,
                        )
                        if ok_review:
                            st.success(f"任务簇已更新为 {status_value}")
                            clear_cached_api_get()
                            st.rerun()
                        else:
                            st.error(resp_review)
        else:
            st.error(cluster_resp)

        if is_reviewer:
            st.markdown("#### 模块配置")
            safe_dataframe(pd.DataFrame(modules), use_container_width=True, height=220)
            m1, m2, m3 = st.columns(3)
            module_key = m1.text_input("module_key", key="taxonomy_module_key")
            display_name = m2.text_input("display_name", key="taxonomy_module_name")
            prefix = m3.text_input("prefix", key="taxonomy_module_prefix")
            description = st.text_area("模块说明", key="taxonomy_module_desc", height=80)
            if st.button("保存模块配置", key="taxonomy_module_submit"):
                ok_module, resp_module = api_post(
                    "/solution-repository/modules",
                    json={"module_key": module_key, "display_name": display_name, "prefix": prefix, "description": description, "is_active": True},
                    timeout=30,
                )
                if ok_module:
                    st.success("模块配置已保存。")
                    clear_cached_api_get()
                    st.rerun()
                else:
                    st.error(resp_module)


st.session_state.setdefault("theme_mode", "light")
st.session_state.setdefault("api_base", DEFAULT_API_BASE)
st.session_state.setdefault("auth_token", "")
st.session_state.setdefault("current_user", None)
inject_design_system(str(st.session_state.get("theme_mode", "light")))
API_BASE = st.sidebar.text_input("FastAPI 地址", value=st.session_state["api_base"])
st.session_state["api_base"] = API_BASE
theme_is_dark = st.sidebar.toggle("暗色主题", value=str(st.session_state.get("theme_mode", "light")) == "dark")
next_theme_mode = "dark" if theme_is_dark else "light"
if next_theme_mode != st.session_state.get("theme_mode", "light"):
    st.session_state["theme_mode"] = next_theme_mode
    st.rerun()

current_user = st.session_state.get("current_user") or _refresh_current_user()
if not current_user:
    render_login_portal()
    st.stop()

render_account_controls(cast(dict[str, Any], current_user))
api_ok, api_msg = check_api_health()

tasks_page = load_tasks_page()
tasks = tasks_page.get("items", [])
label_to_uuid = {f"{_display_datetime_text(t.get('created_at'))} | {str(t.get('task_uuid', ''))[:8]} | {t.get('status', '')} | {t.get('filename', '')}": t.get("task_uuid", "") for t in tasks}
labels = ["(不选择历史任务)"] + list(label_to_uuid.keys())
default_uuid = st.session_state.get("latest_task_uuid", "")
default_label = next((label for label, uuid in label_to_uuid.items() if uuid == default_uuid), labels[0])
selected_label = st.sidebar.selectbox("历史任务", labels, index=labels.index(default_label) if default_label in labels else 0)
if selected_label != labels[0]:
    st.session_state["latest_task_uuid"] = label_to_uuid[selected_label]
manual_uuid = st.sidebar.text_input("任务 UUID", value=st.session_state.get("latest_task_uuid", ""))
if manual_uuid:
    st.session_state["latest_task_uuid"] = manual_uuid.strip()
task_uuid = st.session_state.get("latest_task_uuid", "")
render_sidebar_shell(len(tasks), str(task_uuid), api_ok, api_msg)

with st.sidebar.expander("项目管理", expanded=False):
    if task_uuid:
        st.caption(f"任务 UUID: {task_uuid}")
        if st.checkbox("我确认删除该历史项目", key="confirm_delete_task"):
            if st.button("删除当前项目", type="secondary"):
                ok_del, resp_del = api_delete(f"/tasks/{task_uuid}")
                if ok_del:
                    st.session_state["latest_task_uuid"] = ""
                    st.success("项目已删除")
                    st.rerun()
                else:
                    st.error(resp_del)
    else:
        st.info("当前未选择历史项目。")

nav_pages = ["首页 / 仪表盘", "历史项目中心", "统一事件流", "耗时分析", "事件流时间轴", "错误分析", "参数趋势分析", "LLM 诊断", "方案库中心", "原始文件预览", "未知日志待标注池", "规则建议审核视图", "配置页面", "导出"]
if bool(current_user.get("is_admin")):
    nav_pages.insert(nav_pages.index("方案库中心") + 1, "用户管理")
page = st.sidebar.radio("导航", nav_pages)
if page != "首页 / 仪表盘":
    render_page_intro(page, task_uuid, api_ok)

if page == "用户管理":
    render_user_management_page()

elif page == "方案库中心":
    render_solution_hub(cast(dict[str, Any], current_user))

elif page == "首页 / 仪表盘":
    notice = str(st.session_state.pop("dashboard_upload_notice", "") or "").strip()
    if notice:
        st.success(notice)

    ok_runtime, runtime = api_get("/system/runtime", live=True)
    upload_col, runtime_col = st.columns([1.05, 1.15], gap="large")
    with upload_col:
        render_dashboard_upload_panel(panel_key="dashboard")
    with runtime_col:
        if ok_runtime and isinstance(runtime, dict):
            render_system_pressure_summary(cast(JsonDict, runtime))
        else:
            st.error(runtime)
    render_announcement_feed(limit=50)
    render_announcement_admin_panel(cast(dict[str, Any], current_user))

    if not task_uuid:
        st.info("可先在上方直接上传新文件，或从左侧选择历史任务 UUID。")
    else:
        ok, data = api_get(f"/tasks/{task_uuid}/dashboard")
        ok_status, status = api_get(f"/tasks/{task_uuid}/status", live=True)
        ok_perf, perf = api_get(f"/tasks/{task_uuid}/performance-summary")
        if ok and ok_status:
            perf_summary = perf if ok_perf and isinstance(perf, dict) else {}
            file_count = data.get("file_count", 0) or 0
            total_events = data.get("total_events", 0) or 0
            total_errors = data.get("total_errors", 0) or 0
            unique_error_count = data.get("unique_error_count", 0) or 0
            render_dashboard_summary(
                "序列日志整理与问题反馈系统",
                "首页优先回答当前任务是否异常、问题集中在哪、是否值得继续深挖。",
                [
                    {"icon": "file", "label": "文件数", "value": file_count, "note": "纳入本次分析的源文件总量", "tone": "#052659"},
                    {"icon": "stream", "label": "总事件数", "value": total_events, "note": "统一归档并可追踪的事件记录数", "tone": "#0B5CAD"},
                    {"icon": "alert", "label": "总错误数", "value": total_errors, "note": "累计识别出的错误条目总数", "tone": "#D96B3B"},
                    {"icon": "review", "label": "唯一错误数", "value": unique_error_count, "note": "去重后的错误簇数量", "tone": "#DCEBFA"},
                ],
            )
            render_dashboard_progress_card(task_uuid, cast(JsonDict, status))
            render_dashboard_snapshot(
                status.get("progress_percent", 0),
                f"当前阶段: {status.get('current_stage') or ('已完成' if status.get('status') == 'completed' else '等待状态同步')}",
                status.get("message") or "图表区域保留问题定位信息，性能与运行细节收纳到下方折叠区。",
                [
                    {"label": "当前状态", "value": status.get("status", "-"), "tone": "#052659"},
                    {"label": "错误密度", "value": _format_percent(total_errors, total_events, 2), "tone": "#D96B3B"},
                    {"label": "唯一错误占比", "value": _format_percent(unique_error_count, total_errors, 1), "tone": "#DCEBFA"},
                    {"label": "平均每文件事件", "value": round(total_events / file_count) if file_count else 0, "tone": "#E7EFF8"},
                ],
            )
            top_errors = pd.DataFrame(data.get("top_errors", []))
            comp_df = pd.DataFrame(data.get("component_distribution", []))
            st.markdown("#### 问题定位")
            st.caption("左侧回答先看哪些错误簇最频繁，右侧回答问题主要落在哪些组件。")
            overview_left, overview_right = st.columns([1.35, 0.95], gap="large")
            with overview_left:
                if not top_errors.empty:
                    top_errors = enrich_error_family_frame(top_errors.head(10))
                    top_errors["display_signature_short"] = top_errors["display_signature"].astype(str).map(lambda value: value if len(value) <= 62 else value[:59] + "...")
                    top_errors = top_errors.sort_values(by="count", ascending=True)
                    fig = px.bar(
                        top_errors,
                        x="count",
                        y="display_signature_short",
                        color="error_family_display",
                        orientation="h",
                        text="count",
                        title="近期高频错误簇 Top 10",
                    )
                    fig.update_traces(textposition="outside", cliponaxis=False)
                    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=11))
                    fig.update_xaxes(title="次数", automargin=True)
                    render_fig(fig, key="dash_top", height=480, title_outside=True)
                else:
                    st.info("当前任务暂无可展示的高频错误簇。")
            with overview_right:
                if not comp_df.empty:
                    comp_df = comp_df.sort_values(by="count", ascending=False).copy()
                    if len(comp_df) > 8:
                        others_count = comp_df.iloc[8:]["count"].sum()
                        comp_df = pd.concat([comp_df.iloc[:8], pd.DataFrame([{"component": "其他", "count": others_count}])], ignore_index=True)
                    fig = px.pie(comp_df, names="component", values="count", hole=0.58, title="各组件错误分布")
                    fig.update_traces(textposition="inside", textinfo="percent", sort=False)
                    render_fig(fig, key="dash_comp", height=430, title_outside=True)
                else:
                    st.info("当前任务暂无可展示的组件级错误分布。")
            if ok_perf and perf_summary:
                with st.expander("性能摘要", expanded=False):
                    render_homepage_performance_summary(perf_summary, status)
        else:
            st.error(data if not ok else status)

elif page == "历史项目中心":
    paged_table("/tasks", page_key="tasks_page", page_size_key="tasks_page_size", title="任务列表", default_page_size=50, max_page_size=200)
    if tasks:
        history_labels = [
            f"{str(item.get('task_uuid', ''))[:8]} | {item.get('filename', '-') or '-'} | {item.get('uploaded_by', '-') or '-'} | {item.get('total_size_text', '-') or '-'}"
            for item in tasks
        ]
        picked_history = st.selectbox("选择历史任务", history_labels, key="history_detail_pick")
        selected_task = tasks[history_labels.index(picked_history)]
        st.markdown("### 历史任务详情")
        safe_dataframe(
            pd.DataFrame(
                [
                    {"Field": "task_uuid", "Value": selected_task.get("task_uuid")},
                    {"Field": "filename", "Value": selected_task.get("filename")},
                    {"Field": "uploaded_by", "Value": selected_task.get("uploaded_by")},
                    {"Field": "total_size_text", "Value": selected_task.get("total_size_text") or "0 B"},
                    {"Field": "status", "Value": selected_task.get("status")},
                    {"Field": "progress_percent", "Value": f"{selected_task.get('progress_percent', 0)}%"},
                    {"Field": "total_errors", "Value": selected_task.get("total_errors")},
                    {"Field": "created_at", "Value": _display_datetime_text(selected_task.get("created_at"))},
                    {"Field": "updated_at", "Value": _display_datetime_text(selected_task.get("updated_at"))},
                ]
            ),
            use_container_width=True,
            height=320,
        )
        download_query = _query_params_for_link()
        download_suffix = f"?{download_query}" if download_query else ""
        st.markdown(f"[下载上传文件]({_api_base()}/tasks/{selected_task.get('task_uuid')}/download{download_suffix})")

elif page == "文件上传":
    with st.form("upload_form"):
        uploaded = st.file_uploader("支持多文件与压缩包上传(zip / 7z / tar)", accept_multiple_files=True)
        cpu_cores = st.number_input("并行处理 CPU 核心数", min_value=1, max_value=max(1, os.cpu_count() or 4), value=min(32, max(1, os.cpu_count() or 4)), step=1)
        perf_controls = _render_upload_perf_controls(key_prefix="page_upload")
        submitted = st.form_submit_button("开始批量上传并分析")
    if submitted and uploaded:
        with st.spinner("正在上传并提交后台任务，请勿重复点击..."):
            files_payload = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in uploaded]
            ok, result = api_post("/tasks/upload", files=files_payload, data={"cpu_cores": int(cpu_cores), **perf_controls})
            if ok:
                st.success("任务已提交，后端正在后台处理中。")
                st.session_state["latest_task_uuid"] = result["task_uuid"]
                clear_cached_api_get()
                safe_json(result)
            else:
                st.error(result)
    if task_uuid:
        ok, status = api_get(f"/tasks/{task_uuid}/status", live=True)
        if ok:
            st.markdown("### 当前任务进度")
            st.progress(int(status.get("progress_percent", 0)))
            c1, c2, c3, c4 = st.columns(4, gap="medium")
            c1.metric("状态", status.get("status", "-"))
            c2.metric("进度", f"{status.get('progress_percent', 0)}%")
            c3.metric("识别文件数", status.get("file_count", 0))
            c4.metric("队列位置", status.get("queue_position") or 0)
            st.info(status.get("current_stage") or "-")
            if status.get("message"):
                st.caption(status["message"])
            if st.button("刷新进度"):
                clear_cached_api_get(); st.rerun()

elif page == "统一事件流":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        scope_params = render_scope_filter_panel(task_uuid, "events_scope")
        f1, f2, f3, f4, f5 = st.columns(5, gap="medium")
        component = f1.text_input("组件过滤")
        level = f2.selectbox("级别", ["", "INFO", "WARN", "ERROR", "FATAL"])
        cycle_no = f3.text_input("Cycle")
        chip_name = f4.text_input("芯片名")
        search = f5.text_input("关键词")
        paged_table(
            f"/tasks/{task_uuid}/events",
            params={
                "component": component or None,
                "level": level or None,
                "cycle_no": int(cycle_no) if cycle_no.strip() else None,
                "chip_name": chip_name or None,
                "search": search or None,
                **scope_params,
            },
            page_key="events_page",
            page_size_key="events_page_size",
            title="统一事件流",
            default_page_size=100,
            max_page_size=500,
        )

elif page == "耗时分析":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        unit = DURATION_UNITS[st.selectbox("Cycle 总耗时单位", list(DURATION_UNITS.keys()), key="ana_unit")]
        scope_params = render_scope_filter_panel(task_uuid, "timing_scope")
        ok2, cycle_rows = api_get(f"/tasks/{task_uuid}/cycle-summary", unit=unit, **scope_params)
        if ok2:
            cycle_df = pd.DataFrame(cycle_rows)
            if not cycle_df.empty:
                render_fig(px.line(cycle_df, x="cycle_no", y="total_duration_value", color="chip_name", markers=True), key="ana_cycle", title=f"Cycle 总耗时趋势({unit})", height=420, title_outside=True)
                safe_dataframe(cycle_df, use_container_width=True, height=260)
        paged_table(
            f"/tasks/{task_uuid}/steps",
            params=scope_params,
            page_key="steps_page",
            page_size_key="steps_page_size",
            title="Sub-step 耗时表",
            default_page_size=100,
            max_page_size=500,
        )
        ok3, ops = api_get(f"/tasks/{task_uuid}/operational-metrics", **scope_params)
        if ok3:
            photo_df = pd.DataFrame(ops.get("photo_summary", []))
            if not photo_df.empty:
                st.markdown("### 拍照时间摘要")
                safe_dataframe(photo_df, use_container_width=True, height=240)

elif page == "事件流时间轴":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        scope_params = render_scope_filter_panel(task_uuid, "timeline_scope")
        cycles_ok, cycles = api_get(f"/tasks/{task_uuid}/cycles")
        options = ["全程"] + [str(c) for c in (cycles if cycles_ok else [])]
        cycle_pick = st.selectbox("选择 Cycle", options, key="timeline_cycle")
        track_order = st.selectbox("纵轴顺序", ["default", "cycle"], format_func=lambda x: "默认顺序" if x == "default" else "按 cycle 排序")
        cycle_no = None if cycle_pick == "全程" else int(cycle_pick)
        track_granularity = st.selectbox("轨道粒度", ["component", "side", "side_chip"], index=2)
        ok, rows = api_get(
            f"/tasks/{task_uuid}/movement-timeline",
            cycle_no=cycle_no,
            track_order=track_order,
            track_granularity=track_granularity,
            **scope_params,
        )
        ok_errors, error_rows = api_get(
            f"/tasks/{task_uuid}/movement-timeline/errors",
            cycle_no=cycle_no,
            track_granularity=track_granularity,
            **scope_params,
        )
        if ok:
            timeline_payload = rows if isinstance(rows, dict) else {"rows": rows}
            error_payload = error_rows if ok_errors and isinstance(error_rows, dict) else {"points": error_rows if ok_errors else []}
            side_groups = timeline_payload.get("by_side", []) or []
            all_rows = timeline_payload.get("rows", []) or []
            all_error_rows = error_payload.get("points", []) or []

            if side_groups:
                side_labels = ["整机全部边"]
                side_map = {"整机全部边": None}
                for item in side_groups:
                    base_label = str(item.get("side_label") or item.get("side_scope") or "Unassigned")
                    uncertain_count = int(item.get("uncertain_count") or 0)
                    shared_count = int(item.get("shared_count") or 0)
                    label_parts: list[str] = []
                    if uncertain_count > 0:
                        label_parts.append(f"{uncertain_count} 条不确定时间轴")
                    if shared_count > 0:
                        label_parts.append(f"{shared_count} 条父边/分支边共享动作")
                    side_label = f"{base_label}（{'，'.join(label_parts)}）" if label_parts else base_label
                    side_labels.append(side_label)
                    side_map[side_label] = str(item.get("side_scope") or "")
                picked_side = st.selectbox("查看哪一边", side_labels, key="timeline_side_pick")
                target_side_scope = side_map.get(picked_side)
                visible_groups = side_groups if target_side_scope is None else [item for item in side_groups if str(item.get("side_scope") or "") == target_side_scope]
            else:
                visible_groups = [{"side_scope": None, "side_label": "Unassigned", "rows": all_rows, "uncertain_count": len(timeline_payload.get("unassigned_side_rows", []) or [])}]

            error_df_all = pd.DataFrame(all_error_rows)
            show_error_points = st.checkbox("标记错误发生时间点", value=True, key="timeline_show_errors")
            selected_families: list[str] = []
            selected_severities: list[str] = []
            if show_error_points and not error_df_all.empty:
                error_df_all = enrich_error_family_frame(error_df_all)
                error_df_all["severity"] = error_df_all["severity"].fillna("unknown").astype(str)
                family_options = sorted(error_df_all["error_family_display"].dropna().unique().tolist())
                severity_options = sorted(error_df_all["severity"].dropna().unique().tolist())
                c1, c2 = st.columns(2)
                with c1:
                    selected_families = st.multiselect("显示哪些错误家族", family_options, default=family_options, key="timeline_error_families")
                with c2:
                    selected_severities = st.multiselect("显示哪些严重级别", severity_options, default=severity_options, key="timeline_error_severities")
                error_df_all = error_df_all[
                    error_df_all["error_family_display"].isin(selected_families)
                    & error_df_all["severity"].isin(selected_severities)
                ].copy()
                error_df_all["time"] = pd.to_datetime(error_df_all["time"], errors="coerce")
                error_df_all = _dropna_frame(error_df_all, "time").copy()

            for index, group in enumerate(visible_groups):
                group_rows = group.get("rows", []) or []
                df = pd.DataFrame(group_rows)
                if df.empty:
                    continue
                df["start"] = pd.to_datetime(df["start"], errors="coerce")
                df["end"] = pd.to_datetime(df["end"], errors="coerce")
                df = _dropna_frame(df, "start", "end").copy()
                if df.empty:
                    continue
                if "is_uncertain_side" in df.columns:
                    df["track"] = df.apply(
                        lambda row: f"[?] {row['track']}" if bool(row.get("is_uncertain_side")) else row["track"],
                        axis=1,
                    )
                group_side_scope = str(group.get("side_scope") or "")
                group_error_rows = []
                if not error_df_all.empty:
                    group_error_rows = [
                        item
                        for item in all_error_rows
                        if str(item.get("render_side_scope") or item.get("side_scope") or "") == group_side_scope
                    ]
                error_df = pd.DataFrame(group_error_rows)
                if not error_df.empty:
                    error_df = enrich_error_family_frame(error_df)
                    error_df["severity"] = error_df["severity"].fillna("unknown").astype(str)
                    if selected_families:
                        error_df = error_df[
                            error_df["error_family_display"].isin(selected_families)
                            & error_df["severity"].isin(selected_severities)
                        ].copy()
                    error_df["time"] = pd.to_datetime(error_df["time"], errors="coerce")
                    error_df = _dropna_frame(error_df, "time").copy()
                fig, error_df, track_order_values = build_movement_timeline_figure(df, error_df, order_mode=track_order, show_error_points=show_error_points)
                chart_title = f"运动时间轴 · {group.get('side_label') or group.get('side_scope') or 'Unassigned'}"
                timeline_key_seed = json.dumps(
                    {
                        "task_uuid": task_uuid,
                        "side_scope": group_side_scope,
                        "cycle_pick": cycle_pick,
                        "track_order": track_order,
                        "track_granularity": track_granularity,
                        "show_error_points": show_error_points,
                        "families": selected_families,
                        "severities": selected_severities,
                        "track_count": int(df["track"].nunique()),
                        "error_count": int(len(error_df)),
                    },
                    ensure_ascii=False,
                )
                timeline_render_key = f"timeline_{hashlib.sha1(timeline_key_seed.encode('utf-8')).hexdigest()[:12]}"
                render_fig(fig, key=timeline_render_key, height=min(max(500, 24 * len(df['track'].unique()) + 180), 2200), title=chart_title, title_outside=True)
                uncertain_count = int(group.get("uncertain_count") or 0)
                shared_count = int(group.get("shared_count") or 0)
                shared_sides = [str(item) for item in (group.get("shared_side_scopes") or []) if str(item or "").strip()]
                if uncertain_count > 0:
                    st.caption(f"当前图包含 {uncertain_count} 条边归属不确定的时间轴，已复制到该边视图中供对比。")
                if shared_count > 0:
                    shared_text = " / ".join(shared_sides) if shared_sides else "父边/分支边"
                    st.caption(f"当前图额外合并 {shared_count} 条来自 {shared_text} 的共享动作。")
                if show_error_points:
                    if ok_errors and not error_df.empty:
                        st.caption(f"当前图已标记 {len(error_df)} 个错误时间点，可按错误家族和严重级别自由筛选。")
                    elif ok_errors:
                        st.caption("当前筛选条件下没有可显示的错误时间点。")
                    else:
                        st.caption("错误时间点加载失败，当前仅展示甘特图。")
                if st.checkbox(f"显示时间轴表格明细 · {group.get('side_label') or group.get('side_scope') or 'Unassigned'}", value=False, key=f"timeline_table_{index}"):
                    safe_dataframe(
                        df[[c for c in ["render_side_scope", "side_scope", "original_side_scope", "is_shared_side_family", "track", "cycle_no", "component", "sub_step", "is_uncertain_side", "start_time_sec", "end_time_sec", "duration_ms", "message"] if c in df.columns]],
                        use_container_width=True,
                        height=300,
                    )
            if not all_rows:
                st.info("当前筛选条件下暂无可展示的运动时间轴。")
            else:
                with st.expander("查看原始时间轴与错误点数据", expanded=False):
                    safe_json(timeline_payload)
                    if ok_errors:
                        safe_json(error_payload)
        else:
            st.error(rows)

elif page == "错误分析":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        scope_params = render_scope_filter_panel(task_uuid, "error_scope")
        paged_table(
            f"/tasks/{task_uuid}/errors",
            params=scope_params,
            page_key="errors_page",
            page_size_key="errors_page_size",
            title="错误簇",
            default_page_size=100,
            max_page_size=500,
        )
        ok, rows = api_get(f"/tasks/{task_uuid}/errors", limit=100, offset=0, **scope_params)
        if ok and rows.get("items"):
            df = enrich_error_family_frame(rows["items"])
            tabs = st.tabs(["错误簇 Top N", "错误家族分布", "家族说明"])
            with tabs[0]:
                render_fig(px.bar(df.head(20), x="display_signature", y="count", color="error_family_display"), key="err_top", height=420, title="Top 错误簇")
            with tabs[1]:
                family_df = (
                    df.groupby(["error_family", "error_family_display", "error_family_description"], as_index=False)
                    .agg(count=("count", "sum"))
                    .sort_values(by="count", ascending=False)
                )
                render_fig(px.pie(family_df, names="error_family_display", values="count"), key="err_family", height=420, title="错误家族分布")
            with tabs[2]:
                family_guide_df = (
                    df.groupby(["error_family_display", "error_family", "error_family_description"], as_index=False)
                    .agg(count=("count", "sum"))
                    .sort_values(by="count", ascending=False)
                )
                safe_dataframe(family_guide_df.rename(columns={"error_family_display": "家族名称", "error_family": "家族代码", "error_family_description": "说明", "count": "错误次数"}), use_container_width=True, height=320)

elif page == "参数趋势分析":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        scope_params = render_scope_filter_panel(task_uuid, "parameter_scope")
        axis_mode = st.selectbox("横轴模式", ["cycle", "time"], format_func=lambda value: "按 cycle 排列" if value == "cycle" else "按时间排列", key="trend_axis_mode")
        ok_defs, defs = api_get("/parameter-definitions")
        if ok_defs:
            defs = [d for d in defs if d.get("parameter_name") != "imaging_time"]
            options = [d["parameter_name"] for d in defs]
            selected = st.multiselect("选择参数", options, default=options[:4])
            unit = DURATION_UNITS[st.selectbox("趋势图单位", list(DURATION_UNITS.keys()), key="trend_unit")]
            low_value_reference = st.selectbox("低值判定基线", ["优先期望值", "优先阈值"], key="trend_low_value_reference")
            highlight_low_points = st.checkbox("标红低于基线的点", value=True, key="trend_highlight_low_points")
            hide_low_points = st.checkbox("隐藏低于基线的点", value=False, key="trend_hide_low_points")
            if selected:
                for name in selected:
                    ok, rows = api_get(f"/tasks/{task_uuid}/parameter-series/{name}", unit=unit, axis_mode=axis_mode, **scope_params)
                    if ok and rows:
                        df = pd.DataFrame(rows)
                        if "x_axis_sort_value" in df.columns:
                            df = df.sort_values(by=["x_axis_sort_value", "series_name"], na_position="last")
                        elif "time_epoch_ms" in df.columns:
                            df = df.sort_values(by=["time_epoch_ms", "series_name"], na_position="last")
                        fig, low_value_meta = build_parameter_trend_figure(
                            df,
                            x_col="x_axis_label",
                            y_col="duration_value",
                            series_col="series_name",
                            x_sort_col="x_axis_sort_value",
                            low_value_preference=low_value_reference,
                            highlight_low_points=highlight_low_points,
                            hide_low_points=hide_low_points,
                        )
                        if fig is None:
                            if low_value_meta.get("hidden_low_count"):
                                st.info(f"{name} 趋势中，全部点都低于当前基线，已被隐藏。")
                            else:
                                st.info(f"{name} 趋势暂无可绘制数据。")
                            continue
                        render_fig(fig, key=f"trend_{name}_{axis_mode}", height=360, title=f"{name} 趋势")
                        low_label = low_value_meta.get("low_reference_label")
                        low_value = low_value_meta.get("low_reference_value")
                        hidden_low_count = int(low_value_meta.get("hidden_low_count") or 0)
                        if low_label and low_value is not None:
                            note_parts = [f"低值判定基线: {low_label} = {low_value:.4f} {unit}"]
                            if highlight_low_points:
                                note_parts.append("低于基线的点已标红")
                            if hide_low_points:
                                note_parts.append(f"已隐藏 {hidden_low_count} 个低于基线的点")
                            st.caption("；".join(note_parts))
                ok_sub, sub_rows = api_get(f"/tasks/{task_uuid}/substep-cycle-series", agg_mode="mean", unit=unit, axis_mode=axis_mode, **scope_params)
                if ok_sub and sub_rows:
                    sub_df = pd.DataFrame(sub_rows)
                    if "x_axis_sort_value" in sub_df.columns:
                        sub_df = sub_df.sort_values(by=["x_axis_sort_value", "series_name"], na_position="last")
                    sub_fig, _ = build_parameter_trend_figure(
                        sub_df,
                        x_col="x_axis_label",
                        y_col="duration_value",
                        series_col="series_name",
                        x_sort_col="x_axis_sort_value",
                        low_value_preference=low_value_reference,
                        highlight_low_points=False,
                        hide_low_points=False,
                    )
                    if sub_fig is not None:
                        render_fig(sub_fig, key=f"substep_cycle_facets_{axis_mode}", height=480, title="Sub-step 趋势")
        else:
            st.error(defs)
        ok_metric, metric_rows = api_get(f"/tasks/{task_uuid}/row-scan-metric-series", unit="ms", axis_mode=axis_mode, **scope_params)
        if ok_metric and metric_rows:
            metric_df = pd.DataFrame(metric_rows)
            if "x_axis_sort_value" in metric_df.columns:
                metric_df = metric_df.sort_values(by=["x_axis_sort_value", "series_name"], na_position="last")
            metric_fig, _ = build_parameter_trend_figure(
                metric_df,
                x_col="x_axis_label",
                y_col="duration_value",
                series_col="series_name",
                x_sort_col="x_axis_sort_value",
                low_value_preference=low_value_reference if 'low_value_reference' in locals() else "优先期望值",
                highlight_low_points=False,
                hide_low_points=False,
            )
            if metric_fig is not None:
                render_fig(metric_fig, key=f"metric_trend_{axis_mode}", height=420, title="Row Scan Metrics 各阶段趋势")
            if st.checkbox("显示 metrics 表格明细", value=False):
                safe_dataframe(metric_df, use_container_width=True, height=280)

elif page == "LLM 诊断":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        st.caption("这里会结合当前日志、上下文、源码片段、历史案例和分析深度策略来生成综合诊断。")
        ok_cfg, cfg = api_get("/config")
        ok_repo_cfg, repo_cfg = api_get("/solution-repository/config")
        ok_errors, rows = api_get(f"/tasks/{task_uuid}/errors", limit=100, offset=0)
        ok_hist, hist_rows = api_get(f"/tasks/{task_uuid}/llm-results", limit=300)

        cfg_data = cfg if ok_cfg and isinstance(cfg, dict) else {}
        repo_cfg_data = repo_cfg if ok_repo_cfg and isinstance(repo_cfg, dict) else {}
        llm_cfg = (cfg_data or {}).get("llm", {})
        depth_cfg = repo_cfg_data.get("analysis_depths", {})
        module_tree = repo_cfg_data.get("module_tree", [])
        module_options = [row.get("name") for row in module_tree if row.get("name")]

        with st.expander("当前策略与开关", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("LLM 启用", "是" if llm_cfg.get("enabled") else "否")
            c2.metric("模型", llm_cfg.get("model") or "-")
            c3.metric("诊断超时(秒)", llm_cfg.get("timeout_seconds") or "-")
            c4.metric("可用深度档位", len(depth_cfg))
            safe_json({"llm": llm_cfg, "solution_repository": repo_cfg_data})

        hist_tab, diagnose_tab, solution_entry_tab, repo_tab, review_tab = st.tabs(["历史诊断", "综合诊断", "已有方案录入", "解决方案库", "审核中心"])

        with hist_tab:
            if ok_hist and hist_rows:
                hist_df = pd.DataFrame(hist_rows)
                show_cols = [c for c in ["normalized_signature", "model_name", "analysis_stage", "prompt_version", "created_at", "llm_status", "elapsed_seconds", "final_total_tokens", "compression_efficiency", "chinese_summary"] if c in hist_df.columns]
                safe_dataframe(hist_df[show_cols], use_container_width=True, height=280)
                unique_sigs = sorted({str(r.get("normalized_signature") or "") for r in hist_rows if r.get("normalized_signature")})
                sig_filter = st.selectbox("按错误签名过滤", ["全部"] + unique_sigs, key="llm_hist_sig_filter")
                filtered_rows = hist_rows if sig_filter == "全部" else [r for r in hist_rows if str(r.get("normalized_signature") or "") == sig_filter]
                labels = [f"{i + 1}. {row.get('normalized_signature', '')} | {row.get('analysis_stage', '-')} | {_display_datetime_text(row.get('created_at'))}" for i, row in enumerate(filtered_rows)]
                if labels:
                    picked = st.selectbox("选择历史结果", labels, key="llm_hist_pick")
                    idx = labels.index(picked)
                    selected_hist = filtered_rows[idx]
                    summary_text = str(selected_hist.get("chinese_summary") or "").strip()
                    if summary_text:
                        st.markdown(
                            _html_block(
                                f"""
                                <article class="diagnosis-summary-card">
                                    <div class="diagnosis-summary-content">{escape(summary_text)}</div>
                                </article>
                                """
                            ),
                            unsafe_allow_html=True,
                        )
                    token_summary = selected_hist.get("token_summary", {}) or {}
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("分析深度", selected_hist.get("analysis_stage", "-"))
                    c2.metric("Prompt 版本", selected_hist.get("prompt_version", "-"))
                    c3.metric("LLM 状态", selected_hist.get("llm_status", "-"))
                    c4.metric("总 Token", token_summary.get("final_total_tokens") or "-")
                    tab1, tab2, tab3, tab4, tab5 = st.tabs(["结构化结果", "上下文摘要", "源码片段", "相似案例", "完整片段"])
                    with tab1:
                        safe_json((selected_hist.get("response_payload") or {}).get("structured_result", selected_hist.get("response_payload", {})))
                    with tab2:
                        safe_json(selected_hist.get("context_summary", {}))
                    with tab3:
                        safe_json(selected_hist.get("source_context_snippets", []))
                    with tab4:
                        safe_json(selected_hist.get("similar_cases", []))
                    with tab5:
                        safe_json(selected_hist)
            else:
                st.info("当前任务还没有历史综合诊断记录。")

        with diagnose_tab:
            if not (ok_errors and rows.get("items")):
                st.info("当前任务暂无可诊断的错误簇。")
            else:
                error_rows = rows["items"]
                error_options = {f"{str(r['display_signature'])[:72]} | count={r['count']}": r for r in error_rows}
                selected_label = st.selectbox("选择错误簇", list(error_options.keys()), key="diag_error_pick")
                selected_row = error_options[selected_label]
                signature = selected_row["normalized_signature"]

                latest_ok, latest_item = api_get(f"/tasks/{task_uuid}/llm-results/latest", normalized_signature=signature)
                if latest_ok:
                    st.caption(f"该错误簇已有历史诊断: {_display_datetime_text(latest_item.get('created_at'))} | {latest_item.get('analysis_stage', '-')} | {latest_item.get('llm_status', '-')}")

                default_depth = "medium" if "medium" in depth_cfg else next(iter(depth_cfg.keys()), "medium")
                depth = st.selectbox("分析深度", list(depth_cfg.keys()) or ["low", "medium", "high"], index=(list(depth_cfg.keys()).index(default_depth) if depth_cfg and default_depth in depth_cfg else 0))
                strategy = depth_cfg.get(depth, {})
                st.caption(f"当前策略: {strategy.get('description', '-')}")
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("上下文预算", strategy.get("token_budget", "-"))
                s2.metric("历史案例数", strategy.get("history_case_limit", "-"))
                s3.metric("源码片段数", strategy.get("max_source_snippets", "-"))
                s4.metric("推理粒度", strategy.get("reasoning_granularity", "-"))

                c1, c2 = st.columns(2)
                module_value = c1.selectbox("所属模块", module_options or ["软件控制"], index=(module_options.index(selected_row.get("component")) if selected_row.get("component") in module_options else 0))
                submodule_value = c2.text_input("子模块", key="diag_submodule")
                trigger_scenario = st.text_area("触发场景", key="diag_trigger_scenario", height=110, placeholder="填写触发条件、操作路径、前置动作、环境信息、复现步骤、客户现象等")
                d1, d2 = st.columns(2)
                operation_path = d1.text_area("操作路径 / 前置动作", key="diag_operation_path", height=90)
                customer_symptom = d2.text_area("客户现象描述", key="diag_customer_symptom", height=90)
                d3, d4 = st.columns(2)
                environment_info = d3.text_area("环境信息", key="diag_environment_info", height=90)
                reproduction_steps = d4.text_area("复现步骤", key="diag_reproduction_steps", height=90)
                source_notes = st.text_area("源码补充说明", key="diag_source_notes", height=80, placeholder="可补充关键类/函数、接口定义、伪代码说明")
                source_uploads = st.file_uploader("上传相关源码", accept_multiple_files=True, key="diag_source_uploads")
                if not st.session_state.get("review_error_name"):
                    st.session_state["review_error_name"] = str(selected_row.get("display_signature", ""))[:80]
                st.caption("“已有方案录入”已拆分为独立子界面，可在上方页签中维护入库信息。")

                sol_error_name = st.session_state.get("review_error_name", "")
                sol_error_category = st.session_state.get("review_error_category", "")
                sol_error_code = st.session_state.get("review_error_code", "")
                sol_impact_scope = st.session_state.get("review_impact_scope", "")
                sol_owner_department = st.session_state.get("review_owner_department", "")
                sol_root_cause = st.session_state.get("review_root_cause", "")
                sol_verified_solution = st.session_state.get("review_verified_solution", "")
                sol_workaround = st.session_state.get("review_workaround", "")
                sol_submitter = st.session_state.get("review_submitter", "")
                sol_reusable = bool(st.session_state.get("review_reusable", True))

                if st.button("检索相似案例", key="find_similar_cases"):
                    ok_sim, sim_rows = api_get(f"/tasks/{task_uuid}/errors/{signature}/similar-cases", module=module_value, trigger_scenario=trigger_scenario or None)
                    if ok_sim:
                        st.session_state["latest_similar_cases"] = sim_rows.get("items", [])
                    else:
                        st.error(sim_rows)
                if st.session_state.get("latest_similar_cases"):
                    st.markdown("#### 相似案例推荐")
                    safe_dataframe(pd.DataFrame(st.session_state.get("latest_similar_cases", [])), use_container_width=True, height=220)

                force = st.checkbox("忽略缓存，重新调用 LLM", value=False)
                default_ui_timeout = int(((cfg_data or {}).get("llm") or {}).get("diagnosis_ui_timeout_seconds") or os.getenv("LLM_DIAGNOSIS_UI_TIMEOUT_SECONDS", 120) or 120)
                diagnose_timeout = st.number_input("前端等待超时(秒)", min_value=30, max_value=300, value=int(default_ui_timeout), step=10)

                if st.button("开始综合诊断", type="primary"):
                    data_payload = {
                        "analysis_depth": depth,
                        "trigger_scenario": trigger_scenario,
                        "module": module_value,
                        "submodule": submodule_value,
                        "environment_info": environment_info,
                        "reproduction_steps": reproduction_steps,
                        "customer_symptom": customer_symptom,
                        "operation_path": operation_path,
                        "source_notes": source_notes,
                        "existing_solution_json": json.dumps(
                            {
                                "error_name": sol_error_name,
                                "error_category": sol_error_category,
                                "error_code": sol_error_code,
                                "impact_scope": sol_impact_scope,
                                "root_cause_analysis": sol_root_cause,
                                "verified_solution": sol_verified_solution,
                                "workaround": sol_workaround,
                                "owner_department": sol_owner_department,
                                "submitter": sol_submitter,
                                "reusable": sol_reusable,
                            },
                            ensure_ascii=False,
                        ),
                    }
                    files_payload = [("source_files", (f.name, f.getvalue(), f.type or "text/plain")) for f in (source_uploads or [])]
                    with st.spinner("正在执行综合诊断，请稍候..."):
                        ok_diag, result = api_post(
                            f"/tasks/{task_uuid}/errors/{signature}/analyze?force={'true' if force else 'false'}",
                            timeout=int(diagnose_timeout),
                            data=data_payload,
                            files=files_payload or None,
                        )
                    if ok_diag:
                        st.session_state["latest_diag_result"] = result
                        st.session_state["latest_diag_signature"] = signature
                    else:
                        st.error(result)

                result = st.session_state.get("latest_diag_result") if st.session_state.get("latest_diag_signature") == signature else None
                if result:
                    st.markdown("### 诊断结论")
                    summary_text = str(result.get("chinese_summary") or "").strip()
                    if summary_text:
                        st.markdown(
                            _html_block(
                                f"""
                                <article class="diagnosis-summary-card">
                                    <div class="diagnosis-summary-content">{escape(summary_text)}</div>
                                </article>
                                """
                            ),
                            unsafe_allow_html=True,
                        )
                    token_summary = result.get("token_summary", {}) or {}
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("分析深度", result.get("analysis_stage", "-"))
                    c2.metric("缓存命中", "是" if result.get("from_cache") else "否")
                    c3.metric("LLM 状态", result.get("llm_status", "-"))
                    c4.metric("总 Token", token_summary.get("final_total_tokens") or "-")
                    tab1, tab2, tab3, tab4, tab5 = st.tabs(["结构化结果", "日志与证据摘要", "源码片段", "相似案例", "请求/响应"])
                    with tab1:
                        safe_json(result.get("structured_result", {}))
                    with tab2:
                        safe_json(result.get("context_summary", {}))
                    with tab3:
                        safe_json(result.get("source_context_snippets", []))
                    with tab4:
                        safe_json(result.get("similar_cases", []))
                    with tab5:
                        safe_json({"request_payload": result.get("request_payload", {}), "response_payload": result.get("response_payload", {})})

                    if st.button("提交入库审核", key="submit_solution_review"):
                        review_payload = {
                            "task_uuid": task_uuid,
                            "submission_type": "solution_record",
                            "error_name": sol_error_name or str(selected_row.get("display_signature", "")),
                            "error_category": sol_error_category,
                            "module": module_value,
                            "submodule": submodule_value,
                            "error_code": sol_error_code,
                            "message": str(selected_row.get("representative_message") or selected_row.get("display_signature") or ""),
                            "normalized_signature": signature,
                            "exception_description": str(selected_row.get("error_family_display") or selected_row.get("error_family") or ""),
                            "trigger_scenario": trigger_scenario,
                            "impact_scope": sol_impact_scope,
                            "report_source": f"task:{task_uuid}",
                            "related_logs": {
                                "display_signature": selected_row.get("display_signature"),
                                "representative_message": selected_row.get("representative_message"),
                                "count": selected_row.get("count"),
                            },
                            "related_source_files": result.get("source_context_snippets", []),
                            "root_cause_analysis": sol_root_cause or (result.get("structured_result", {}) or {}).get("root_cause_summary"),
                            "verified_solution": sol_verified_solution,
                            "workaround": sol_workaround,
                            "owner_department": sol_owner_department or ",".join((result.get("structured_result", {}) or {}).get("owner_departments", [])),
                            "submitter": sol_submitter or "streamlit_ui",
                            "source": "ui_submit_review",
                            "reusable": sol_reusable,
                            "similar_case_refs": [row.get("case_id") for row in result.get("similar_cases", [])],
                            "metadata": {
                                "analysis_depth": depth,
                                "analysis_result": result.get("structured_result", {}),
                                "customer_symptom": customer_symptom,
                                "environment_info": environment_info,
                                "reproduction_steps": reproduction_steps,
                                "operation_path": operation_path,
                            },
                            "attachments": result.get("source_context_snippets", []),
                        }
                        ok_review, review_resp = api_post("/solution-reviews", json=review_payload, timeout=90)
                        if ok_review:
                            st.session_state["latest_review_result"] = review_resp.get("item")
                            clear_cached_api_get()
                        else:
                            st.error(review_resp)

                if st.session_state.get("latest_review_result"):
                    st.markdown("#### 审核结果展示区")
                    safe_json(st.session_state.get("latest_review_result"))

        with solution_entry_tab:
            if not (ok_errors and rows.get("items")):
                st.info("当前任务暂无可录入的错误簇。")
            else:
                error_rows = rows["items"]
                error_options = {f"{str(r['display_signature'])[:72]} | count={r['count']}": r for r in error_rows}
                selected_label = st.selectbox("选择错误簇", list(error_options.keys()), key="solution_entry_error_pick")
                selected_row = error_options[selected_label]
                if not st.session_state.get("review_error_name"):
                    st.session_state["review_error_name"] = str(selected_row.get("display_signature", ""))[:80]

                st.caption("这个子界面专门维护已有方案录入内容，综合诊断提交审核时会直接复用这里的字段。")
                r1, r2, r3 = st.columns(3)
                r1.text_input("错误名", key="review_error_name")
                r2.text_input("错误类别", key="review_error_category")
                r3.text_input("错误码", key="review_error_code")
                r4, r5 = st.columns(2)
                r4.text_area("影响范围", key="review_impact_scope", height=80)
                r5.text_input("责任部门", key="review_owner_department")
                st.text_area("根因分析", key="review_root_cause", height=100)
                st.text_area("已验证解决方案", key="review_verified_solution", height=100)
                st.text_area("临时绕过方案", key="review_workaround", height=80)
                r6, r7 = st.columns(2)
                r6.text_input("提交人 / 来源", key="review_submitter")
                r7.checkbox("是否可复用", value=True, key="review_reusable")

        with repo_tab:
            q1, q2, q3 = st.columns(3)
            repo_search = q1.text_input("关键词搜索", key="repo_search")
            repo_module = q2.selectbox("按模块筛选", [""] + module_options, key="repo_module_filter")
            repo_review_status = q3.selectbox("审核状态", ["", "approved", "needs_revision", "rejected"], key="repo_review_filter")
            ok_repo, repo_rows = api_get("/solution-repository/records", search=repo_search or None, module=repo_module or None, review_status=repo_review_status or None, limit=200)
            if ok_repo:
                items = repo_rows.get("items", [])
                safe_dataframe(pd.DataFrame(items), use_container_width=True, height=280)
                st.markdown("#### 导出解决方案数据")
                st.markdown(f"[导出 JSON]({_api_base()}/solution-repository/export?format=json{_auth_query_suffix()})")
                st.markdown(f"[导出 CSV]({_api_base()}/solution-repository/export?format=csv{_auth_query_suffix()})")
                st.markdown(f"[导出 Excel]({_api_base()}/solution-repository/export?format=xlsx{_auth_query_suffix()})")
                st.markdown(f"[导出 SQLite 备份]({_api_base()}/solution-repository/export?format=sqlite{_auth_query_suffix()})")
                if items:
                    labels = [f"{row['id']} | {row.get('error_name', '')} | {row.get('module', '')}" for row in items]
                    picked = st.selectbox("选择记录进行编辑", labels, key="repo_edit_pick")
                    edit_row = items[labels.index(picked)]
                    e1, e2 = st.columns(2)
                    edit_root = e1.text_area("编辑根因分析", value=edit_row.get("root_cause_analysis") or "", key=f"edit_root_{edit_row['id']}", height=100)
                    edit_solution = e2.text_area("编辑已验证解决方案", value=edit_row.get("verified_solution") or "", key=f"edit_solution_{edit_row['id']}", height=100)
                    edit_workaround = st.text_area("编辑临时绕过方案", value=edit_row.get("workaround") or "", key=f"edit_workaround_{edit_row['id']}", height=80)
                    edit_reusable = st.checkbox("可复用", value=bool(edit_row.get("reusable")), key=f"edit_reusable_{edit_row['id']}")
                    if st.button("保存当前记录编辑", key=f"save_repo_record_{edit_row['id']}"):
                        payload = {
                            **edit_row,
                            "root_cause_analysis": edit_root,
                            "verified_solution": edit_solution,
                            "workaround": edit_workaround,
                            "reusable": edit_reusable,
                        }
                        ok_update, resp_update = api_put(f"/solution-repository/records/{edit_row['id']}", payload)
                        if ok_update:
                            st.success("记录已更新")
                            clear_cached_api_get()
                            st.rerun()
                        else:
                            st.error(resp_update)
            else:
                st.error(repo_rows)

        with review_tab:
            review_status_filter = st.selectbox("审核列表筛选", ["", "pending_review", "approved", "needs_revision", "rejected"], key="solution_review_status_filter")
            ok_reviews, review_rows = api_get("/solution-reviews", status=review_status_filter or None, limit=200)
            if ok_reviews:
                items = review_rows.get("items", [])
                safe_dataframe(pd.DataFrame(items), use_container_width=True, height=260)
                if items:
                    labels = [f"{row['id']} | {row.get('review_status', '')} | {row.get('module', '')} | {row.get('normalized_signature', '')}" for row in items]
                    selected_label = st.selectbox("选择待审核记录", labels, key="review_pick")
                    selected_review = items[labels.index(selected_label)]
                    safe_json(selected_review)
                    reviewer = st.text_input("人工复核人", key="manual_reviewer")
                    notes = st.text_area("审核意见", key="manual_review_notes", height=90)
                    m1, m2, m3 = st.columns(3)
                    if m1.button("人工通过", key="manual_review_approved"):
                        ok_manual, resp_manual = api_post(f"/solution-reviews/{selected_review['id']}/manual-review", json={"review_status": "approved", "reviewer": reviewer, "notes": notes}, timeout=60)
                        if ok_manual:
                            st.success("已人工通过并写入案例库")
                            clear_cached_api_get()
                            st.rerun()
                        else:
                            st.error(resp_manual)
                    if m2.button("退回修改", key="manual_review_revision"):
                        ok_manual, resp_manual = api_post(f"/solution-reviews/{selected_review['id']}/manual-review", json={"review_status": "needs_revision", "reviewer": reviewer, "notes": notes}, timeout=60)
                        if ok_manual:
                            st.success("已标记为 needs_revision")
                            clear_cached_api_get()
                            st.rerun()
                        else:
                            st.error(resp_manual)
                    if m3.button("拒绝入库", key="manual_review_rejected"):
                        ok_manual, resp_manual = api_post(f"/solution-reviews/{selected_review['id']}/manual-review", json={"review_status": "rejected", "reviewer": reviewer, "notes": notes}, timeout=60)
                        if ok_manual:
                            st.success("已拒绝入库")
                            clear_cached_api_get()
                            st.rerun()
                        else:
                            st.error(resp_manual)
            else:
                st.error(review_rows)

elif page == "原始文件预览":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        paged_table(f"/tasks/{task_uuid}/files", page_key="files_page", page_size_key="files_page_size", title="原始文件列表", default_page_size=100, max_page_size=500)
        ok, files_page = api_get(f"/tasks/{task_uuid}/files", limit=500, offset=0)
        items = files_page.get("items", []) if ok else []
        if items:
            selected_file = st.selectbox("选择原始文件", [r["relative_path"] for r in items])
            max_lines = st.slider("预览行数", 20, 500, 120, 20)
            if st.button("加载原始文件预览"):
                ok2, preview = api_get(f"/tasks/{task_uuid}/files/preview", relative_path=selected_file, max_lines=max_lines)
                if ok2:
                    st.caption(f"文件: {preview.get('relative_path')} | 类型: {preview.get('mime_type', 'unknown')} | 编码: {preview.get('encoding', 'unknown')} | 预览行数: {preview.get('line_count')}")
                    st.code("\n".join(preview.get("preview", [])))
                else:
                    st.error(preview)


elif page == "未知日志待标注池":
    st.subheader("未知日志待标注池")
    st.caption("这里收集所有尚未命中 parser / parser_rules 的日志簇，建议先按出现次数筛选，再查看代表样本与上下文。")
    c1, c2, c3 = st.columns([1,1,1])
    min_occurrence = c1.number_input("最小出现次数", min_value=1, value=1, step=1)
    limit = c2.number_input("展示条数", min_value=10, max_value=500, value=100, step=10)
    review_filter = c3.selectbox("审核状态过滤", ["", "pending_review", "submitted_for_review", "approved", "rejected", "ignored"])
    ok, data = api_get("/active-learning/unknown-clusters", min_occurrence=int(min_occurrence), limit=int(limit), review_status=review_filter or None)
    if ok:
        items = data.get("items", [])
        if not items:
            st.info("当前没有未知日志待标注样本。")
        else:
            df = pd.DataFrame(items)
            show_cols = [c for c in ["signature", "occurrence_count", "representative_source_file", "representative_timestamp", "review_status", "first_seen_at", "last_seen_at", "failure_reasons"] if c in df.columns]
            safe_dataframe(df[show_cols], use_container_width=True, height=320)
            sigs = df["signature"].tolist()
            selected_sig = st.selectbox("选择一个未知日志簇查看详情", sigs)
            row = next((x for x in items if x.get("signature") == selected_sig), None)
            if row:
                c1, c2, c3 = st.columns(3)
                c1.metric("当前状态", row.get("review_status", "pending_review"))
                c2.metric("出现次数", row.get("occurrence_count", 0))
                c3.metric("源文件数", _safe_len(row.get("source_files")))
                st.markdown("### 代表性样本")
                st.code(str(row.get("representative_text") or ""))
                render_review_actions("unknown_cluster", f"/active-learning/unknown-clusters/{selected_sig}/review", reviewer_key="unknown_reviewer", notes_key="unknown_notes")
                if row.get("review_history"):
                    with st.expander("审核历史", expanded=False):
                        safe_dataframe(pd.DataFrame(row.get("review_history") or []), use_container_width=True, height=180)
                col1, col2 = st.columns(2)
                col1.markdown("#### 尝试过的 Parsers")
                safe_json(row.get("attempted_parsers") or [])
                col2.markdown("#### 尝试过的 Rules")
                safe_json(row.get("attempted_rules") or [])
                st.markdown("#### 上下文样本")
                examples = row.get("context_examples") or []
                for i, ex in enumerate(examples[:10], start=1):
                    with st.expander(f"样本 {i} | {ex.get('source_file')} | line {ex.get('line_no')}", expanded=False):
                        safe_json(ex)
    else:
        st.error(data)

elif page == "规则建议审核视图":
    st.subheader("规则建议审核视图")
    st.caption("先看本地规则建议，再按需触发 LLM 候选建议；所有建议都只进入审核流，不会直接改生产规则。")
    llm_switch = st.checkbox("启用 LLM 规则建议", value=False, help="只生成候选建议，不会写入生产规则")
    llm_force_refresh = st.checkbox("忽略 LLM 预览缓存并重新生成", value=False, help="默认优先读取最近一次 LLM 预览缓存")
    ok_unknown_pool, unknown_pool = api_get("/active-learning/unknown-clusters", min_occurrence=1, limit=200)
    selected_llm_signatures = []
    if llm_switch:
        with st.expander("选择要送入 LLM 的未知日志簇", expanded=True):
            st.caption("建议只勾选当前最需要补规则的未知日志簇，以减少无关上下文。")
            unknown_items = unknown_pool.get("items", []) if ok_unknown_pool else []
            if unknown_items:
                options = []
                label_to_sig = {}
                for row in unknown_items:
                    sig = str(row.get("signature") or "")
                    label = f"{sig} | count={row.get('occurrence_count', 0)} | {str(row.get('representative_text', ''))[:90]}"
                    options.append(label)
                    label_to_sig[label] = sig
                picked_labels = st.multiselect("未知日志簇", options, default=options[:min(3, len(options))], key="llm_unknown_signature_pick")
                selected_llm_signatures = [label_to_sig[x] for x in picked_labels if x in label_to_sig]
                st.caption(f"当前已选择 {len(selected_llm_signatures)} 个未知日志簇用于 LLM 规则建议。")
            else:
                st.info("当前没有可供选择的未知日志簇，将无法生成定向 LLM 规则建议。")
    ok_prev, preview = api_get("/active-learning/rule-suggestions/preview", use_llm=False)
    if llm_switch and st.button("生成/刷新 LLM 规则建议", key="refresh_llm_rule_preview"):
        st.session_state["rule_preview_fetch_llm"] = True
    fetch_llm_now = bool(st.session_state.pop("rule_preview_fetch_llm", False))
    llm_preview = None
    if fetch_llm_now and llm_switch:
        with st.spinner("正在生成 LLM 候选规则建议..."):
            ok_llm, llm_preview = api_get("/active-learning/rule-suggestions/preview", use_llm=True, force_refresh=llm_force_refresh, selected_signatures=','.join(selected_llm_signatures) if selected_llm_signatures else None)
            if not ok_llm:
                st.error(llm_preview)
                llm_preview = None

    ok_files, files = api_get("/active-learning/rule-suggestions/files")
    ok_reviews, reviews = api_get("/active-learning/rule-suggestions/reviews")
    if ok_prev:
        summary = preview.get("summary", {})
        llm_meta = (llm_preview or preview).get("llm_assisted", {}) if (llm_preview or preview) else {}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("未知簇总数", summary.get("unknown_clusters_total", 0))
        c2.metric("反馈记录总数", summary.get("feedback_records_total", 0))
        c3.metric("新规则建议", summary.get("new_rule_suggestions", 0))
        c4.metric("修正规则建议", summary.get("rule_fix_suggestions", 0))
        with st.expander("LLM 规则建议状态", expanded=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("LLM 开关可用", "是" if llm_meta.get("switch_enabled") else "否")
            m2.metric("本次请求 LLM", "是" if llm_meta.get("requested") else "否")
            m3.metric("LLM 实际生效", "是" if llm_meta.get("used") else ("降级本地" if llm_meta.get("fallback_to_local") else "否"))
            m4.metric("LLM 预览缓存", "命中" if llm_meta.get("from_cache") else "实时")
            if llm_switch:
                st.caption(f"本次 LLM 规则建议仅使用所选未知日志簇: {llm_meta.get('selected_unknown_cluster_count', 0)} 个。")
            safe_json({
                "switch_enabled": llm_meta.get("switch_enabled"),
                "requested": llm_meta.get("requested"),
                "used": llm_meta.get("used"),
                "fallback_to_local": llm_meta.get("fallback_to_local"),
                "from_cache": llm_meta.get("from_cache"),
                "cache_ttl_seconds": llm_meta.get("cache_ttl_seconds"),
                "timeout_seconds": llm_meta.get("timeout_seconds"),
                "max_retries": llm_meta.get("max_retries"),
                "max_unknown_samples": llm_meta.get("max_unknown_samples"),
                "max_feedback_samples": llm_meta.get("max_feedback_samples"),
                "max_parser_snippets": llm_meta.get("max_parser_snippets"),
                "selected_signatures": llm_meta.get("selected_signatures"),
                "selected_unknown_cluster_count": llm_meta.get("selected_unknown_cluster_count"),
            })

        tabs = st.tabs(["本地新规则建议", "本地修正规则建议", "LLM 新规则建议", "LLM 修正规则建议", "高频误判模式", "YAML 候选片段", "审核记录", "已写入建议文件", "LLM 请求/响应"])
        local_new = preview.get("new_rule_suggestions", [])
        local_fix = preview.get("rule_fix_suggestions", [])
        effective_preview = llm_preview or preview
        effective_llm_meta = effective_preview.get("llm_assisted", {}) if effective_preview else {}
        llm_new = (effective_llm_meta.get("result") or {}).get("new_rule_suggestions", [])
        llm_fix = (effective_llm_meta.get("result") or {}).get("rule_fix_suggestions", [])
        patterns = preview.get("high_frequency_misclassified_patterns", [])
        llm_patterns = (effective_llm_meta.get("result") or {}).get("high_frequency_misclassified_patterns", [])

        with tabs[0]:
            if local_new:
                safe_dataframe(pd.DataFrame(local_new), use_container_width=True, height=320)
                pick = st.selectbox("选择本地新规则建议", [x.get("suggestion_id") for x in local_new], key="local_new_pick")
                row = next((x for x in local_new if x.get("suggestion_id") == pick), None)
                if row:
                    safe_json(row)
                    render_review_actions("local_new_rule", f"/active-learning/rule-suggestions/{pick}/review", reviewer_key="local_new_rule_reviewer", notes_key="local_new_rule_notes")
            else:
                st.info("暂无本地新规则建议。")
        with tabs[1]:
            if local_fix:
                safe_dataframe(pd.DataFrame(local_fix), use_container_width=True, height=320)
                pick = st.selectbox("选择本地修正规则建议", [x.get("suggestion_id") for x in local_fix], key="local_fix_pick")
                row = next((x for x in local_fix if x.get("suggestion_id") == pick), None)
                if row:
                    safe_json(row)
                    render_review_actions("local_fix_rule", f"/active-learning/rule-suggestions/{pick}/review", reviewer_key="local_fix_rule_reviewer", notes_key="local_fix_rule_notes")
            else:
                st.info("暂无本地修正规则建议。")
        with tabs[2]:
            if llm_switch and llm_new:
                safe_dataframe(pd.DataFrame(llm_new), use_container_width=True, height=320)
                pick = st.selectbox("选择 LLM 新规则建议", [x.get("suggestion_id") for x in llm_new], key="llm_new_pick")
                row = next((x for x in llm_new if x.get("suggestion_id") == pick), None)
                if row:
                    safe_json(row)
                    render_review_actions("llm_new_rule", f"/active-learning/rule-suggestions/{pick}/review", reviewer_key="llm_new_rule_reviewer", notes_key="llm_new_rule_notes")
            elif llm_switch:
                st.info("当前没有 LLM 新规则建议；如刚开启开关，可点击上方按钮生成。")
            else:
                st.info("尚未启用 LLM 规则建议。")
        with tabs[3]:
            if llm_switch and llm_fix:
                safe_dataframe(pd.DataFrame(llm_fix), use_container_width=True, height=320)
                pick = st.selectbox("选择 LLM 修正规则建议", [x.get("suggestion_id") for x in llm_fix], key="llm_fix_pick")
                row = next((x for x in llm_fix if x.get("suggestion_id") == pick), None)
                if row:
                    safe_json(row)
                    render_review_actions("llm_fix_rule", f"/active-learning/rule-suggestions/{pick}/review", reviewer_key="llm_fix_rule_reviewer", notes_key="llm_fix_rule_notes")
            elif llm_switch:
                st.info("当前没有 LLM 修正规则建议；如刚开启开关，可点击上方按钮生成。")
            else:
                st.info("尚未启用 LLM 规则建议。")
        with tabs[4]:
            rows = patterns + llm_patterns
            if rows:
                safe_dataframe(pd.DataFrame(rows), use_container_width=True, height=320)
            else:
                st.info("暂无高频误判模式。")
        with tabs[5]:
            safe_text = yaml.safe_dump(preview.get("parser_rules_yaml_fragment", {}), allow_unicode=True, sort_keys=False)
            st.code(safe_text, language="yaml")
            llm_fragment = ((effective_llm_meta.get("result") or {}).get("parser_rules_yaml_fragment") or {})
            if llm_fragment:
                st.markdown("#### LLM 候选 YAML 片段")
                st.code(yaml.safe_dump(llm_fragment, allow_unicode=True, sort_keys=False), language="yaml")
            st.caption("所有建议均为 review-only，不会自动覆盖生产 parser_rules.yaml。")
        with tabs[6]:
            review_items = reviews.get("items", []) if ok_reviews else []
            if review_items:
                safe_dataframe(pd.DataFrame(review_items), use_container_width=True, height=280)
            else:
                st.info("暂无规则建议审核记录。")
        with tabs[7]:
            file_items = files.get("items", []) if ok_files else []
            if file_items:
                safe_dataframe(pd.DataFrame(file_items), use_container_width=True, height=240)
                selected_file = st.selectbox("选择建议文件", [x["filename"] for x in file_items])
                ok_file, file_content = api_get("/active-learning/rule-suggestions/file", filename=selected_file)
                if ok_file:
                    st.code(file_content.get("content", ""), language="yaml")
                else:
                    st.error(file_content)
            else:
                st.info("当前没有已写入的建议文件。可先运行 scripts/learn_parser_rules.py --write。")
        with tabs[8]:
            if llm_switch:
                safe_json({
                    "request_payload": effective_llm_meta.get("request_payload", {}),
                    "response_payload": effective_llm_meta.get("response_payload", {}),
                })
            else:
                st.info("启用 LLM 规则建议后，可在这里查看请求与响应摘要。")
    else:
        st.error(preview)

elif page == "配置页面":
    ok, data = api_get("/config")
    if ok:
        thresholds = data.get("thresholds", {}) if isinstance(data.get("thresholds"), dict) else {}
        parser_rules = data.get("parser_rules", {}) if isinstance(data.get("parser_rules"), dict) else {}
        error_rules = data.get("error_rules", {}) if isinstance(data.get("error_rules"), dict) else {}
        prompt_templates = data.get("prompt_templates", {}) if isinstance(data.get("prompt_templates"), dict) else {}
        llm_cfg = data.get("llm", {}) if isinstance(data.get("llm"), dict) else {}
        repo_cfg = data.get("solution_repository", {}) if isinstance(data.get("solution_repository"), dict) else {}

        step_thresholds = thresholds.get("step_thresholds_ms", {}) if isinstance(thresholds.get("step_thresholds_ms"), dict) else {}
        parameter_thresholds = thresholds.get("parameter_thresholds_seconds", {}) if isinstance(thresholds.get("parameter_thresholds_seconds"), dict) else {}
        parameter_expected = thresholds.get("parameter_expected_seconds", {}) if isinstance(thresholds.get("parameter_expected_seconds"), dict) else {}
        threshold_llm_context = thresholds.get("llm_context", {}) if isinstance(thresholds.get("llm_context"), dict) else {}

        prompt_versions = prompt_templates.get("templates", {}) if isinstance(prompt_templates.get("templates"), dict) else {}
        active_prompt_version = prompt_templates.get("active_version")
        active_learning = parser_rules.get("active_learning", {}) if isinstance(parser_rules.get("active_learning"), dict) else {}
        family_rules = error_rules.get("family_rules", []) if isinstance(error_rules.get("family_rules"), list) else []
        component_rules = parser_rules.get("component_filename_rules", {}) if isinstance(parser_rules.get("component_filename_rules"), dict) else {}
        module_tree = repo_cfg.get("module_tree", []) if isinstance(repo_cfg.get("module_tree"), list) else []
        module_prefixes = repo_cfg.get("module_prefixes", {}) if isinstance(repo_cfg.get("module_prefixes"), dict) else {}

        step_threshold_count = sum(len(items) for items in step_thresholds.values() if isinstance(items, dict))
        template_count = len(prompt_versions)
        module_count = len(module_tree)
        submodule_count = sum(len(item.get("children") or []) for item in module_tree if isinstance(item, dict))

        render_stat_cards(
            [
                {"icon": "clock", "label": "步骤级阈值", "value": step_threshold_count, "note": "业务步骤已配置的时间阈值数量"},
                {"icon": "sliders", "label": "参数判定项", "value": len(parameter_thresholds), "note": "用于性能判断的参数阈值项"},
                {"icon": "alert", "label": "异常家族", "value": len(family_rules), "note": "当前异常归类与识别规则数量"},
                {"icon": "brain", "label": "Prompt 模板", "value": template_count, "note": f"当前启用: {_display_config_value(active_prompt_version)}"},
            ]
        )

        config_tab_labels = ["总览", "时间与阈值", "异常与审核", "Prompt 与方案库"]
        if bool(current_user.get("is_admin")):
            config_tab_labels.append("Env 配置")
        config_tabs = st.tabs(config_tab_labels)
        overview_tab, threshold_tab, rules_tab, knowledge_tab = config_tabs[:4]
        admin_env_tab = config_tabs[4] if len(config_tabs) > 4 else None

        with overview_tab:
            st.markdown("#### 基础信息")
            render_info_tiles(
                [
                    {"label": "默认超时阈值", "value": thresholds.get("default_threshold_ms"), "note": "未命中步骤细分阈值时的统一兜底值，单位 ms"},
                    {"label": "LLM 诊断开关", "value": llm_cfg.get("enabled"), "note": "控制诊断页面是否启用大模型分析"},
                    {"label": "诊断模型", "value": llm_cfg.get("model"), "note": "当前用于综合诊断的模型名称"},
                    {"label": "提示词版本", "value": active_prompt_version, "note": "当前生效的 Prompt 模板版本"},
                    {"label": "解决方案模块", "value": module_count, "note": f"共覆盖 {submodule_count} 个子模块"},
                    {"label": "组件映射规则", "value": len(component_rules), "note": "用于从文件名归类组件来源的规则数"},
                ],
                columns=3,
            )

            st.markdown("#### 时间记录与资源预算")
            render_info_tiles(
                [
                    {"label": "LLM 超时", "value": llm_cfg.get("timeout_seconds"), "note": "单次诊断请求最长等待时间，单位秒"},
                    {"label": "重试次数", "value": llm_cfg.get("max_retries"), "note": "诊断失败后的自动重试上限"},
                    {"label": "上下文时间窗", "value": (llm_cfg.get("context") or {}).get("time_window_seconds"), "note": "诊断上下文关联日志的时间窗口，单位秒"},
                    {"label": "Token 预算", "value": (llm_cfg.get("context") or {}).get("max_token_budget"), "note": "单次诊断可使用的上下文 Token 上限"},
                    {"label": "预览缓存", "value": (llm_cfg.get("preview") or {}).get("cache_ttl_seconds"), "note": "预览缓存有效期，单位秒"},
                    {"label": "预览样本上限", "value": (llm_cfg.get("preview") or {}).get("max_unknown_samples"), "note": "单次预览纳入的未知日志样本数"},
                ],
                columns=3,
            )

            st.markdown("#### 审核信息与学习策略")
            render_info_tiles(
                [
                    {"label": "主动学习", "value": active_learning.get("enabled"), "note": "统一控制未知日志聚类、反馈学习与建议生成"},
                    {"label": "未知日志聚类", "value": (active_learning.get("unknown_handling") or {}).get("enabled"), "note": "将未命中规则的日志按相似性聚合"},
                    {"label": "反馈学习", "value": (active_learning.get("feedback_learning") or {}).get("enabled"), "note": "把人工反馈沉淀为可复用数据"},
                    {"label": "规则建议生成", "value": (active_learning.get("suggestion_generation") or {}).get("enabled"), "note": "基于聚类与反馈自动形成规则建议"},
                    {"label": "建议需审核", "value": (active_learning.get("suggestion_generation") or {}).get("review_required"), "note": "建议写入前是否必须人工审核"},
                    {"label": "LLM 建议仅审核模式", "value": (active_learning.get("llm_suggestion") or {}).get("force_review_only"), "note": "LLM 输出是否只进入审核流，不直接生效"},
                ],
                columns=3,
            )

        with threshold_tab:
            st.markdown("#### 时间记录与阈值维护")
            st.caption("通过表格和表单维护阈值配置，避免直接编辑整段 YAML。")

            default_threshold_ms = st.number_input(
                "默认超时阈值 (ms)",
                min_value=0,
                value=int(_coerce_numeric_value(thresholds.get("default_threshold_ms")) or 0),
                step=100,
            )

            parameter_cols = st.columns(2, gap="large")
            with parameter_cols[0]:
                st.markdown("##### 参数阈值")
                edited_parameter_thresholds = st.data_editor(
                    pd.DataFrame(_rows_from_mapping(parameter_thresholds, "参数项", "阈值(秒)")),
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    key="config_parameter_thresholds",
                )
            with parameter_cols[1]:
                st.markdown("##### 参数期望值")
                edited_parameter_expected = st.data_editor(
                    pd.DataFrame(_rows_from_mapping(parameter_expected, "参数项", "期望(秒)")),
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    key="config_parameter_expected",
                )

            st.markdown("##### 步骤级阈值")
            edited_step_thresholds = st.data_editor(
                pd.DataFrame(_rows_from_nested_mapping(step_thresholds, "业务模块", "步骤名称", "超时阈值(ms)")),
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="config_step_thresholds",
            )

            st.markdown("##### 诊断上下文窗口")
            edited_threshold_context = st.data_editor(
                pd.DataFrame(_rows_from_mapping(threshold_llm_context, "上下文项", "值")),
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="config_threshold_context",
            )

            if st.button("保存阈值配置", type="primary"):
                payload = {
                    "default_threshold_ms": int(default_threshold_ms),
                    "step_thresholds_ms": _nested_mapping_from_editor_rows(edited_step_thresholds, "业务模块", "步骤名称", "超时阈值(ms)"),
                    "parameter_thresholds_seconds": _mapping_from_editor_rows(edited_parameter_thresholds, "参数项", "阈值(秒)"),
                    "parameter_expected_seconds": _mapping_from_editor_rows(edited_parameter_expected, "参数项", "期望(秒)"),
                    "llm_context": _mapping_from_editor_rows(edited_threshold_context, "上下文项", "值"),
                }
                ok2, resp = api_put("/config/thresholds", payload)
                if ok2:
                    st.success("阈值配置已保存")
                    clear_cached_api_get()
                    st.rerun()
                else:
                    st.error(resp)

        with rules_tab:
            st.markdown("#### 异常识别信息")
            render_info_tiles(
                [
                    {"label": "时间格式规则", "value": len(parser_rules.get("time_formats") or []), "note": "日志时间字段的识别格式数"},
                    {"label": "Cycle 提取规则", "value": len(parser_rules.get("cycle_patterns") or []), "note": "从文本中定位 Cycle 的模式数"},
                    {"label": "Chip 提取规则", "value": len(parser_rules.get("chip_patterns") or []), "note": "识别芯片/载片标识的模式数"},
                    {"label": "回退异常家族", "value": error_rules.get("fallback_family"), "note": "未命中具体家族时的默认归类"},
                ],
                columns=4,
            )

            parser_cols = st.columns(2, gap="large")
            with parser_cols[0]:
                st.markdown("##### 时间格式")
                render_tag_cloud(parser_rules.get("time_formats") or [], empty_text="未配置时间格式")
                st.markdown("##### Cycle 识别")
                render_tag_cloud(parser_rules.get("cycle_patterns") or [], empty_text="未配置 Cycle 识别模式")
            with parser_cols[1]:
                st.markdown("##### Chip 识别")
                render_tag_cloud(parser_rules.get("chip_patterns") or [], empty_text="未配置 Chip 识别模式")
                st.markdown("##### 文件来源映射")
                safe_dataframe(
                    [{"组件名称": key, "文件标识": value} for key, value in component_rules.items()],
                    use_container_width=True,
                    height=280,
                )

            st.markdown("#### 审核与建议生成策略")
            render_info_tiles(
                [
                    {
                        "label": "未知日志最小分值",
                        "value": ((active_learning.get("unknown_handling") or {}).get("min_score_threshold")),
                        "note": "低于该值的候选样本不会纳入未知日志池",
                    },
                    {
                        "label": "上下文窗口行数",
                        "value": ((active_learning.get("unknown_handling") or {}).get("context_window_lines")),
                        "note": "未知日志聚类时附带的上下文行数",
                    },
                    {
                        "label": "未知样本触发建议",
                        "value": ((active_learning.get("suggestion_generation") or {}).get("min_unknown_occurrence_for_suggestion")),
                        "note": "同类未知日志累计达到该次数才生成建议",
                    },
                    {
                        "label": "反馈样本触发建议",
                        "value": ((active_learning.get("suggestion_generation") or {}).get("min_feedback_occurrence_for_suggestion")),
                        "note": "同类反馈累计达到该次数才生成建议",
                    },
                    {
                        "label": "建议代表样本",
                        "value": ((active_learning.get("suggestion_generation") or {}).get("max_representative_samples_per_cluster")),
                        "note": "每个簇最多选取多少条样本用于规则建议",
                    },
                    {
                        "label": "LLM 建议超时",
                        "value": ((active_learning.get("llm_suggestion") or {}).get("timeout_seconds")),
                        "note": "LLM 建议生成请求超时时间，单位秒",
                    },
                ],
                columns=3,
            )

            st.markdown("#### 异常家族")
            family_columns = st.columns(2, gap="large")
            for index, family in enumerate(family_rules):
                label = family.get("label") or family.get("key") or f"规则 {index + 1}"
                patterns = family.get("patterns") or []
                with family_columns[index % 2]:
                    st.markdown(f"##### {label}")
                    st.caption(f"{family.get('key', '-')} | 匹配模式 {len(patterns)} 条")
                    st.write(_preview_config_text(family.get("description"), limit=220))
                    render_tag_cloud(patterns, empty_text="当前未配置匹配模式")

        with knowledge_tab:
            st.markdown("#### Prompt 模板")
            render_text_panels(
                [
                    {
                        "badge": "当前启用" if version == active_prompt_version else "候选模板",
                        "title": f"{version} · {template.get('name') or '未命名模板'}",
                        "body": template.get("analysis_policy") or template.get("system_prompt"),
                        "note": template.get("system_prompt"),
                    }
                    for version, template in prompt_versions.items()
                    if isinstance(template, dict)
                ],
                columns=2,
            )

            st.markdown("#### 诊断深度与评分信息")
            analysis_depths = llm_cfg.get("analysis_depths", {}) if isinstance(llm_cfg.get("analysis_depths"), dict) else {}
            render_text_panels(
                [
                    {
                        "badge": depth_key,
                        "title": depth_config.get("label") or depth_key,
                        "body": depth_config.get("description"),
                        "note": f"Token 预算 {_display_config_value(depth_config.get('token_budget'))} | 历史案例 {_display_config_value(depth_config.get('history_case_limit'))} | 源码片段 {_display_config_value(depth_config.get('max_source_snippets'))}",
                    }
                    for depth_key, depth_config in analysis_depths.items()
                    if isinstance(depth_config, dict)
                ],
                columns=3,
            )

            st.markdown("#### 解决方案知识库")
            render_info_tiles(
                [
                    {"label": "模块前缀数", "value": len(module_prefixes), "note": "错误码前缀与业务模块的映射数量"},
                    {"label": "一级模块", "value": module_count, "note": "方案库当前覆盖的一级业务模块"},
                    {"label": "子模块", "value": submodule_count, "note": "方案库中维护的细分子模块总量"},
                    {"label": "建议输出目录", "value": (active_learning.get("suggestion_generation") or {}).get("write_suggestions_to"), "note": "规则建议最终写入位置"},
                ],
                columns=4,
            )

            for module in module_tree:
                if not isinstance(module, dict):
                    continue
                module_name = module.get("name") or "未命名模块"
                children = module.get("children") or []
                module_prefix = module_prefixes.get(module_name)
                with st.expander(f"{module_name} · {len(children)} 个子模块", expanded=False):
                    render_info_tiles(
                        [
                            {"label": "错误码前缀", "value": module_prefix, "note": "用于规范解决方案错误码命名"},
                            {"label": "子模块数量", "value": len(children), "note": "当前业务模块下可挂载的子模块数"},
                        ],
                        columns=2,
                    )
                    render_tag_cloud(children, empty_text="当前未配置子模块")

        if admin_env_tab is not None:
            with admin_env_tab:
                render_admin_env_config_panel(llm_cfg)
    else:
        st.error(data)

elif page == "导出":
    if task_uuid:
        st.markdown(f"[导出统一事件 CSV]({_api_base()}/tasks/{task_uuid}/export/events?access_token={st.session_state.get('auth_token','')})")
        st.markdown(f"[导出错误分析 CSV]({_api_base()}/tasks/{task_uuid}/export/errors?access_token={st.session_state.get('auth_token','')})")
        st.markdown(f"[导出参数结果 CSV]({_api_base()}/tasks/{task_uuid}/export/parameters?access_token={st.session_state.get('auth_token','')})")
        st.markdown(f"[导出统一 HTML 报告]({_api_base()}/tasks/{task_uuid}/export/report.html?access_token={st.session_state.get('auth_token','')})")
        st.markdown(f"[导出 JSON 报告]({_api_base()}/tasks/{task_uuid}/export/report.json?access_token={st.session_state.get('auth_token','')})")
        st.markdown(f"[导出 Excel 报告]({_api_base()}/tasks/{task_uuid}/export/report.xlsx?access_token={st.session_state.get('auth_token','')})")
        st.markdown(f"[导出 PDF 报告]({_api_base()}/tasks/{task_uuid}/export/report.pdf?access_token={st.session_state.get('auth_token','')})")
    else:
        st.info("请先选择任务 UUID。")

