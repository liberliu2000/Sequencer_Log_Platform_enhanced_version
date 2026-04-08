from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.bootstrap import bootstrap_for_local_run

bootstrap_for_local_run()

from app.db.session import SessionLocal
from app.models.db_models import NormalizedEventModel, ParameterResultModel, StepSummaryModel, UploadTaskModel
from app.utils.side_inference import normalize_side_scope, repair_scope_inference


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except Exception:
        return None


def _load_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _is_scope_backfill_candidate(side_scope: str | None, side_confidence: Any) -> bool:
    normalized = normalize_side_scope(side_scope)
    if not normalized:
        return True
    if normalized in {"A", "B"}:
        return True
    confidence = _safe_float(side_confidence)
    return confidence is None or confidence < 0.75


def _update_field(changes: dict[str, Any], name: str, before: Any, after: Any) -> None:
    if before != after:
        changes[name] = {"before": before, "after": after}


def _repair_normalized_event(row: NormalizedEventModel) -> dict[str, Any]:
    inference = repair_scope_inference(
        source_file=row.source_file,
        message=row.message,
        raw_text=row.raw_text,
        sub_step=row.sub_step,
        chip_name=row.chip_name,
        stage_name=row.stage_name,
        stage_key=row.stage_key,
        chuck_no=row.chuck_no,
        slot_no=row.slot_no,
        instrument_scope=row.instrument_scope,
        side_scope=row.side_scope,
        side_group=row.side_group,
        side_confidence=row.side_confidence,
        side_evidence=_load_json_dict(row.side_evidence),
    )
    changes: dict[str, Any] = {}
    _update_field(changes, "side_scope", row.side_scope, inference.side_scope)
    _update_field(changes, "side_group", row.side_group, inference.side_group)
    _update_field(changes, "side_confidence", row.side_confidence, inference.side_confidence)
    _update_field(changes, "side_evidence", _load_json_dict(row.side_evidence), inference.side_evidence)
    if changes:
        row.side_scope = inference.side_scope
        row.side_group = inference.side_group
        row.side_confidence = inference.side_confidence
        row.side_evidence = json.dumps(inference.side_evidence or {}, ensure_ascii=False, default=str)
    return changes


def _repair_step_summary(row: StepSummaryModel) -> dict[str, Any]:
    inference = repair_scope_inference(
        source_file=None,
        message=row.sub_step,
        raw_text=row.sub_step,
        sub_step=row.sub_step,
        chip_name=row.chip_name,
        stage_key=row.stage_key,
        chuck_no=row.chuck_no,
        slot_no=row.slot_no,
        instrument_scope=row.instrument_scope,
        side_scope=row.side_scope,
        side_group=row.side_group,
        side_confidence=row.side_confidence,
        side_evidence=_load_json_dict(row.side_evidence),
    )
    changes: dict[str, Any] = {}
    _update_field(changes, "side_scope", row.side_scope, inference.side_scope)
    _update_field(changes, "side_group", row.side_group, inference.side_group)
    _update_field(changes, "side_confidence", row.side_confidence, inference.side_confidence)
    _update_field(changes, "side_evidence", _load_json_dict(row.side_evidence), inference.side_evidence)
    if changes:
        row.side_scope = inference.side_scope
        row.side_group = inference.side_group
        row.side_confidence = inference.side_confidence
        row.side_evidence = json.dumps(inference.side_evidence or {}, ensure_ascii=False, default=str)
    return changes


def _repair_parameter_result(row: ParameterResultModel) -> dict[str, Any]:
    inference = repair_scope_inference(
        source_file=row.source_file,
        message=row.start_message or row.end_message,
        raw_text=" | ".join(part for part in [row.start_message, row.end_message] if part),
        sub_step=row.parameter_display_name,
        start_message=row.start_message,
        end_message=row.end_message,
        parameter_name=row.parameter_name,
        parameter_display_name=row.parameter_display_name,
        slide=row.slide,
        chip_name=row.chip_name,
        stage_key=row.stage_key,
        chuck_no=row.chuck_no,
        slot_no=row.slot_no,
        instrument_scope=row.instrument_scope,
        side_scope=row.side_scope,
        side_group=row.side_group,
        side_confidence=row.side_confidence,
        side_evidence=_load_json_dict(row.side_evidence),
    )
    changes: dict[str, Any] = {}
    _update_field(changes, "side_scope", row.side_scope, inference.side_scope)
    _update_field(changes, "side_group", row.side_group, inference.side_group)
    _update_field(changes, "side_confidence", row.side_confidence, inference.side_confidence)
    _update_field(changes, "side_evidence", _load_json_dict(row.side_evidence), inference.side_evidence)
    if changes:
        row.side_scope = inference.side_scope
        row.side_group = inference.side_group
        row.side_confidence = inference.side_confidence
        row.side_evidence = json.dumps(inference.side_evidence or {}, ensure_ascii=False, default=str)
    return changes


def run_backfill(task_uuid: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "task_uuid": task_uuid,
        "dry_run": dry_run,
        "normalized_events": {"scanned": 0, "updated": 0},
        "step_summaries": {"scanned": 0, "updated": 0},
        "parameter_results": {"scanned": 0, "updated": 0},
        "touched_task_ids": [],
    }
    touched_task_ids: set[int] = set()

    with SessionLocal() as db:
        task_id_filter: int | None = None
        if task_uuid:
            task = db.scalar(select(UploadTaskModel).where(UploadTaskModel.task_uuid == task_uuid))
            if task is None:
                raise SystemExit(f"task_uuid 不存在: {task_uuid}")
            task_id_filter = int(task.id)

        candidates = [
            (
                "normalized_events",
                NormalizedEventModel,
                _repair_normalized_event,
            ),
            (
                "step_summaries",
                StepSummaryModel,
                _repair_step_summary,
            ),
            (
                "parameter_results",
                ParameterResultModel,
                _repair_parameter_result,
            ),
        ]

        for bucket_name, model, repair_fn in candidates:
            stmt = select(model).where(
                or_(
                    model.side_scope.is_(None),
                    model.side_scope.in_(["A", "B"]),
                    model.side_confidence.is_(None),
                    model.side_confidence < 0.75,
                )
            )
            if task_id_filter is not None:
                stmt = stmt.where(model.task_id == task_id_filter)
            rows = list(db.execute(stmt).scalars())
            summary[bucket_name]["scanned"] = len(rows)
            for row in rows:
                changes = repair_fn(row)
                if not changes:
                    continue
                summary[bucket_name]["updated"] += 1
                touched_task_ids.add(int(row.task_id))

        if touched_task_ids and not dry_run:
            now = datetime.utcnow()
            tasks = db.execute(select(UploadTaskModel).where(UploadTaskModel.id.in_(sorted(touched_task_ids)))).scalars()
            for task in tasks:
                task.updated_at = now
            db.commit()
        else:
            db.rollback()

    summary["touched_task_ids"] = sorted(touched_task_ids)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill side scope for rows that were stored as Unassigned/coarse side.")
    parser.add_argument("--task-uuid", help="Only repair one task_uuid", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Scan and report without committing")
    args = parser.parse_args()
    result = run_backfill(task_uuid=args.task_uuid, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
