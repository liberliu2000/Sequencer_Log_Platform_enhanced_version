from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.db.session import SessionLocal
from app.models.db_models import SolutionRecordModel, SolutionReviewRecordModel
from app.services.solution_repository import SolutionRepositoryService
from app.services.solution_review_service import SolutionReviewService


def _payload(seed: str) -> dict:
    return {
        "task_uuid": f"task_{seed}",
        "error_name": f"Motion timeout {seed}",
        "error_category": "runtime_exception",
        "module": "运动平台",
        "submodule": "XYZ 平台",
        "error_code": "MP-1001",
        "message": f"Axis timeout while homing {seed}",
        "normalized_signature": f"sig_{seed}",
        "trigger_scenario": "开机后执行归零流程，平台在 Z 轴回原点阶段超时",
        "impact_scope": "当前批次无法继续运行",
        "root_cause_analysis": "Z 轴回零等待条件过严，传感器抖动导致状态机未收敛。",
        "verified_solution": "放宽去抖时间并补充传感器异常重试，问题已在现场复现后消失。",
        "workaround": "重启后单独执行一次回零流程。",
        "owner_department": "运动平台",
        "submitter": "pytest",
        "source": "unit_test",
        "reusable": True,
    }


def test_solution_repository_create_search_export():
    db = SessionLocal()
    record_id = None
    export_path = None
    seed = uuid4().hex[:8]
    try:
        service = SolutionRepositoryService(db)
        created = service.create_record(_payload(seed))
        record_id = created["id"]
        assert created["error_code_prefix"] == "MP"
        rows = service.list_records(normalized_signature=f"sig_{seed}", limit=10)
        assert any(row["id"] == record_id for row in rows)
        export_path = Path(service.export_records("json"))
        assert export_path.exists()
    finally:
        if record_id:
            row = db.get(SolutionRecordModel, record_id)
            if row:
                db.delete(row)
                db.commit()
        if export_path and export_path.exists():
            export_path.unlink()
        db.close()


def test_solution_review_submit_and_manual_review():
    db = SessionLocal()
    review_id = None
    linked_solution_id = None
    seed = uuid4().hex[:8]
    try:
        payload = _payload(seed)
        payload["verified_solution"] = ""
        review_service = SolutionReviewService(db)
        review = review_service.submit_for_review(payload)
        review_id = review["id"]
        assert review["review_status"] == "needs_revision"

        manual = review_service.manually_review(
            review_id,
            review_status="approved",
            reviewer="pytest",
            notes="补充人工确认，可入库",
        )
        linked_solution_id = manual["linked_solution_id"]
        assert manual["review_status"] == "approved"
        assert linked_solution_id is not None
    finally:
        if linked_solution_id:
            row = db.get(SolutionRecordModel, linked_solution_id)
            if row:
                db.delete(row)
                db.commit()
        if review_id:
            review_row = db.get(SolutionReviewRecordModel, review_id)
            if review_row:
                db.delete(review_row)
                db.commit()
        db.close()
