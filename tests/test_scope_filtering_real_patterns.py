from __future__ import annotations

from pathlib import Path

import orjson
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.settings import get_settings
from app.db.base import Base
from app.models.db_models import ParameterResultModel, StepSummaryModel, UploadTaskModel
from app.schemas.common import NormalizedEvent
from app.services.export_service import ExportService
from app.services.query_service import QueryService
from app.services.streaming_aggregation import StreamingAggregationCoordinator


def _make_event(
    *,
    epoch_ms: int,
    message: str,
    side_scope: str,
    chip_name: str,
    direction: str,
) -> NormalizedEvent:
    return NormalizedEvent(
        source_file="ISW.ZebraMammoth.Service-RobotScheduler_A-20260326.log",
        parser_name="service_log",
        epoch_ms=epoch_ms,
        formatted_ms=str(epoch_ms),
        level="INFO",
        component="Workflow",
        message=message,
        raw_text=message,
        cycle_no=31,
        sub_step="Move slide from imager to chuck stage",
        instrument_scope="Whole Instrument",
        side_scope=side_scope,
        side_group="A",
        chip_name=chip_name,
        event_kind="step",
        direction=direction,
        side_confidence=0.98,
    )


def _session_factory(tmp_path: Path):
    db_path = tmp_path / "scope-filtering.sqlite3"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_query_and_export_scope_filters_keep_a1_a2_separate(tmp_path: Path):
    chip_a1 = "40.M1_UL_HLAA1QY03261"
    chip_a2 = "40.M1_UR_HLAA2QY03263"
    events = [
        _make_event(
            epoch_ms=1000,
            message="Move slide from imager to chuck stage start. A1",
            side_scope="A1",
            chip_name=chip_a1,
            direction="start",
        ),
        _make_event(
            epoch_ms=4000,
            message="Move slide from imager to chuck stage finished. A1",
            side_scope="A1",
            chip_name=chip_a1,
            direction="end",
        ),
        _make_event(
            epoch_ms=1500,
            message="Move slide from imager to chuck stage start. A2",
            side_scope="A2",
            chip_name=chip_a2,
            direction="start",
        ),
        _make_event(
            epoch_ms=5200,
            message="Move slide from imager to chuck stage finished. A2",
            side_scope="A2",
            chip_name=chip_a2,
            direction="end",
        ),
    ]

    SessionLocal = _session_factory(tmp_path)
    jsonl = tmp_path / "events.jsonl"
    with jsonl.open("wb") as handle:
        for event in events:
            handle.write(orjson.dumps(event.model_dump()))
            handle.write(b"\n")

    with SessionLocal() as db:
        task = UploadTaskModel(task_uuid="scope-filter-task", filename="scope-filter.zip", stored_path=str(tmp_path), status="completed")
        db.add(task)
        db.commit()
        db.refresh(task)

        coordinator = StreamingAggregationCoordinator(db, task.id, get_settings())
        coordinator.clear_existing_outputs()
        coordinator.merge_intermediate_results([{"path": "events.jsonl", "output_path": str(jsonl)}])
        context = coordinator.build_cycle_context(total_events=len(events))
        coordinator.postprocess_and_aggregate(context, total_events=len(events))

        query = QueryService(db)
        export = ExportService(db)

        catalog = query.get_scope_catalog(task.id)
        assert {row["side_scope"] for row in catalog["sides"] if row["side_scope"]} == {"A1", "A2"}
        assert {row["chip_name"] for row in catalog["chips"] if row["chip_name"]} == {chip_a1, chip_a2}

        timeline_all = query.get_movement_timeline(task.id, track_granularity="side_chip")
        assert {row["side_scope"] for row in timeline_all["rows"]} == {"A1", "A2"}
        assert {row["chip_name"] for row in timeline_all["rows"]} == {chip_a1, chip_a2}
        assert {row["side_scope"] for row in timeline_all["by_side"]} == {"A1", "A2"}

        timeline_a1 = query.get_movement_timeline(task.id, track_granularity="side_chip", side_scopes=["A1"])
        assert timeline_a1["rows"]
        assert {row["side_scope"] for row in timeline_a1["rows"]} == {"A1"}
        assert {row["chip_name"] for row in timeline_a1["rows"]} == {chip_a1}

        timeline_chip = query.get_movement_timeline(task.id, track_granularity="side_chip", chip_names=[chip_a2])
        assert timeline_chip["rows"]
        assert {row["chip_name"] for row in timeline_chip["rows"]} == {chip_a2}
        assert {row["side_scope"] for row in timeline_chip["rows"]} == {"A2"}

        cycle_all = query.get_cycle_summaries(task.id, unit="s")
        assert {row["side_scope"] for row in cycle_all} == {"A1", "A2"}

        parameter_all = query.get_parameter_series(task.id, "transfer_time", unit="s")
        assert {row["side_scope"] for row in parameter_all} == {"A1", "A2"}

        parameter_a1 = query.get_parameter_series(task.id, "transfer_time", unit="s", side_scopes=["A1"])
        assert parameter_a1
        assert {row["side_scope"] for row in parameter_a1} == {"A1"}
        assert {row["chip_name"] for row in parameter_a1} == {chip_a1}

        parameter_chip = query.get_parameter_series(task.id, "transfer_time", unit="s", chip_names=[chip_a2])
        assert parameter_chip
        assert {row["side_scope"] for row in parameter_chip} == {"A2"}
        assert {row["chip_name"] for row in parameter_chip} == {chip_a2}

        export_all = export._build_report_payload(task.id)
        assert {row["side_scope"] for row in export_all["events"]} == {"A1", "A2"}

        export_a1 = export._build_report_payload(task.id, side_scopes=["A1"])
        assert export_a1["events"]
        assert {row["side_scope"] for row in export_a1["events"]} == {"A1"}
        assert {row["chip_name"] for row in export_a1["events"] if row["chip_name"]} == {chip_a1}
        assert {row["side_scope"] for row in export_a1["parameter_series"]["transfer_time"]} == {"A1"}


def test_query_repairs_unassigned_side_scope_from_step_and_parameter_text(tmp_path: Path):
    SessionLocal = _session_factory(tmp_path)
    with SessionLocal() as db:
        task = UploadTaskModel(task_uuid="scope-repair-task", filename="scope-repair.log", stored_path=str(tmp_path), status="completed")
        db.add(task)
        db.flush()

        db.add_all(
            [
                StepSummaryModel(
                    task_id=task.id,
                    cycle_no=5,
                    sub_step="A1 fill IR",
                    component="ScriptRunner",
                    instrument_scope="Whole Instrument",
                    side_scope=None,
                    side_group=None,
                    chip_name=None,
                    start_epoch_ms=1710000100000,
                    end_epoch_ms=1710000138000,
                    duration_ms=38000,
                    start_time_text="2024-03-09 16:01:40",
                    end_time_text="2024-03-09 16:02:18",
                    side_confidence=None,
                ),
                StepSummaryModel(
                    task_id=task.id,
                    cycle_no=5,
                    sub_step="Chuck stage B2 washing",
                    component="ScriptRunner",
                    instrument_scope="Whole Instrument",
                    side_scope=None,
                    side_group=None,
                    chip_name=None,
                    start_epoch_ms=1710000140000,
                    end_epoch_ms=1710000243000,
                    duration_ms=103000,
                    start_time_text="2024-03-09 16:02:20",
                    end_time_text="2024-03-09 16:04:03",
                    side_confidence=None,
                ),
            ]
        )
        db.add(
            ParameterResultModel(
                task_id=task.id,
                parameter_name="cpas_priming",
                parameter_display_name="cPAS primming",
                cycle_no=27,
                slide="B2",
                instrument_scope="Whole Instrument",
                side_scope=None,
                side_group=None,
                chip_name=None,
                duration_seconds=44.016,
                duration_ms=44016,
                start_time_text="2024-03-09 16:05:00",
                end_time_text="2024-03-09 16:05:44",
                start_message="<<<<<<<< B2 cPAS reagent priming start before cycle= 27 >>>>>>>>>>",
                end_message="<<<<<<<< B2 cPAS reagent priming completed before cycle= 27, span time: 44.016s >>>>>>>>>>",
                source_file="ISW.ZebraMammoth.Service-All_20260326_00.log",
                source_type="derived",
                threshold=40.0,
                expected=30.0,
                is_exceed=True,
                component="ScriptRunner",
                side_confidence=None,
            )
        )
        db.commit()

        query = QueryService(db)

        timeline = query.get_movement_timeline(task.id, track_granularity="side")
        assert {row["side_scope"] for row in timeline["rows"]} == {"A1", "B2"}
        assert {row["side_scope"] for row in timeline["by_side"]} == {"A1", "B2"}

        timeline_a1 = query.get_movement_timeline(task.id, track_granularity="side", side_scopes=["A1"])
        assert timeline_a1["rows"]
        assert {row["side_scope"] for row in timeline_a1["rows"]} == {"A1"}

        substep_a1 = query.get_substep_cycle_series(task.id, axis_mode="cycle", unit="s", side_scopes=["A1"])
        assert substep_a1
        assert {row["side_scope"] for row in substep_a1} == {"A1"}
        assert any("A1 fill IR" in row["series_name"] for row in substep_a1)

        cpas_b2 = query.get_parameter_series(task.id, "cpas_priming", unit="s", side_scopes=["B2"])
        assert cpas_b2
        assert {row["side_scope"] for row in cpas_b2} == {"B2"}
