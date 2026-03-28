from app.utils.timeparse import parse_datetime, format_ms


def test_parse_slash_dot_ms():
    dt = parse_datetime("2026/03/18 09:45:18.644")
    assert dt is not None
    assert format_ms(dt) == "2026-03-18 09:45:18.644"


def test_parse_slash_colon_ms():
    dt = parse_datetime("2026/03/18 09:21:30:738")
    assert dt is not None
    assert format_ms(dt) == "2026-03-18 09:21:30.738"


def test_parse_dash_four_digits():
    dt = parse_datetime("2026-03-18 09:46:49.1052")
    assert dt is not None
    assert format_ms(dt) == "2026-03-18 09:46:49.105"
