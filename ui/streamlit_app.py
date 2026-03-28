from __future__ import annotations

import json
import math
import os
import textwrap
from html import escape
from typing import Any, cast

from app.core.bootstrap import bootstrap_for_local_run
bootstrap_for_local_run()

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import yaml

st.set_page_config(page_title="测序仪日志整理及问题反馈系统", layout="wide")

DEFAULT_API_BASE = os.getenv("STREAMLIT_API_BASE", "http://127.0.0.1:8000/api/v1")
DURATION_UNITS = {"毫秒(ms)": "ms", "秒(s)": "s", "分钟(min)": "min", "小时(h)": "h"}
PLOTLY_COLOR_SEQUENCE = ["#052659", "#0B5CAD", "#5483B3", "#7DA0CA", "#38A3E0", "#C1E8FF"]
ERROR_SEVERITY_COLORS = {
    "fatal": "#8C1C13",
    "error": "#D94841",
    "warn": "#D96B3B",
    "warning": "#D96B3B",
    "info": "#5B7C99",
    "unknown": "#7A7A7A",
}
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

    red, green, blue = _hex_to_rgb(color)
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


def inject_design_system():
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
        [data-testid="stBaseButton-primary"] {
            min-height: 2.85rem;
            border-radius: 999px !important;
            border: 1px solid var(--line-strong) !important;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(193, 232, 255, 0.72) 100%) !important;
            color: var(--ink) !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.1rem !important;
            transition: all 0.18s ease;
        }

        [data-testid="stBaseButton-primary"] {
            background: linear-gradient(135deg, #052659 0%, #5483B3 100%) !important;
            color: #f4fbff !important;
            border-color: #052659 !important;
        }

        .stButton > button p,
        .stDownloadButton > button p,
        [data-testid="stBaseButton-secondary"] p,
        [data-testid="stBaseButton-primary"] p,
        .stButton > button span,
        .stDownloadButton > button span,
        [data-testid="stBaseButton-secondary"] span,
        [data-testid="stBaseButton-primary"] span {
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

        [data-testid="stDataFrame"],
        [data-testid="stTable"] {
            border-radius: 24px;
            overflow: hidden;
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
        }

        div[data-testid="stPlotlyChart"] {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(233, 245, 255, 0.92) 100%);
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

        .diagnosis-card-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 0.85rem 0 1.15rem;
        }

        .diagnosis-card {
            min-width: 0;
            overflow: hidden;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(236, 247, 255, 0.95) 100%);
            border: 1px solid rgba(84, 131, 179, 0.2);
            border-radius: 24px;
            padding: 1rem 1.05rem;
            box-shadow: 0 18px 42px rgba(2, 16, 36, 0.08);
        }

        .diagnosis-card.full-span {
            grid-column: 1 / -1;
        }

        .diagnosis-card-label {
            color: var(--muted);
            font-size: 0.76rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
            line-height: 1.4;
        }

        .diagnosis-card-value {
            margin-top: 0.45rem;
            color: var(--ink);
            font-size: 1rem;
            line-height: 1.78;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: break-word;
            min-width: 0;
        }

        .diagnosis-card-value strong {
            color: var(--ink);
        }

        @media (max-width: 1100px) {
            .premium-stat-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .dashboard-snapshot {
                grid-template-columns: 1fr;
            }

            .diagnosis-card-grid {
                grid-template-columns: 1fr;
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


def _api_base() -> str:
    return st.session_state.get("api_base", DEFAULT_API_BASE)


@st.cache_data(show_spinner=False, ttl=15)
def cached_api_get(path: str, params_json: str = "") -> Any:
    params = json.loads(params_json) if params_json else {}
    resp = requests.get(f"{_api_base()}{path}", params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def clear_cached_api_get() -> None:
    cast(Any, cached_api_get).clear()


def api_get(path: str, **params: Any) -> tuple[bool, Any]:
    try:
        key = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
        return True, cached_api_get(path, key)
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        return False, f"GET {path} 失败: HTTP {exc.response.status_code} | {detail}"
    except Exception as exc:
        return False, f"GET {path} 失败: {exc}"


def api_post(path: str, timeout: int = 180, **kwargs: Any) -> tuple[bool, Any]:
    try:
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
        resp = requests.put(f"{_api_base()}{path}", json=payload, timeout=120)
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
        resp = requests.delete(f"{_api_base()}{path}", timeout=120)
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
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)
    return str(value)


def safe_dataframe(data, *, use_container_width=True, height=None):
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
    st.dataframe(df, use_container_width=use_container_width, height=height)


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


def _detail_text(value: Any, *, empty_text: str = "未提供") -> str:
    if not _has_display_value(value):
        return empty_text
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return _format_metric_value(value)
    if isinstance(value, dict):
        lines = [f"{key}: {_detail_text(item, empty_text='-')}" for key, item in value.items() if _has_display_value(item)]
        return "\n".join(lines) if lines else empty_text
    if isinstance(value, (list, tuple, set)):
        lines = [_detail_text(item, empty_text="-") for item in value if _has_display_value(item)]
        return "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines)) if lines else empty_text
    return str(value).strip() or empty_text


def render_diagnosis_detail_cards(summary_text: Any, structured_result: Any):
    structured = structured_result if isinstance(structured_result, dict) else {}
    probable_module = structured.get("probable_module")
    affected_modules = list(structured.get("affected_modules") or []) if isinstance(structured.get("affected_modules"), list) else []
    if probable_module and probable_module not in affected_modules:
        affected_modules = [probable_module] + affected_modules

    sections = [
        {"label": "诊断摘要", "value": summary_text or structured.get("root_cause_summary"), "full_span": True},
        {"label": "根因摘要", "value": structured.get("root_cause_summary")},
        {"label": "可能原因", "value": structured.get("possible_causes")},
        {"label": "影响模块", "value": affected_modules},
        {"label": "建议检查", "value": structured.get("recommended_checks")},
        {"label": "排查步骤", "value": structured.get("troubleshooting_steps")},
        {"label": "修复方向", "value": structured.get("possible_fix_paths")},
        {"label": "责任部门", "value": structured.get("owner_departments")},
        {"label": "严重级别 / 置信度", "value": f"严重级别: {_detail_text(structured.get('severity'), empty_text='未评估')}\n置信度: {_detail_text(structured.get('confidence'), empty_text='未评估')}"},
        {"label": "风险提示", "value": structured.get("risk_warnings")},
    ]
    visible_sections = [section for section in sections if _has_display_value(section.get("value"))]
    if not visible_sections:
        return

    cards: list[str] = []
    for section in visible_sections:
        full_span_class = " full-span" if section.get("full_span") else ""
        body_html = escape(_detail_text(section.get("value"))).replace("\n", "<br>")
        cards.append(
            _html_block(
                f"""
                <article class="diagnosis-card{full_span_class}">
                    <div class="diagnosis-card-label">{escape(str(section.get("label", "")))}</div>
                    <div class="diagnosis-card-value">{body_html}</div>
                </article>
                """
            )
        )
    st.markdown(f'<div class="diagnosis-card-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


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


def render_fig(
    fig,
    key: str | None = None,
    height: int | None = None,
    title: str | None = None,
    title_outside: bool = False,
    title_x: float = 0,
    title_y: float = 0.98,
):
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
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.94)",
        colorway=PLOTLY_COLOR_SEQUENCE,
        font=dict(family='"Avenir Next", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif', color="#021024", size=13),
        title=dict(text="<br>".join(wrapped_title_lines) if wrapped_title_lines and not title_outside else "", font=dict(family='"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif', size=22, color="#052659"), x=title_x, xanchor="left", y=title_y, yanchor="top", pad=dict(b=18)),
        title_automargin=True,
        margin=dict(l=12, r=18, t=top_margin, b=28),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)", title_text=""),
        uniformtext=dict(minsize=10, mode="hide"),
        hoverlabel=dict(bgcolor="#f4fbff", bordercolor="#7DA0CA", font=dict(color="#021024")),
    )
    fig.update_xaxes(automargin=True, title_standoff=14, gridcolor="rgba(84,131,179,0.12)", linecolor="rgba(84,131,179,0.18)", zeroline=False)
    fig.update_yaxes(automargin=True, title_standoff=14, gridcolor="rgba(84,131,179,0.12)", linecolor="rgba(84,131,179,0.18)", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, key=key, config={"responsive": True, "displayModeBar": False, "displaylogo": False, "scrollZoom": False})


def render_substep_cycle_facets(df: pd.DataFrame, value_col: str = "duration_value", facet_wrap: int = 2, key: str | None = None):
    required_cols = {"cycle_no", "sub_step", value_col}
    missing = required_cols - set(df.columns)
    if missing:
        st.warning(f"无法绘制分面图，缺少字段: {', '.join(sorted(missing))}")
        return
    plot_df = df[["cycle_no", "sub_step", value_col]].copy().dropna(subset=["cycle_no", "sub_step", value_col])
    if plot_df.empty:
        st.info("当前筛选条件下没有可用于绘制 Substep-Cycle 趋势图的数据。")
        return
    plot_df["cycle_no"] = pd.to_numeric(plot_df["cycle_no"], errors="coerce")
    plot_df[value_col] = pd.to_numeric(plot_df[value_col], errors="coerce")
    plot_df = plot_df.dropna(subset=["cycle_no", value_col]).sort_values(by=["sub_step", "cycle_no"])
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


inject_design_system()
st.session_state.setdefault("api_base", DEFAULT_API_BASE)
API_BASE = st.sidebar.text_input("FastAPI 地址", value=st.session_state["api_base"])
st.session_state["api_base"] = API_BASE
api_ok, api_msg = check_api_health()

tasks_page = load_tasks_page()
tasks = tasks_page.get("items", [])
label_to_uuid = {f"{t.get('created_at', '')} | {str(t.get('task_uuid', ''))[:8]} | {t.get('status', '')} | {t.get('filename', '')}": t.get("task_uuid", "") for t in tasks}
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

page = st.sidebar.radio("导航", ["首页 / 仪表盘", "历史项目中心", "文件上传", "统一事件流", "耗时分析", "事件流时间轴", "错误分析", "参数趋势分析", "LLM 诊断", "原始文件预览", "未知日志待标注池", "规则建议审核视图", "配置页面", "导出"])
if page != "首页 / 仪表盘":
    render_page_intro(page, task_uuid, api_ok)

if page == "首页 / 仪表盘":
    if not task_uuid:
        st.info("请先在左侧选择任务 UUID。")
    else:
        ok, data = api_get(f"/tasks/{task_uuid}/dashboard")
        ok_status, status = api_get(f"/tasks/{task_uuid}/status")
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

elif page == "文件上传":
    with st.form("upload_form"):
        uploaded = st.file_uploader("支持多文件与压缩包上传(zip / 7z / tar)", accept_multiple_files=True)
        cpu_cores = st.number_input("并行处理 CPU 核心数", min_value=1, max_value=max(1, os.cpu_count() or 4), value=min(4, max(1, os.cpu_count() or 4)), step=1)
        submitted = st.form_submit_button("开始批量上传并分析")
    if submitted and uploaded:
        with st.spinner("正在上传并提交后台任务，请勿重复点击..."):
            files_payload = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in uploaded]
            ok, result = api_post("/tasks/upload", files=files_payload, data={"cpu_cores": int(cpu_cores)})
            if ok:
                st.success("任务已提交，后端正在后台处理中。")
                st.session_state["latest_task_uuid"] = result["task_uuid"]
                clear_cached_api_get()
                safe_json(result)
            else:
                st.error(result)
    if task_uuid:
        ok, status = api_get(f"/tasks/{task_uuid}/status")
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
        f1, f2, f3, f4, f5 = st.columns(5, gap="medium")
        component = f1.text_input("组件过滤")
        level = f2.selectbox("级别", ["", "INFO", "WARN", "ERROR", "FATAL"])
        cycle_no = f3.text_input("Cycle")
        chip_name = f4.text_input("芯片名")
        search = f5.text_input("关键词")
        paged_table(f"/tasks/{task_uuid}/events", params={"component": component or None, "level": level or None, "cycle_no": int(cycle_no) if cycle_no.strip() else None, "chip_name": chip_name or None, "search": search or None}, page_key="events_page", page_size_key="events_page_size", title="统一事件流", default_page_size=100, max_page_size=500)

elif page == "耗时分析":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        unit = DURATION_UNITS[st.selectbox("Cycle 总耗时单位", list(DURATION_UNITS.keys()), key="ana_unit")]
        ok2, cycle_rows = api_get(f"/tasks/{task_uuid}/cycle-summary", unit=unit)
        if ok2:
            cycle_df = pd.DataFrame(cycle_rows)
            if not cycle_df.empty:
                render_fig(px.line(cycle_df, x="cycle_no", y="total_duration_value", color="chip_name", markers=True), key="ana_cycle", title=f"Cycle 总耗时趋势({unit})", height=420, title_outside=True)
                safe_dataframe(cycle_df, use_container_width=True, height=260)
        paged_table(f"/tasks/{task_uuid}/steps", page_key="steps_page", page_size_key="steps_page_size", title="Sub-step 耗时表", default_page_size=100, max_page_size=500)
        ok3, ops = api_get(f"/tasks/{task_uuid}/operational-metrics")
        if ok3:
            photo_df = pd.DataFrame(ops.get("photo_summary", []))
            if not photo_df.empty:
                st.markdown("### 拍照时间摘要")
                safe_dataframe(photo_df, use_container_width=True, height=240)

elif page == "事件流时间轴":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        cycles_ok, cycles = api_get(f"/tasks/{task_uuid}/cycles")
        options = ["全程"] + [str(c) for c in (cycles if cycles_ok else [])]
        cycle_pick = st.selectbox("选择 Cycle", options, key="timeline_cycle")
        track_order = st.selectbox("纵轴顺序", ["default", "cycle"], format_func=lambda x: "默认顺序" if x == "default" else "按 cycle 排序")
        cycle_no = None if cycle_pick == "全程" else int(cycle_pick)
        ok, rows = api_get(f"/tasks/{task_uuid}/movement-timeline", cycle_no=cycle_no, track_order=track_order)
        ok_errors, error_rows = api_get(f"/tasks/{task_uuid}/movement-timeline/errors", cycle_no=cycle_no)
        if ok:
            df = pd.DataFrame(rows)
            if not df.empty:
                # Avoid relying on pandas' newer "mixed" parser so timeline rendering
                # still works in environments with slightly different pandas versions.
                df["start"] = pd.to_datetime(df["start"], errors="coerce")
                df["end"] = pd.to_datetime(df["end"], errors="coerce")
                df = df.dropna(subset=["start", "end"]).copy()
                if df.empty:
                    st.info("当前时间轴数据缺少可解析的开始/结束时间，暂时无法绘制甘特图。")
                else:
                    error_df = pd.DataFrame(error_rows if ok_errors and isinstance(error_rows, list) else [])
                    show_error_points = st.checkbox("标记错误发生时间点", value=True, key="timeline_show_errors")
                    selected_families: list[str] = []
                    selected_severities: list[str] = []
                    if show_error_points and not error_df.empty:
                        error_df = enrich_error_family_frame(error_df)
                        error_df["severity"] = error_df["severity"].fillna("unknown").astype(str)
                        family_options = sorted(error_df["error_family_display"].dropna().unique().tolist())
                        severity_options = sorted(error_df["severity"].dropna().unique().tolist())
                        c1, c2 = st.columns(2)
                        with c1:
                            selected_families = st.multiselect("显示哪些错误家族", family_options, default=family_options, key="timeline_error_families")
                        with c2:
                            selected_severities = st.multiselect("显示哪些严重级别", severity_options, default=severity_options, key="timeline_error_severities")
                        error_df = error_df[
                            error_df["error_family_display"].isin(selected_families)
                            & error_df["severity"].isin(selected_severities)
                        ].copy()
                        error_df["time"] = pd.to_datetime(error_df["time"], errors="coerce")
                        error_df = error_df.dropna(subset=["time"]).copy()
                    fig = px.timeline(df, x_start="start", x_end="end", y="track", color="sub_step", hover_data=["sub_step", "cycle_no", "start_time_sec", "end_time_sec", "duration_ms", "component", "module", "message"])
                    if show_error_points and not error_df.empty:
                        for severity_value, severity_group in error_df.groupby("severity", dropna=False):
                            severity_text = str(severity_value or "unknown")
                            fig.add_trace(
                                go.Scatter(
                                    x=severity_group["time"],
                                    y=severity_group["track"],
                                    mode="markers",
                                    name=f"错误点 {severity_text}",
                                    marker={
                                        "size": 11,
                                        "symbol": "diamond",
                                        "color": ERROR_SEVERITY_COLORS.get(severity_text.lower(), ERROR_SEVERITY_COLORS["unknown"]),
                                        "line": {"width": 1, "color": "#FFFFFF"},
                                    },
                                    customdata=severity_group[["time_text", "normalized_signature", "error_family_display", "severity", "component", "message"]].to_numpy(),
                                    hovertemplate=(
                                        "时间: %{customdata[0]}<br>"
                                        "错误签名: %{customdata[1]}<br>"
                                        "错误家族: %{customdata[2]}<br>"
                                        "严重级别: %{customdata[3]}<br>"
                                        "组件: %{customdata[4]}<br>"
                                        "消息: %{customdata[5]}<extra></extra>"
                                    ),
                                )
                            )
                    render_fig(fig, key="timeline", height=min(max(500, 24 * len(df['track'].unique()) + 180), 2200), title="按 Cycle / 全程查看各组件运动时间轴", title_outside=True)
                    if show_error_points:
                        if ok_errors and not error_df.empty:
                            st.caption(f"当前已标记 {len(error_df)} 个错误时间点，可按错误家族和严重级别自由筛选。")
                        elif ok_errors:
                            st.caption("当前筛选条件下没有可显示的错误时间点。")
                        else:
                            st.caption("错误时间点加载失败，当前仅展示甘特图。")
                    if st.checkbox("显示时间轴表格明细", value=False):
                        safe_dataframe(df[[c for c in ["track","cycle_no","component","sub_step","start_time_sec","end_time_sec","duration_ms","message"] if c in df.columns]], use_container_width=True, height=300)
            else:
                st.info("当前筛选条件下暂无可展示的运动时间轴。")
        else:
            st.error(rows)

elif page == "错误分析":
    if not task_uuid:
        st.info("请先选择任务 UUID。")
    else:
        paged_table(f"/tasks/{task_uuid}/errors", page_key="errors_page", page_size_key="errors_page_size", title="错误簇", default_page_size=100, max_page_size=500)
        ok, rows = api_get(f"/tasks/{task_uuid}/errors", limit=100, offset=0)
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
        ok_defs, defs = api_get("/parameter-definitions")
        if ok_defs:
            defs = [d for d in defs if d.get("parameter_name") != "imaging_time"]
            options = [d["parameter_name"] for d in defs]
            selected = st.multiselect("选择参数", options, default=options[:4])
            unit = DURATION_UNITS[st.selectbox("趋势图单位", list(DURATION_UNITS.keys()), key="trend_unit")]
            if selected:
                for name in selected:
                    ok, rows = api_get(f"/tasks/{task_uuid}/parameter-series/{name}", unit=unit)
                    if ok and rows:
                        df = pd.DataFrame(rows)
                        x_col = "cycle"
                        if str(name).startswith("temperature_"):
                            x_col = "start_time"
                        df = df.sort_values(by=[x_col, "cycle"], na_position="last")
                        fig = px.line(df, x=x_col, y="duration_value", markers=True)
                        if df["threshold_value"].notna().any():
                            fig.add_hline(y=float(df["threshold_value"].dropna().iloc[0]), line_dash="dash", line_color="red")
                        if df["expected_value"].notna().any():
                            fig.add_hline(y=float(df["expected_value"].dropna().iloc[0]), line_dash="dot", line_color="green")
                        render_fig(fig, key=f"trend_{name}", height=360, title=f"{name} 趋势")
                ok_sub, sub_rows = api_get(f"/tasks/{task_uuid}/substep-cycle-series", agg_mode="mean", unit=unit)
                if ok_sub and sub_rows:
                    render_substep_cycle_facets(pd.DataFrame(sub_rows), value_col="duration_value", key="substep_cycle_facets")
        ok_metric, metric_rows = api_get(f"/tasks/{task_uuid}/row-scan-metric-series", unit="ms")
        if ok_metric and metric_rows:
            metric_df = pd.DataFrame(metric_rows)
            render_fig(px.line(metric_df, x="cycle", y="duration_value", color="metric_stage", markers=True), key="metric_trend", height=420, title="Row Scan Metrics 各阶段趋势")
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
                labels = [f"{i + 1}. {row.get('normalized_signature', '')} | {row.get('analysis_stage', '-')} | {row.get('created_at', '-')}" for i, row in enumerate(filtered_rows)]
                if labels:
                    picked = st.selectbox("选择历史结果", labels, key="llm_hist_pick")
                    idx = labels.index(picked)
                    selected_hist = filtered_rows[idx]
                    selected_hist_structured = (selected_hist.get("response_payload") or {}).get("structured_result", selected_hist.get("response_payload", {}))
                    render_diagnosis_detail_cards(selected_hist.get("chinese_summary", ""), selected_hist_structured)
                    token_summary = selected_hist.get("token_summary", {}) or {}
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("分析深度", selected_hist.get("analysis_stage", "-"))
                    c2.metric("Prompt 版本", selected_hist.get("prompt_version", "-"))
                    c3.metric("LLM 状态", selected_hist.get("llm_status", "-"))
                    c4.metric("总 Token", token_summary.get("final_total_tokens") or "-")
                    tab1, tab2, tab3, tab4, tab5 = st.tabs(["结构化结果", "上下文摘要", "源码片段", "相似案例", "完整片段"])
                    with tab1:
                        safe_json(selected_hist_structured)
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
                    st.caption(f"该错误簇已有历史诊断: {latest_item.get('created_at', '-')} | {latest_item.get('analysis_stage', '-')} | {latest_item.get('llm_status', '-')}")

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
                    render_diagnosis_detail_cards(result.get("chinese_summary", ""), result.get("structured_result", {}))
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
                st.markdown(f"[导出 JSON]({_api_base()}/solution-repository/export?format=json)")
                st.markdown(f"[导出 CSV]({_api_base()}/solution-repository/export?format=csv)")
                st.markdown(f"[导出 Excel]({_api_base()}/solution-repository/export?format=xlsx)")
                st.markdown(f"[导出 SQLite 备份]({_api_base()}/solution-repository/export?format=sqlite)")
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
                c3.metric("源文件数", len(row.get("source_files") or {}))
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

        overview_tab, threshold_tab, rules_tab, knowledge_tab = st.tabs(["总览", "时间与阈值", "异常与审核", "Prompt 与方案库"])

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
    else:
        st.error(data)

elif page == "导出":
    if task_uuid:
        st.markdown(f"[导出统一事件 CSV]({_api_base()}/tasks/{task_uuid}/export/events)")
        st.markdown(f"[导出错误分析 CSV]({_api_base()}/tasks/{task_uuid}/export/errors)")
        st.markdown(f"[导出参数结果 CSV]({_api_base()}/tasks/{task_uuid}/export/parameters)")
        st.markdown(f"[导出统一 HTML 报告]({_api_base()}/tasks/{task_uuid}/export/report.html)")
        st.markdown(f"[导出 JSON 报告]({_api_base()}/tasks/{task_uuid}/export/report.json)")
        st.markdown(f"[导出 Excel 报告]({_api_base()}/tasks/{task_uuid}/export/report.xlsx)")
        st.markdown(f"[导出 PDF 报告]({_api_base()}/tasks/{task_uuid}/export/report.pdf)")
    else:
        st.info("请先选择任务 UUID。")

