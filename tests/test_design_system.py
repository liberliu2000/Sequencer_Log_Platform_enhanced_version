from ui.shared.design_system import css_rgba_to_flet_color, get_flet_design_tokens


def test_css_rgba_to_flet_color_converts_alpha_color() -> None:
    assert css_rgba_to_flet_color("rgba(193, 232, 255, 0.85)") == "#C1E8FF,0.85"


def test_css_rgba_to_flet_color_handles_zero_alpha() -> None:
    assert css_rgba_to_flet_color("rgba(0, 0, 0, 0)") == "transparent"


def test_flet_design_tokens_do_not_expose_css_rgba_values() -> None:
    tokens = get_flet_design_tokens("light")

    assert "rgba(" not in tokens.line
    assert "rgba(" not in tokens.shadow_color
    assert tokens.line == "#5483B3,0.2"
    assert tokens.shadow_color == "#021024,0.12"
