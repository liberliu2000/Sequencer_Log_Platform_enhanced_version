from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.correlators.pairing import pair_start_end
from app.core.settings import get_settings
from app.db.base import Base
from app.detectors.error_detection import annotate_errors
from app.models.db_models import ParameterResultModel, UploadTaskModel
from app.repositories.task_repository import TaskRepository
from app.schemas.common import NormalizedEvent
from app.services.cycle_inference import infer_missing_cycles
from app.services.cycle_service import aggregate_metric_steps, build_parameter_summaries, build_unified_parameter_results
from app.services.query_service import QueryService
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
        _make_event(source_file="a.log", parser_name="text_log", epoch_ms=1000, message="Current imaging cycle 1", component="Workflow", cycle_no=1),
        _make_event(source_file="a.log", parser_name="text_log", epoch_ms=1100, message="Row scan Done in 1100 ms", component="Imager", sub_step="Row scan Done", chip_name="ChipA", duration_ms=1100.0),
        _make_event(source_file="a.log", parser_name="text_log", epoch_ms=1200, message="Move slide from imager to chuck stage start. N1", component="Workflow", cycle_no=1, sub_step="Move slide from imager to chuck stage", chip_name="ChipA", event_kind="step", direction="start"),
        _make_event(source_file="a.log", parser_name="text_log", epoch_ms=1300, message="Move slide from imager to chuck stage finished. N1", component="Workflow", cycle_no=1, sub_step="Move slide from imager to chuck stage", chip_name="ChipA", event_kind="step", direction="end"),
        _make_event(source_file="a.log", parser_name="text_log", epoch_ms=1350, message="FineAlign Completed in 2500 ms", component="OpticalBoard", cycle_no=1, sub_step="FineAlign", chip_name="ChipA", duration_ms=2500.0),
        _make_event(source_file="a.log", parser_name="text_log", epoch_ms=1400, message="Timeout while moving stage 1234", level="ERROR", component="Workflow", cycle_no=1, method_name="RunWorkflow", exception_type="TimeoutException"),
        _make_event(source_file="b.csv", parser_name="metrics_csv", epoch_ms=1450, message="scan-row-1", component="Imager", cycle_no=1, sub_step="imaging::ScanTotalTime", chip_name="ChipA", event_kind="metric", duration_ms=1000.0),
        _make_event(source_file="b.csv", parser_name="metrics_csv", epoch_ms=1460, message="scan-row-2", component="Imager", cycle_no=1, sub_step="imaging::ScanTotalTime", chip_name="ChipA", event_kind="metric", duration_ms=1200.0),
        _make_event(source_file="b.csv", parser_name="text_log", epoch_ms=1500, message="Timeout while moving stage 5678", level="ERROR", component="Workflow", cycle_no=1, method_name="RunWorkflow", exception_type="TimeoutException"),
        _make_event(source_file="b.csv", parser_name="text_log", epoch_ms=2000, message="Current imaging cycle 2", component="Workflow", cycle_no=2),
    ]


def _normalized_pipeline_outputs() -> tuple[list[NormalizedEvent], list[dict], list[dict]]:
    expected_events = annotate_errors(infer_missing_cycles([NormalizedEvent(**event.model_dump()) for event in _sample_events()]))
    expected_paired = pair_start_end(expected_events)
    expected_metric = aggregate_metric_steps(expected_events)
    expected_base_steps = expected_paired + expected_metric
    expected_parameter_steps = build_parameter_summaries(expected_events, expected_base_steps)
    expected_steps = expected_base_steps + expected_parameter_steps
    expected_results = build_unified_parameter_results(expected_events, expected_base_steps)
    return (
        expected_events,
        [step.model_dump(mode="json") for step in expected_steps],
        [result.model_dump(mode="json") for result in expected_results],
    )


def _create_session_factory(tmp_path: Path):
    db_path = tmp_path / "query-parameter-results.sqlite3"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_query_service_reads_materialized_parameter_results(tmp_path, monkeypatch):
    SessionLocal = _create_session_factory(tmp_path)
    events = _sample_events()
    _, _, expected_results = _normalized_pipeline_outputs()

    worker_a = tmp_path / "worker_a.jsonl"
    worker_b = tmp_path / "worker_b.jsonl"
    with worker_a.open("wb") as handle:
        for event in events[:6]:
            handle.write(json.dumps(event.model_dump()).encode("utf-8"))
            handle.write(b"\n")
    with worker_b.open("wb") as handle:
        for event in events[6:]:
            handle.write(json.dumps(event.model_dump()).encode("utf-8"))
            handle.write(b"\n")

    with SessionLocal() as db:
        task = UploadTaskModel(task_uuid="materialized-task", filename="sample.zip", stored_path=str(tmp_path), status="completed")
        db.add(task)
        db.commit()
        db.refresh(task)

        coordinator = StreamingAggregationCoordinator(db, task.id, get_settings())
        coordinator.clear_existing_outputs()
        coordinator.merge_intermediate_results(
            [
                {"path": "a.log", "output_path": str(worker_a)},
                {"path": "b.csv", "output_path": str(worker_b)},
            ]
        )
        cycle_context = coordinator.build_cycle_context(total_events=len(events))
        coordinator.postprocess_and_aggregate(cycle_context, total_events=len(events))

        query = QueryService(db)
        monkeypatch.setattr(query, "_rebuild_parameter_results_from_events", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not rebuild")))

        rows = query.get_parameter_results(task.id)
        stored_count = int(
            db.scalar(select(func.count()).select_from(ParameterResultModel).where(ParameterResultModel.task_id == task.id))
            or 0
        )

        assert rows == expected_results
        assert stored_count == len(expected_results)


def test_query_service_streaming_rebuild_backfills_parameter_results_for_legacy_task(tmp_path):
    SessionLocal = _create_session_factory(tmp_path)
    expected_events, expected_steps, expected_results = _normalized_pipeline_outputs()

    with SessionLocal() as db:
        task = UploadTaskModel(task_uuid="legacy-task", filename="legacy.zip", stored_path=str(tmp_path), status="completed")
        db.add(task)
        db.commit()
        db.refresh(task)

        repo = TaskRepository(db)
        repo.save_events(
            task.id,
            (
                {
                    **event.model_dump(mode="json"),
                    "extra_json": json.dumps(event.extra_json or {}, ensure_ascii=False),
                }
                for event in expected_events
            ),
        )
        repo.save_step_summaries(task.id, expected_steps)

        query = QueryService(db)
        rows = query.get_parameter_results(task.id)
        stored_rows = list(
            db.execute(
                select(ParameterResultModel).where(ParameterResultModel.task_id == task.id)
            ).mappings()
        )

        assert rows == expected_results
        assert len(stored_rows) == len(expected_results)
