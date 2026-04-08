from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.correlators.pairing import pair_start_end
from app.db.base import Base
from app.models.db_models import StepSummaryModel, UploadTaskModel
from app.normalizers.event_normalizer import normalize_record
from app.schemas.common import RawLogRecord
from app.services.query_service import QueryService


def _raw_record(
    *,
    time_text: str,
    message: str,
    component: str,
    method_name: str,
    source_file: str = "ISW.ZebraMammoth.Service-All_20260326_00.log",
) -> RawLogRecord:
    return RawLogRecord(
        source_file=source_file,
        parser_name="service_log",
        raw_text=message,
        original_time_text=time_text,
        level="INFO",
        component=component,
        method_name=method_name,
        message=message,
    )


def test_message_token_side_fallback_flows_through_normalizer():
    event = normalize_record(
        _raw_record(
            time_text="2026-03-26 11:06:03.8113",
            message="manual action a2 ready",
            component="T100Scheduler",
            method_name="ManualAction",
        )
    )
    assert event.side_scope == "A2"
    assert event.side_evidence.get("from_context") == "A2"


def test_pairing_matches_request_imager_hold_and_acquire_patterns():
    request_start = normalize_record(
        _raw_record(
            time_text="2026-03-26 11:06:03.8113",
            message="A2 request imager and wait.",
            component="T100Scheduler",
            method_name="RequestImagerAndWait",
        )
    )
    request_end = normalize_record(
        _raw_record(
            time_text="2026-03-26 11:06:04.8136",
            message="A2 has hold imager.",
            component="T100Scheduler",
            method_name="RequestImagerAndWait",
        )
    )
    acquire_start = normalize_record(
        _raw_record(
            time_text="2026-03-26 10:02:49.6053",
            message="Start Acquire called for row : 1",
            component="Scanner_1",
            method_name="SendRowImageInfo",
        )
    )
    acquire_end = normalize_record(
        _raw_record(
            time_text="2026-03-26 10:02:51.6459",
            message="Start Acquire Completed for row : 1",
            component="Scanner_1",
            method_name="SendRowImageInfo",
        )
    )

    paired = pair_start_end([request_start, request_end, acquire_start, acquire_end])

    assert len(paired) == 2
    assert any(item.sub_step == "requestimagerandwait" and item.start_epoch_ms is not None and item.end_epoch_ms is not None for item in paired)
    assert any(item.sub_step == "acquire for row : 1" and item.start_epoch_ms is not None and item.end_epoch_ms is not None for item in paired)


def test_pairing_collapses_running_heartbeat_status_into_single_interval():
    running_lines = [
        "2026-03-26 10:04:05.6669",
        "2026-03-26 10:04:06.6682",
        "2026-03-26 10:04:07.6715",
    ]
    events = [
        normalize_record(
            _raw_record(
                time_text=time_text,
                message=r"Spray-B1 Fluidic\T100_Seq2_CpasReagentPrime.py status:Running, errorCode:, updateTime:2026/3/26 10:04:05 +00:00.",
                component="SprayClient",
                method_name="RunSprayAction",
            )
        )
        for time_text in running_lines
    ]
    events.append(
        normalize_record(
            _raw_record(
                time_text="2026-03-26 10:04:47.7014",
                message=r"Spray-B1 Fluidic\T100_Seq2_CpasReagentPrime.py status:Stopped, errorCode:, updateTime:2026/3/26 10:04:46 +00:00.",
                component="SprayClient",
                method_name="RunSprayAction",
            )
        )
    )

    paired = pair_start_end(events)

    assert len(paired) == 1
    assert "cpasreagentprime" in paired[0].sub_step.lower()
    assert paired[0].side_scope == "B1"
    assert paired[0].start_epoch_ms == events[0].epoch_ms
    assert paired[0].end_epoch_ms == events[-1].epoch_ms


def test_pairing_uses_last_heartbeat_when_terminal_status_is_missing():
    running_first = normalize_record(
        _raw_record(
            time_text="2026-03-26 10:04:05.6669",
            message=r"Spray-A2 Fluidic\T100_Seg2_CpasReagentPrime.py status:Running, errorCode:, updateTime:2026/3/26 10:04:05 +00:00.",
            component="SprayClient",
            method_name="RunSprayAction",
        )
    )
    running_last = normalize_record(
        _raw_record(
            time_text="2026-03-26 10:04:10.6735",
            message=r"Spray-A2 Fluidic\T100_Seg2_CpasReagentPrime.py status:Running, errorCode:, updateTime:2026/3/26 10:04:10 +00:00.",
            component="SprayClient",
            method_name="RunSprayAction",
        )
    )

    paired = pair_start_end([running_first, running_last])

    assert len(paired) == 1
    assert paired[0].start_epoch_ms == running_first.epoch_ms
    assert paired[0].end_epoch_ms == running_last.epoch_ms
    assert paired[0].duration_ms == float(running_last.epoch_ms - running_first.epoch_ms)


def test_pairing_keeps_distinct_spray_scripts_separate():
    events = [
        normalize_record(
            _raw_record(
                time_text="2026-03-26 11:05:32.7952",
                message=r"Spray-A2 Fluidic\T100_Fill_IR.py status:Running, errorCode:, updateTime:2026/3/26 11:05:32 +00:00.",
                component="SprayClient",
                method_name="RunSprayAction",
            )
        ),
        normalize_record(
            _raw_record(
                time_text="2026-03-26 11:05:33.1792",
                message=r"Spray-A1 Fluidic\T100_Seq2_CpasReagentPrime.py status:Running, errorCode:, updateTime:2026/3/26 11:05:33 +00:00.",
                component="SprayClient",
                method_name="RunSprayAction",
            )
        ),
        normalize_record(
            _raw_record(
                time_text="2026-03-26 11:05:40.7978",
                message=r"Spray-A2 Fluidic\T100_Fill_IR.py status:Stopped, errorCode:, updateTime:2026/3/26 11:05:40 +00:00.",
                component="SprayClient",
                method_name="RunSprayAction",
            )
        ),
        normalize_record(
            _raw_record(
                time_text="2026-03-26 11:05:44.1878",
                message=r"Spray-A1 Fluidic\T100_Seq2_CpasReagentPrime.py status:Stopped, errorCode:, updateTime:2026/3/26 11:05:44 +00:00.",
                component="SprayClient",
                method_name="RunSprayAction",
            )
        ),
    ]

    paired = pair_start_end(events)

    assert len(paired) == 2
    assert {item.side_scope for item in paired} == {"A1", "A2"}
    assert any("fill_ir.py" in item.sub_step.lower() for item in paired)
    assert any("cpasreagentprime.py" in item.sub_step.lower() for item in paired)


def test_movement_timeline_includes_spray_tracks_and_inferred_bounds(tmp_path: Path):
    db_path = tmp_path / "timeline.sqlite3"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with SessionLocal() as db:
        task = UploadTaskModel(task_uuid="timeline-task", filename="sample.zip", stored_path=str(tmp_path))
        db.add(task)
        db.commit()
        db.refresh(task)

        db.add_all(
            [
                StepSummaryModel(
                    task_id=task.id,
                    cycle_no=1,
                    sub_step="runsprayaction",
                    component="SprayClient",
                    side_scope="B1",
                    side_group="B",
                    start_epoch_ms=1000,
                    end_epoch_ms=5000,
                    duration_ms=4000.0,
                    start_time_text="1000",
                    end_time_text="5000",
                ),
                StepSummaryModel(
                    task_id=task.id,
                    cycle_no=1,
                    sub_step="requestimagerandwait",
                    component="T100Scheduler",
                    side_scope="A2",
                    side_group="A",
                    start_epoch_ms=None,
                    end_epoch_ms=9000,
                    duration_ms=1500.0,
                    start_time_text=None,
                    end_time_text="9000",
                ),
            ]
        )
        db.commit()

        timeline = QueryService(db).get_movement_timeline(task.id, track_granularity="side")

        assert len(timeline) == 2
        assert {row["component"] for row in timeline} == {"SprayClient", "T100Scheduler"}
        inferred_row = next(row for row in timeline if row["component"] == "T100Scheduler")
        assert inferred_row["start_epoch_ms"] == 7500
        assert inferred_row["end_epoch_ms"] == 9000
