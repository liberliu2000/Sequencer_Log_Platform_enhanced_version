from __future__ import annotations

import argparse
import json

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.detectors.error_detection import normalize_error_signature, top_error_clusters
from app.models.db_models import ErrorClusterModel, NormalizedEventModel, UploadTaskModel
from app.schemas.common import NormalizedEvent


def _event_model_to_schema(row: NormalizedEventModel) -> NormalizedEvent:
    extra_json = {}
    if row.extra_json:
        try:
            extra_json = json.loads(row.extra_json)
        except Exception:
            extra_json = {}
    return NormalizedEvent(
        source_file=row.source_file,
        parser_name=row.parser_name,
        original_time_text=row.original_time_text,
        parsed_datetime=row.parsed_datetime,
        epoch_ms=row.epoch_ms,
        formatted_ms=row.formatted_ms,
        level=row.level,
        component=row.component,
        module=row.module,
        thread=row.thread,
        method_name=row.method_name,
        class_name=row.class_name,
        source_path=row.source_path,
        line_no=row.line_no,
        message=row.message,
        raw_text=row.raw_text,
        cycle_no=row.cycle_no,
        sub_step=row.sub_step,
        chip_name=row.chip_name,
        stage_name=row.stage_name,
        board_name=row.board_name,
        event_kind=row.event_kind,
        direction=row.direction,
        duration_ms=row.duration_ms,
        status=row.status,
        error_code=row.error_code,
        exception_type=row.exception_type,
        normalized_signature=row.normalized_signature,
        error_family=row.error_family,
        severity=row.severity,
        cycle_inferred=row.cycle_inferred,
        cycle_infer_method=row.cycle_infer_method,
        cycle_infer_confidence=row.cycle_infer_confidence,
        cycle_infer_reason=row.cycle_infer_reason,
        extra_json=extra_json,
    )


def rebuild_task(task: UploadTaskModel) -> dict[str, int | str]:
    db = SessionLocal()
    try:
        rows = list(
            db.scalars(
                select(NormalizedEventModel)
                .where(NormalizedEventModel.task_id == task.id)
                .order_by(NormalizedEventModel.epoch_ms.asc(), NormalizedEventModel.id.asc())
            )
        )
        events: list[NormalizedEvent] = []
        changed_events = 0

        for row in rows:
            event = _event_model_to_schema(row)
            signature, family, severity = normalize_error_signature(event)
            if (
                row.normalized_signature != signature
                or row.error_family != family
                or row.severity != severity
                or row.extra_json != json.dumps(event.extra_json or {}, ensure_ascii=False)
            ):
                changed_events += 1
            row.normalized_signature = signature
            row.error_family = family
            row.severity = severity
            row.extra_json = json.dumps(event.extra_json or {}, ensure_ascii=False)
            events.append(event)

        db.execute(delete(ErrorClusterModel).where(ErrorClusterModel.task_id == task.id))
        cluster_rows = top_error_clusters(events, limit=2000)
        clusters: list[ErrorClusterModel] = []
        for item in cluster_rows:
            matching = [event for event in events if event.normalized_signature == item["normalized_signature"]]
            first_seen = min((event.epoch_ms for event in matching if event.epoch_ms is not None), default=None)
            last_seen = max((event.epoch_ms for event in matching if event.epoch_ms is not None), default=None)
            clusters.append(
                ErrorClusterModel(
                    task_id=task.id,
                    normalized_signature=item["normalized_signature"],
                    error_family=item["error_family"],
                    severity=item["severity"],
                    representative_message=item["display_signature"],
                    representative_exception=item["exception_type"],
                    component=item["component"],
                    count=item["count"],
                    first_seen_epoch_ms=first_seen,
                    last_seen_epoch_ms=last_seen,
                )
            )
        if clusters:
            db.add_all(clusters)

        task.total_errors = sum(1 for event in events if event.normalized_signature)
        db.commit()
        return {
            "task_id": task.id,
            "task_uuid": task.task_uuid,
            "event_count": len(rows),
            "changed_events": changed_events,
            "cluster_count": len(clusters),
            "total_errors": task.total_errors,
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild stored error families and error clusters with the latest message-based rules.")
    parser.add_argument("--task-uuid", dest="task_uuid", help="Only rebuild the specified task UUID.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stmt = select(UploadTaskModel).order_by(UploadTaskModel.id.asc())
        if args.task_uuid:
            stmt = stmt.where(UploadTaskModel.task_uuid == args.task_uuid)
        tasks = list(db.scalars(stmt))
    finally:
        db.close()

    if not tasks:
        target = args.task_uuid or "ALL"
        print(f"No tasks found for target={target}")
        return

    print(f"Rebuilding error families for {len(tasks)} task(s)...")
    for task in tasks:
        summary = rebuild_task(task)
        print(
            f"[task {summary['task_id']}] {summary['task_uuid']} | "
            f"events={summary['event_count']} changed={summary['changed_events']} "
            f"clusters={summary['cluster_count']} total_errors={summary['total_errors']}"
        )


if __name__ == "__main__":
    main()
