from __future__ import annotations

from dataclasses import asdict, dataclass
import re

FONT_SANS = '"Avenir Next", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif'
FONT_SERIF = '"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", "STSong", "Songti SC", serif'
FONT_MONO = '"Consolas", "JetBrains Mono", "SFMono-Regular", monospace'

PAGE_MAX_WIDTH = 1420
SIDEBAR_WIDTH = 320
PAGE_PADDING = 24
RADIUS_XL = 30
RADIUS_LG = 24
RADIUS_MD = 22
RADIUS_SM = 18
PILL_RADIUS = 999
CONTROL_HEIGHT = 46


@dataclass(frozen=True)
class DesignTokens:
    name: str
    bg_top: str
    bg_mid: str
    bg_bottom: str
    page_glow_primary: str
    page_glow_secondary: str
    surface: str
    surface_strong: str
    surface_solid: str
    surface_soft: str
    hero_start: str
    hero_end: str
    card_start: str
    card_end: str
    dashboard_start: str
    dashboard_end: str
    plot_start: str
    plot_end: str
    sidebar_start: str
    sidebar_end: str
    sidebar_card_start: str
    sidebar_card_end: str
    ink: str
    muted: str
    sidebar_ink: str
    sidebar_muted: str
    line: str
    line_strong: str
    accent: str
    accent_strong: str
    accent_soft: str
    accent_ice: str
    on_primary: str
    success: str
    warning: str
    danger: str
    shadow: str
    shadow_color: str
    input_bg: str
    input_focus_bg: str
    input_text: str
    input_label: str
    button_secondary_start: str
    button_secondary_end: str
    button_primary_start: str
    button_primary_end: str
    progress_track: str
    progress_start: str
    progress_mid: str
    progress_end: str
    pill_bg: str
    pill_border: str
    pill_ink: str
    sidebar_pill_bg: str
    sidebar_pill_border: str
    sidebar_pill_ink: str
    icon_chip_bg: str
    icon_chip_border: str
    icon_chip_ink: str
    sidebar_icon_chip_bg: str
    sidebar_icon_chip_border: str
    sidebar_icon_chip_ink: str
    tab_bg: str
    tab_ink: str
    tab_selected_start: str
    tab_selected_end: str
    tab_selected_ink: str
    code_bg: str
    note: str
    disabled_bg: str
    disabled_fg: str


LIGHT_TOKENS = DesignTokens(
    name="light",
    bg_top="#E8F5FF",
    bg_mid="#D6EAFF",
    bg_bottom="#BFD8F0",
    page_glow_primary="rgba(193, 232, 255, 0.85)",
    page_glow_secondary="rgba(125, 160, 202, 0.25)",
    surface="rgba(255, 255, 255, 0.82)",
    surface_strong="rgba(255, 255, 255, 0.94)",
    surface_solid="#F7FBFF",
    surface_soft="#ECF4FB",
    hero_start="rgba(255, 255, 255, 0.96)",
    hero_end="rgba(193, 232, 255, 0.82)",
    card_start="rgba(255, 255, 255, 0.97)",
    card_end="rgba(237, 247, 255, 0.92)",
    dashboard_start="rgba(255, 255, 255, 0.97)",
    dashboard_end="rgba(233, 245, 255, 0.94)",
    plot_start="rgba(255, 255, 255, 0.96)",
    plot_end="rgba(233, 245, 255, 0.92)",
    sidebar_start="rgba(2, 16, 36, 0.96)",
    sidebar_end="rgba(5, 38, 89, 0.95)",
    sidebar_card_start="rgba(7, 45, 96, 0.72)",
    sidebar_card_end="rgba(2, 16, 36, 0.68)",
    ink="#021024",
    muted="#3B6898",
    sidebar_ink="#F4FBFF",
    sidebar_muted="rgba(233, 245, 255, 0.82)",
    line="rgba(84, 131, 179, 0.20)",
    line_strong="rgba(84, 131, 179, 0.34)",
    accent="#052659",
    accent_strong="#5483B3",
    accent_soft="#7DA0CA",
    accent_ice="#C1E8FF",
    on_primary="#F4FBFF",
    success="#2E7D5A",
    warning="#D96B3B",
    danger="#D94841",
    shadow="0 24px 72px rgba(2, 16, 36, 0.12)",
    shadow_color="rgba(2, 16, 36, 0.12)",
    input_bg="rgba(255, 255, 255, 0.92)",
    input_focus_bg="#FFFFFF",
    input_text="#021024",
    input_label="#3B6898",
    button_secondary_start="rgba(255, 255, 255, 0.96)",
    button_secondary_end="rgba(193, 232, 255, 0.72)",
    button_primary_start="#052659",
    button_primary_end="#5483B3",
    progress_track="rgba(31, 36, 33, 0.08)",
    progress_start="#052659",
    progress_mid="#5483B3",
    progress_end="#7DA0CA",
    pill_bg="rgba(255, 255, 255, 0.62)",
    pill_border="rgba(84, 131, 179, 0.20)",
    pill_ink="#021024",
    sidebar_pill_bg="rgba(193, 232, 255, 0.10)",
    sidebar_pill_border="rgba(193, 232, 255, 0.16)",
    sidebar_pill_ink="#F4FBFF",
    icon_chip_bg="rgba(84, 131, 179, 0.12)",
    icon_chip_border="rgba(84, 131, 179, 0.16)",
    icon_chip_ink="#021024",
    sidebar_icon_chip_bg="rgba(193, 232, 255, 0.12)",
    sidebar_icon_chip_border="rgba(193, 232, 255, 0.16)",
    sidebar_icon_chip_ink="#F4FBFF",
    tab_bg="rgba(255, 251, 246, 0.68)",
    tab_ink="#3B6898",
    tab_selected_start="#052659",
    tab_selected_end="#5483B3",
    tab_selected_ink="#F4FBFF",
    code_bg="#F5FAFF",
    note="#4B6E94",
    disabled_bg="#D9E5F2",
    disabled_fg="#88A4BF",
)

DARK_TOKENS = DesignTokens(
    name="dark",
    bg_top="#09111F",
    bg_mid="#0D1B31",
    bg_bottom="#132844",
    page_glow_primary="rgba(84, 131, 179, 0.28)",
    page_glow_secondary="rgba(193, 232, 255, 0.16)",
    surface="rgba(12, 22, 38, 0.84)",
    surface_strong="rgba(10, 20, 36, 0.94)",
    surface_solid="#12243C",
    surface_soft="#17304D",
    hero_start="rgba(18, 36, 60, 0.98)",
    hero_end="rgba(12, 24, 40, 0.92)",
    card_start="rgba(18, 36, 60, 0.96)",
    card_end="rgba(14, 27, 44, 0.90)",
    dashboard_start="rgba(18, 36, 60, 0.98)",
    dashboard_end="rgba(14, 27, 44, 0.94)",
    plot_start="rgba(18, 36, 60, 0.96)",
    plot_end="rgba(14, 27, 44, 0.92)",
    sidebar_start="rgba(3, 10, 20, 0.98)",
    sidebar_end="rgba(6, 21, 40, 0.97)",
    sidebar_card_start="rgba(11, 27, 48, 0.86)",
    sidebar_card_end="rgba(5, 14, 27, 0.82)",
    ink="#F4FBFF",
    muted="#A8C9EC",
    sidebar_ink="#F4FBFF",
    sidebar_muted="rgba(233, 245, 255, 0.78)",
    line="rgba(125, 160, 202, 0.24)",
    line_strong="rgba(193, 232, 255, 0.32)",
    accent="#C1E8FF",
    accent_strong="#7DA0CA",
    accent_soft="#5483B3",
    accent_ice="#E8F5FF",
    on_primary="#04101F",
    success="#5CB690",
    warning="#F1B17C",
    danger="#F27F7A",
    shadow="0 24px 72px rgba(2, 8, 18, 0.38)",
    shadow_color="rgba(2, 8, 18, 0.38)",
    input_bg="rgba(8, 18, 31, 0.92)",
    input_focus_bg="rgba(12, 24, 40, 0.98)",
    input_text="#F4FBFF",
    input_label="#A8C9EC",
    button_secondary_start="rgba(18, 36, 60, 0.96)",
    button_secondary_end="rgba(23, 48, 77, 0.88)",
    button_primary_start="#7DA0CA",
    button_primary_end="#C1E8FF",
    progress_track="rgba(193, 232, 255, 0.14)",
    progress_start="#7DA0CA",
    progress_mid="#C1E8FF",
    progress_end="#F4FBFF",
    pill_bg="rgba(18, 36, 60, 0.78)",
    pill_border="rgba(125, 160, 202, 0.24)",
    pill_ink="#F4FBFF",
    sidebar_pill_bg="rgba(193, 232, 255, 0.12)",
    sidebar_pill_border="rgba(193, 232, 255, 0.18)",
    sidebar_pill_ink="#F4FBFF",
    icon_chip_bg="rgba(125, 160, 202, 0.18)",
    icon_chip_border="rgba(193, 232, 255, 0.18)",
    icon_chip_ink="#F4FBFF",
    sidebar_icon_chip_bg="rgba(193, 232, 255, 0.12)",
    sidebar_icon_chip_border="rgba(193, 232, 255, 0.18)",
    sidebar_icon_chip_ink="#F4FBFF",
    tab_bg="rgba(18, 36, 60, 0.74)",
    tab_ink="#C1DDF4",
    tab_selected_start="#7DA0CA",
    tab_selected_end="#C1E8FF",
    tab_selected_ink="#04101F",
    code_bg="#0B1728",
    note="#BFD8F0",
    disabled_bg="#29415D",
    disabled_fg="#8BA7C2",
)

THEMES = {"light": LIGHT_TOKENS, "dark": DARK_TOKENS}
FLET_THEMES: dict[str, DesignTokens] = {}
_RGBA_COLOR_RE = re.compile(
    r"rgba\(\s*(?P<r>\d{1,3})\s*,\s*(?P<g>\d{1,3})\s*,\s*(?P<b>\d{1,3})\s*,\s*(?P<a>(?:0|1)(?:\.\d+)?)\s*\)",
    re.IGNORECASE,
)
_FLET_COLOR_EXCLUDE_FIELDS = {"name", "shadow"}


def get_design_tokens(mode: str | None) -> DesignTokens:
    key = str(mode or "light").strip().lower()
    return THEMES["dark" if key == "dark" else "light"]


def css_rgba_to_flet_color(value: str) -> str:
    text = str(value).strip()
    match = _RGBA_COLOR_RE.fullmatch(text)
    if not match:
        return text

    red = max(0, min(255, int(match.group("r"))))
    green = max(0, min(255, int(match.group("g"))))
    blue = max(0, min(255, int(match.group("b"))))
    alpha = max(0.0, min(1.0, float(match.group("a"))))
    base = f"#{red:02X}{green:02X}{blue:02X}"
    if alpha <= 0:
        return "transparent"
    if alpha >= 1:
        return base
    alpha_text = f"{alpha:.4f}".rstrip("0").rstrip(".")
    return f"{base},{alpha_text}"


def get_flet_design_tokens(mode: str | None) -> DesignTokens:
    key = "dark" if str(mode or "light").strip().lower() == "dark" else "light"
    cached = FLET_THEMES.get(key)
    if cached is not None:
        return cached

    raw_tokens = get_design_tokens(key)
    converted = {
        field_name: css_rgba_to_flet_color(field_value)
        if field_name not in _FLET_COLOR_EXCLUDE_FIELDS
        else field_value
        for field_name, field_value in asdict(raw_tokens).items()
    }
    flet_tokens = DesignTokens(**converted)
    FLET_THEMES[key] = flet_tokens
    return flet_tokens


def streamlit_root_vars(theme: DesignTokens) -> str:
    variables = {
        "bg-top": theme.bg_top,
        "bg-mid": theme.bg_mid,
        "bg-bottom": theme.bg_bottom,
        "page-glow-primary": theme.page_glow_primary,
        "page-glow-secondary": theme.page_glow_secondary,
        "surface": theme.surface,
        "surface-strong": theme.surface_strong,
        "surface-solid": theme.surface_solid,
        "surface-soft": theme.surface_soft,
        "hero-start": theme.hero_start,
        "hero-end": theme.hero_end,
        "card-start": theme.card_start,
        "card-end": theme.card_end,
        "dashboard-start": theme.dashboard_start,
        "dashboard-end": theme.dashboard_end,
        "plot-start": theme.plot_start,
        "plot-end": theme.plot_end,
        "sidebar-start": theme.sidebar_start,
        "sidebar-end": theme.sidebar_end,
        "sidebar-card-start": theme.sidebar_card_start,
        "sidebar-card-end": theme.sidebar_card_end,
        "ink": theme.ink,
        "muted": theme.muted,
        "sidebar-ink": theme.sidebar_ink,
        "sidebar-muted": theme.sidebar_muted,
        "line": theme.line,
        "line-strong": theme.line_strong,
        "accent": theme.accent,
        "accent-strong": theme.accent_strong,
        "accent-soft": theme.accent_soft,
        "accent-ice": theme.accent_ice,
        "on-primary": theme.on_primary,
        "success": theme.success,
        "warning": theme.warning,
        "danger": theme.danger,
        "shadow": theme.shadow,
        "input-bg": theme.input_bg,
        "input-focus-bg": theme.input_focus_bg,
        "input-text": theme.input_text,
        "input-label": theme.input_label,
        "button-secondary-start": theme.button_secondary_start,
        "button-secondary-end": theme.button_secondary_end,
        "button-primary-start": theme.button_primary_start,
        "button-primary-end": theme.button_primary_end,
        "progress-track": theme.progress_track,
        "progress-start": theme.progress_start,
        "progress-mid": theme.progress_mid,
        "progress-end": theme.progress_end,
        "pill-bg": theme.pill_bg,
        "pill-border": theme.pill_border,
        "pill-ink": theme.pill_ink,
        "sidebar-pill-bg": theme.sidebar_pill_bg,
        "sidebar-pill-border": theme.sidebar_pill_border,
        "sidebar-pill-ink": theme.sidebar_pill_ink,
        "icon-chip-bg": theme.icon_chip_bg,
        "icon-chip-border": theme.icon_chip_border,
        "icon-chip-ink": theme.icon_chip_ink,
        "sidebar-icon-chip-bg": theme.sidebar_icon_chip_bg,
        "sidebar-icon-chip-border": theme.sidebar_icon_chip_border,
        "sidebar-icon-chip-ink": theme.sidebar_icon_chip_ink,
        "tab-bg": theme.tab_bg,
        "tab-ink": theme.tab_ink,
        "tab-selected-start": theme.tab_selected_start,
        "tab-selected-end": theme.tab_selected_end,
        "tab-selected-ink": theme.tab_selected_ink,
        "code-bg": theme.code_bg,
        "note": theme.note,
        "disabled-bg": theme.disabled_bg,
        "disabled-fg": theme.disabled_fg,
        "page-pad": "clamp(1rem, 2vw, 2rem)",
    }
    joined = "\n            ".join(f"--{name}: {value};" for name, value in variables.items())
    return f":root {{\n            {joined}\n        }}"


def streamlit_component_overrides() -> str:
    return """
        html {
            color-scheme: light dark;
        }

        html, body, [class*=\"css\"], [data-testid=\"stApp\"] {
            font-family: """ + FONT_SANS + """;
            color: var(--ink);
        }

        body {
            background: var(--bg-bottom);
        }

        .block-container {
            max-width: """ + str(PAGE_MAX_WIDTH) + """px;
            padding-top: 1.35rem;
            padding-bottom: 3rem;
            padding-left: var(--page-pad);
            padding-right: var(--page-pad);
        }

        #MainMenu, footer, header[data-testid=\"stHeader\"] {
            visibility: hidden;
        }

        h1, h2, h3, h4, [data-testid=\"stMetricValue\"], .premium-title, .premium-stat-value,
        .config-info-value, .config-panel-title, .chart-frame-title, .dashboard-title, .dashboard-progress-value {
            font-family: """ + FONT_SERIF + """;
        }

        [data-testid=\"stAppViewContainer\"] {
            background:
                radial-gradient(circle at top left, var(--page-glow-primary) 0, transparent 32%),
                radial-gradient(circle at top right, var(--page-glow-secondary) 0, transparent 24%),
                linear-gradient(180deg, var(--bg-top) 0%, var(--bg-mid) 40%, var(--bg-bottom) 100%);
        }

        [data-testid=\"stSidebar\"] {
            background: linear-gradient(180deg, var(--sidebar-start) 0%, var(--sidebar-end) 100%);
            border-right: 1px solid var(--sidebar-pill-border);
        }

        [data-testid=\"stSidebar\"] > div:first-child {
            padding-top: 1.2rem;
        }

        [data-testid=\"stSidebar\"] .stTextInput > label,
        [data-testid=\"stSidebar\"] .stSelectbox > label,
        [data-testid=\"stSidebar\"] .stRadio > label,
        [data-testid=\"stSidebar\"] .stCheckbox > label,
        [data-testid=\"stSidebar\"] .stToggle > label {
            color: var(--sidebar-ink) !important;
        }

        [data-testid=\"stSidebar\"] [data-baseweb=\"radio\"] label,
        [data-testid=\"stSidebar\"] [role=\"radiogroup\"] label {
            border-radius: 16px;
            padding: 0.28rem 0.5rem;
            transition: background 0.18s ease, border-color 0.18s ease;
        }

        [data-testid=\"stSidebar\"] [data-baseweb=\"radio\"] label:hover,
        [data-testid=\"stSidebar\"] [role=\"radiogroup\"] label:hover {
            background: var(--sidebar-icon-chip-bg);
        }

        div[data-baseweb=\"input\"] > div,
        div[data-baseweb=\"select\"] > div,
        [data-testid=\"stTextArea\"] textarea,
        [data-testid=\"stNumberInput\"] input,
        [data-testid=\"stFileUploader\"] section {
            background: var(--input-bg) !important;
            border: 1px solid var(--line) !important;
            color: var(--input-text) !important;
        }

        [data-testid=\"stTextArea\"] textarea,
        [data-testid=\"stNumberInput\"] input,
        [data-testid=\"stTextInput\"] input,
        [data-testid=\"stTextInput\"] textarea,
        div[data-baseweb=\"select\"] span,
        div[data-baseweb=\"select\"] div {
            color: var(--input-text) !important;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid=\"stBaseButton-secondary\"],
        [data-testid=\"stBaseButton-primary\"] {
            background: linear-gradient(180deg, var(--button-secondary-start) 0%, var(--button-secondary-end) 100%) !important;
            border-color: var(--line-strong) !important;
            color: var(--ink) !important;
            box-shadow: none !important;
        }

        [data-testid=\"stBaseButton-primary\"] {
            background: linear-gradient(135deg, var(--button-primary-start) 0%, var(--button-primary-end) 100%) !important;
            color: var(--on-primary) !important;
            border-color: var(--button-primary-start) !important;
        }

        [data-testid=\"stBaseButton-primary\"] *,
        [data-testid=\"stBaseButton-primary\"] p,
        [data-testid=\"stBaseButton-primary\"] span {
            color: var(--on-primary) !important;
        }

        [data-testid=\"stProgressBar\"] > div {
            background: var(--progress-track) !important;
        }

        [data-testid=\"stProgressBar\"] > div > div {
            background: linear-gradient(90deg, var(--progress-start) 0%, var(--progress-mid) 60%, var(--progress-end) 100%) !important;
        }

        [data-testid=\"stTabs\"] [role=\"tab\"] {
            background: var(--tab-bg);
            color: var(--tab-ink);
            border-color: var(--line);
        }

        [data-testid=\"stTabs\"] [aria-selected=\"true\"] {
            background: linear-gradient(135deg, var(--tab-selected-start) 0%, var(--tab-selected-end) 100%) !important;
            color: var(--tab-selected-ink) !important;
            border-color: var(--tab-selected-start) !important;
        }

        [data-testid=\"stTabs\"] [aria-selected=\"true\"] *,
        [data-testid=\"stTabs\"] [aria-selected=\"true\"] p,
        [data-testid=\"stTabs\"] [aria-selected=\"true\"] span {
            color: var(--tab-selected-ink) !important;
        }

        [data-testid=\"stMetric\"],
        [data-testid=\"stExpander\"] details,
        [data-testid=\"stDataFrame\"],
        [data-testid=\"stTable\"],
        .section-card,
        .premium-stat-card,
        .config-info-card,
        .config-panel-card,
        .diagnosis-card {
            background: linear-gradient(180deg, var(--card-start) 0%, var(--card-end) 100%) !important;
            border-color: var(--line) !important;
            box-shadow: var(--shadow) !important;
        }

        .premium-hero {
            background: linear-gradient(135deg, var(--hero-start) 0%, var(--hero-end) 100%) !important;
            border-color: var(--line) !important;
            box-shadow: var(--shadow) !important;
        }

        .dashboard-hero {
            background: linear-gradient(180deg, var(--dashboard-start) 0%, var(--dashboard-end) 100%) !important;
            border-color: var(--line) !important;
            box-shadow: var(--shadow) !important;
        }

        .dashboard-progress-shell {
            background: linear-gradient(180deg, var(--card-start) 0%, var(--card-end) 100%);
            border-color: var(--line) !important;
        }

        div[data-testid=\"stPlotlyChart\"] {
            background: linear-gradient(180deg, var(--plot-start) 0%, var(--plot-end) 100%) !important;
            border-color: var(--line) !important;
            box-shadow: var(--shadow) !important;
        }

        .premium-pill {
            background: var(--pill-bg);
            border-color: var(--pill-border);
            color: var(--pill-ink);
        }

        .sidebar-brand .premium-pill,
        .sidebar-note .premium-pill {
            background: var(--sidebar-pill-bg);
            border-color: var(--sidebar-pill-border);
            color: var(--sidebar-pill-ink);
        }

        .icon-chip {
            background: var(--icon-chip-bg);
            border-color: var(--icon-chip-border);
            color: var(--icon-chip-ink);
        }

        .sidebar-brand .icon-chip,
        .sidebar-note .icon-chip {
            background: var(--sidebar-icon-chip-bg);
            border-color: var(--sidebar-icon-chip-border);
            color: var(--sidebar-icon-chip-ink);
        }

        .sidebar-brand,
        .sidebar-note {
            background: linear-gradient(180deg, var(--sidebar-card-start) 0%, var(--sidebar-card-end) 100%);
            border-color: var(--sidebar-pill-border);
            box-shadow: var(--shadow);
        }

        .sidebar-brand p,
        .sidebar-note p,
        .sidebar-brand-kicker,
        .sidebar-note strong {
            color: var(--sidebar-muted) !important;
        }

        .sidebar-brand-title,
        .sidebar-brand .premium-pill,
        .sidebar-note .premium-pill,
        [data-testid=\"stSidebar\"] .stCheckbox > label,
        [data-testid=\"stSidebar\"] .stToggle > label {
            color: var(--sidebar-ink) !important;
        }

        .premium-description,
        .premium-stat-note,
        .config-info-note,
        .config-panel-body,
        .config-panel-note,
        .dashboard-subtitle,
        .dashboard-progress-message,
        .dashboard-insight-label,
        .diagnosis-card-label,
        .section-card-note,
        .section-label,
        .config-info-label,
        .config-panel-badge {
            color: var(--muted) !important;
        }

        .config-panel-note {
            color: var(--note) !important;
        }

        .chart-frame-title,
        .premium-title,
        .premium-stat-value,
        .config-info-value,
        .config-panel-title,
        .dashboard-title,
        .dashboard-progress-value,
        .dashboard-insight-value,
        .diagnosis-card-value,
        .section-card-title,
        .dashboard-hero h1,
        .dashboard-hero h2,
        .dashboard-hero h3,
        .section-card h1,
        .section-card h2,
        .section-card h3 {
            color: var(--ink) !important;
        }

        .dashboard-hero > p,
        .section-card p,
        .section-card span,
        .section-card label {
            color: var(--ink) !important;
        }

        [data-testid=\"stAlert\"],
        [data-testid=\"stInfo\"],
        [data-testid=\"stException\"] {
            background: linear-gradient(180deg, var(--card-start) 0%, var(--card-end) 100%) !important;
            border: 1px solid var(--line) !important;
            color: var(--ink) !important;
        }

        [data-testid=\"stCodeBlock\"],
        [data-testid=\"stCode\"],
        pre {
            background: var(--code-bg) !important;
        }

        *::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        *::-webkit-scrollbar-thumb {
            background: var(--accent-soft);
            border-radius: 999px;
            border: 2px solid transparent;
            background-clip: padding-box;
        }

        *::-webkit-scrollbar-track {
            background: transparent;
        }
    """
