from __future__ import annotations

from pathlib import Path

import orjson
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.correlators.pairing import pair_start_end
from app.core.settings import get_settings
from app.db.base import Base
from app.detectors.error_detection import annotate_errors, top_error_clusters
from app.models.db_models import ErrorClusterModel, NormalizedEventModel, StepSummaryModel, UploadTaskModel
from app.schemas.common import NormalizedEvent
from app.services.cycle_inference import infer_missing_cycles
from app.services.cycle_service import aggregate_metric_steps, build_parameter_summaries
from app.services.streaming_aggregation import StreamingAggregationCoordinator


def _make_event(
    *,
    source_file: str,
    parser_name: str,
    epoch_ms: int,
    message: str,
    level: str = "INFO",
    component: str | None = None,
    cycle_no: int | None = None,
    sub_step: str | None = None,
    chip_name: str | None = None,
    event_kind: str | None = None,
    direction: str | None = None,
    duration_ms: float | None = None,
    method_name: str | None = None,
    exception_type: str | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        source_file=source_file,
        parser_name=parser_name,
        epoch_ms=epoch_ms,
        formatted_ms=str(epoch_ms),
        level=level,
        component=component,
        method_name=method_name,
        exception_type=exception_type,
        message=message,
        raw_text=message,
        cycle_no=cycle_no,
        sub_step=sub_step,
        chip_name=chip_name,
        event_kind=event_kind,
        direction=direction,
        duration_ms=duration_ms,
    )


def _sample_events() -> list[NormalizedEvent]:
    return [
        _make_event(
            source_file="a.log",
            parser_name="text_log",
            epoch_ms=1000,
            message="Current imaging cycle 1",
            component="Workflow",
            cycle_no=1,
        ),
        _make_event(
            source_file="a.log",
            parser_name="text_log",
            epoch_ms=1100,
            message="Row scan Done in 1100 ms",
            component="Imager",
            cycle_no=None,
            sub_step="Row scan Done",
            chip_name="ChipA",
            event_kind="metric",
            duration_ms=1100.0,
        ),
        _make_event(
            source_file="a.log",
            parser_name="text_log",
            epoch_ms=1200,
            message="Move slide from imager to chuck stage start. N1",
            component="Workflow",
            cycle_no=1,
            sub_step="Move slide from imager to chuck stage",
            chip_name="ChipA",
            event_kind="step",
            direction="start",
        ),
        _make_event(
            source_file="a.log",
            parser_name="text_log",
            epoch_ms=1300,
            message="Move slide from imager to chuck stage finished. N1",
            component="Workflow",
            cycle_no=1,
            sub_step="Move slide from imager to chuck stage",
            chip_name="ChipA",
            event_kind="step",
            direction="end",
        ),
        _make_event(
            source_file="a.log",
            parser_name="text_log",
            epoch_ms=1350,
            message="FineAlign Completed in 2500 ms",
            component="OpticalBoard",
            cycle_no=1,
            sub_step="FineAlign",
            chip_name="ChipA",
            event_kind="metric",
            duration_ms=2500.0,
        ),
        _make_event(
            source_file="a.log",
            parser_name="text_log",
            epoch_ms=1400,
            message="Timeout while moving stage 1234",
            level="ERROR",
            component="Workflow",
            cycle_no=1,
            method_name="RunWorkflow",
            exception_type="TimeoutException",
        ),
        _make_event(
            source_file="b.csv",
            parser_name="metrics_csv",
            epoch_ms=1450,
            message="scan-row-1",
            component="Imager",
            cycle_no=1,
            sub_step="imaging::ScanTotalTime",
            chip_name="ChipA",
            event_kind="metric",
            duration_ms=1000.0,
        ),
        _make_event(
            source_file="b.csv",
            parser_name="metrics_csv",
            epoch_ms=1460,
            message="scan-row-2",
            component="Imager",
            cycle_no=1,
            sub_step="imaging::ScanTotalTime",
            chip_name="ChipA",
            event_kind="metric",
            duration_ms=1200.0,
        ),
        _make_event(
            source_file="b.csv",
            parser_name="text_log",
            epoch_ms=1500,
            message="Timeout while moving stage 5678",
            level="ERROR",
            component="Workflow",
            cycle_no=1,
            method_name="RunWorkflow",
            exception_type="TimeoutException",
        ),
        _make_event(
            source_file="b.csv",
            parser_name="text_log",
            epoch_ms=2000,
            message="Current imaging cycle 2",
            component="Workflow",
            cycle_no=2,
        ),
    ]


def _expected_error_bounds(events: list[NormalizedEvent]) -> tuple[int, dict[str, dict[str, int | None]]]:
    total_errors = 0
    bounds: dict[str, dict[str, int | None]] = {}
    for event in events:
        signature = event.normalized_signature
        if not signature:
            continue
        total_errors += 1
        state = bounds.setdefault(signature, {"first": None, "last": None})
        if event.epoch_ms is None:
            continue
        if state["first"] is None or event.epoch_ms < int(state["first"]):
            state["first"] = int(event.epoch_ms)
        if state["last"] is None or event.epoch_ms > int(state["last"]):
            state["last"] = int(event.epoch_ms)
    return total_errors, bounds


def _normalize_event_row(row: NormalizedEventModel) -> dict:
    return {
        "source_file": row.source_file,
        "parser_name": row.parser_name,
        "message": row.message,
        "cycle_no": row.cycle_no,
        "normalized_signature": row.normalized_signature,
        "error_family": row.error_family,
        "severity": row.severity,
        "extra_json": orjson.loads(row.extra_json or "{}"),
    }


def _normalize_expected_event(event: NormalizedEvent) -> dict:
    return {
        "source_file": event.source_file,
        "parser_name": event.parser_name,
        "message": event.message,
        "cycle_no": event.cycle_no,
        "normalized_signature": event.normalized_signature,
        "error_family": event.error_family,
        "severity": event.severity,
        "extra_json": dict(event.extra_json or {}),
    }


def _normalize_step_row(row: StepSummaryModel) -> tuple:
    return (
        row.cycle_no,
        row.parameter_name,
        row.sub_step,
        row.component,
        row.chip_name,
        row.start_epoch_ms,
        row.end_epoch_ms,
        None if row.duration_ms is None else round(float(row.duration_ms), 6),
        None if row.threshold_ms is None else round(float(row.threshold_ms), 6),
        bool(row.is_over_threshold),
        row.start_time_text,
        row.end_time_text,
    )


def _normalize_expected_step(row) -> tuple:
    return (
        row.cycle_no,
        row.parameter_name,
        row.sub_step,
        row.component,
        row.chip_name,
        row.start_epoch_ms,
        row.end_epoch_ms,
        None if row.duration_ms is None else round(float(row.duration_ms), 6),
        None if row.threshold_ms is None else round(float(row.threshold_ms), 6),
        bool(row.is_over_threshold),
        row.start_time_text,
        row.end_time_text,
    )


def _step_sort_key(row: tuple) -> tuple:
    return (
        row[0] if row[0] is not None else -1,
        row[1] or "",
        row[2] or "",
        row[3] or "",
        row[4] or "",
        row[5] if row[5] is not None else -1,
        row[6] if row[6] is not None else -1,
        row[7] if row[7] is not None else -1.0,
        row[8] if row[8] is not None else -1.0,
        row[9],
        row[10] or "",
        row[11] or "",
    )


def _normalize_cluster_row(row: ErrorClusterModel) -> dict:
    return {
        "normalized_signature": row.normalized_signature,
        "error_family": row.error_family,
        "severity": row.severity,
        "representative_message": row.representative_message,
        "representative_exception": row.representative_exception,
        "component": row.component,
        "count": row.count,
        "first_seen_epoch_ms": row.first_seen_epoch_ms,
        "last_seen_epoch_ms": row.last_seen_epoch_ms,
    }


def test_streaming_aggregation_matches_existing_pipeline(tmp_path):
    db_path = tmp_path / "streaming.sqlite3"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    events = _sample_events()
    expected_events = annotate_errors(infer_missing_cycles([NormalizedEvent(**event.model_dump()) for event in events]))
    expected_paired = pair_start_end(expected_events)
    expected_metric = aggregate_metric_steps(expected_events)
    expected_base_steps = expected_paired + expected_metric
    expected_parameter_steps = build_parameter_summaries(expected_events, expected_base_steps)
    expected_steps = expected_base_steps + expected_parameter_steps
    expected_total_errors, expected_bounds = _expected_error_bounds(expected_events)
    expected_top_clusters = top_error_clusters(expected_events, limit=200)
    expected_clusters = [
        {
            "normalized_signature": row["normalized_signature"],
            "error_family": row["error_family"],
            "severity": row["severity"],
            "representative_message": row["display_signature"],
            "representative_exception": row["exception_type"],
            "component": row["component"],
            "count": row["count"],
            "first_seen_epoch_ms": expected_bounds.get(row["normalized_signature"], {}).get("first"),
            "last_seen_epoch_ms": expected_bounds.get(row["normalized_signature"], {}).get("last"),
        }
        for row in expected_top_clusters
    ]

    worker_a = tmp_path / "worker_a.jsonl"
    worker_b = tmp_path / "worker_b.jsonl"
    with worker_a.open("wb") as handle:
        for event in events[:6]:
            handle.write(orjson.dumps(event.model_dump()))
            handle.write(b"\n")
    with worker_b.open("wb") as handle:
        for event in events[6:]:
            handle.write(orjson.dumps(event.model_dump()))
            handle.write(b"\n")

    with SessionLocal() as db:
        task = UploadTaskModel(task_uuid="stream-task", filename="sample.zip", stored_path=str(tmp_path))
        db.add(task)
        db.commit()
        db.refresh(task)

        coordinator = StreamingAggregationCoordinator(db, task.id, get_settings())
        coordinator.clear_existing_outputs()

        merge_result = coordinator.merge_intermediate_results(
            [
                {"path": "a.log", "output_path": str(worker_a)},
                {"path": "b.csv", "output_path": str(worker_b)},
            ]
        )
        assert merge_result["total_events"] == len(events)

        context = coordinator.build_cycle_context(total_events=len(events))
        result = coordinator.postprocess_and_aggregate(context, total_events=len(events))

        assert result["total_errors"] == expected_total_errors
        assert result["step_summary_count"] == len(expected_steps)
        assert result["cluster_count"] == len(expected_clusters)

        ordered_stmt = (
            select(NormalizedEventModel)
            .where(NormalizedEventModel.task_id == task.id)
            .order_by(
                func.coalesce(NormalizedEventModel.epoch_ms, 0).asc(),
                NormalizedEventModel.source_file.asc(),
                NormalizedEventModel.message.asc(),
                NormalizedEventModel.id.asc(),
            )
        )
        stored_events = list(db.scalars(ordered_stmt))
        assert [_normalize_event_row(row) for row in stored_events] == [
            _normalize_expected_event(event) for event in expected_events
        ]

        stored_steps = list(
            db.scalars(
                select(StepSummaryModel)
                .where(StepSummaryModel.task_id == task.id)
                .order_by(StepSummaryModel.id.asc())
            )
        )
        assert sorted((_normalize_step_row(row) for row in stored_steps), key=_step_sort_key) == sorted(
            (_normalize_expected_step(step) for step in expected_steps),
            key=_step_sort_key,
        )

        stored_clusters = list(
            db.scalars(
                select(ErrorClusterModel)
                .where(ErrorClusterModel.task_id == task.id)
                .order_by(ErrorClusterModel.count.desc(), ErrorClusterModel.id.asc())
            )
        )
        assert [_normalize_cluster_row(row) for row in stored_clusters] == expected_clusters


def test_memory_guard_degrades_batches(tmp_path, monkeypatch):
    db_path = tmp_path / "guard.sqlite3"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with SessionLocal() as db:
        task = UploadTaskModel(task_uuid="guard-task", filename="guard.zip", stored_path=str(tmp_path))
        db.add(task)
        db.commit()
        db.refresh(task)

        coordinator = StreamingAggregationCoordinator(db, task.id, get_settings())
        before = coordinator.memory_guard_report()["current_batches"]
        monkeypatch.setattr(
            coordinator,
            "_memory_snapshot",
            lambda: {"system_percent": 99.0, "available_mb": 32.0, "process_rss_mb": 128.0},
        )
        monkeypatch.setattr("app.services.streaming_aggregation.time.sleep", lambda *_args, **_kwargs: None)

        assert coordinator._apply_memory_guard("test", collect=False) is True
        after = coordinator.memory_guard_report()["current_batches"]

        assert after["merge_insert_batch"] < before["merge_insert_batch"]
        assert after["update_batch"] < before["update_batch"]
        assert after["step_insert_batch"] < before["step_insert_batch"]
        assert coordinator.memory_guard_report()["trigger_count"] == 1
