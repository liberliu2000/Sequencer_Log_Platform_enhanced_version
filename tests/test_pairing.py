from app.correlators.pairing import pair_start_end
from app.schemas.common import NormalizedEvent


def test_pair_start_end():
    events = [
        NormalizedEvent(
            source_file="a.csv",
            parser_name="csv_workflow",
            message="Start B1 fill IR",
            raw_text="Start B1 fill IR",
            level="INFO",
            component="System",
            cycle_no=1,
            sub_step="B1 fill IR",
            event_kind="step",
            direction="start",
            epoch_ms=1000,
            formatted_ms="2026-03-18 09:00:01.000",
        ),
        NormalizedEvent(
            source_file="a.csv",
            parser_name="csv_workflow",
            message="<<<<<<<< B1 fill IR completed, span time: 37.025s >>>>>>>>",
            raw_text="<<<<<<<< B1 fill IR completed, span time: 37.025s >>>>>>>>",
            level="INFO",
            component="System",
            cycle_no=1,
            sub_step="B1 fill IR",
            event_kind="step",
            direction="end",
            epoch_ms=38025,
            formatted_ms="2026-03-18 09:00:38.025",
        ),
    ]
    rows = pair_start_end(events)
    assert rows
    assert rows[0].duration_ms == 37025
