from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.db_models import (
    NormalizedEventModel,
    RegistrationChallengeModel,
    SolutionRecordModel,
    SolutionReviewRecordModel,
    StepSummaryModel,
    UploadTaskModel,
    UserModel,
)


def test_health(client: TestClient):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_solution_review_api_flow(client: TestClient):
    seed = uuid4().hex[:8]
    payload = {
        "task_uuid": f"task_{seed}",
        "submission_type": "solution_record",
        "error_name": f"Software alarm {seed}",
        "error_category": "logic_exception",
        "module": "scheduler",
        "submodule": "state_machine",
        "message": f"Unexpected transition {seed} while scheduler switched states and received duplicated callback events",
        "normalized_signature": f"sw_sig_{seed}",
        "trigger_scenario": "状态机在切换运行态时收到了重复回调，导致异常路径持续复现。",
        "impact_scope": "单次流程失败",
        "root_cause_analysis": "状态机缺少幂等保护，重复触发后进入非法状态。",
        "verified_solution": "增加状态判重逻辑，并在进入 running 前补充一致性检查。",
        "workaround": "重试前先复位任务状态并清理缓存事件。",
        "owner_department": "scheduler",
        "submitter": "pytest_api",
        "source": "api_test",
        "task_clusters": ["流程执行"],
        "message_keywords": ["scheduler", "transition", "callback"],
        "reusable": True,
    }
    review_resp = client.post("/api/v1/solution-reviews", json=payload)
    assert review_resp.status_code == 200
    review_item = review_resp.json()["item"]
    assert review_item["review_status"] == "pending_review"

    manual_resp = client.post(
        f"/api/v1/solution-reviews/{review_item['id']}/manual-review",
        json={"review_status": "approved", "notes": "pytest approve"},
    )
    assert manual_resp.status_code == 200
    manual_item = manual_resp.json()["item"]
    assert manual_item["linked_solution_id"] is not None

    list_resp = client.get(
        "/api/v1/solution-repository/records",
        params={"normalized_signature": payload["normalized_signature"]},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(row["normalized_signature"] == payload["normalized_signature"] for row in items)

    db = SessionLocal()
    try:
        if manual_item.get("linked_solution_id"):
            solution_row = db.get(SolutionRecordModel, manual_item["linked_solution_id"])
            if solution_row:
                db.delete(solution_row)
        review_row = db.get(SolutionReviewRecordModel, review_item["id"])
        if review_row:
            db.delete(review_row)
        db.commit()
    finally:
        db.close()


def test_register_verify_and_admin_review_flow(client: TestClient):
    seed = uuid4().hex[:8]
    username = f"user_{seed}"
    email = f"{username}@example.com"

    request_code_resp = client.post(
        "/api/v1/auth/register/request-code",
        json={"username": username, "email": email, "password": "Password_123", "registration_note": "pytest"},
    )
    assert request_code_resp.status_code == 200
    assert request_code_resp.json()["status"] == "verification_sent"

    db = SessionLocal()
    try:
        challenge = db.query(RegistrationChallengeModel).filter(RegistrationChallengeModel.username == username).one()
        challenge.code_hash = __import__("hashlib").sha256(f"{challenge.id}:123456".encode("utf-8")).hexdigest()
        db.commit()
    finally:
        db.close()

    verify_resp = client.post("/api/v1/auth/register/verify-email", json={"login_name": username, "code": "123456"})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["next_status"] == "verified_can_submit"
    verification_token = verify_resp.json()["verification_token"]

    register_resp = client.post("/api/v1/auth/register", json={"verification_token": verification_token})
    assert register_resp.status_code == 200
    assert register_resp.json()["next_status"] == "pending_admin_approval"

    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.username == username).one()
        user_id = user.id
    finally:
        db.close()

    approve_resp = client.post(f"/api/v1/admin/users/{user_id}/status", json={"action": "approve"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["item"]["status"] == "approved"


def test_movement_timeline_error_points_api(client: TestClient):
    seed = uuid4().hex[:8]
    task_uuid = f"timeline_{seed}"
    db = SessionLocal()
    try:
        task = UploadTaskModel(
            task_uuid=task_uuid,
            filename=f"{task_uuid}.log",
            stored_path=f"/tmp/{task_uuid}.log",
            status="done",
        )
        db.add(task)
        db.flush()
        db.add(
            StepSummaryModel(
                task_id=task.id,
                cycle_no=1,
                sub_step="MoveToScan",
                component="Scanner_1",
                chip_name="chipA",
                start_epoch_ms=1710000000000,
                end_epoch_ms=1710000005000,
                duration_ms=5000,
                start_time_text="2024-03-09 16:00:00",
                end_time_text="2024-03-09 16:00:05",
            )
        )
        db.add(
            NormalizedEventModel(
                task_id=task.id,
                source_file=f"{task_uuid}.log",
                parser_name="service_log",
                level="ERROR",
                message="Scanner move timeout",
                raw_text="Scanner move timeout",
                cycle_no=1,
                component="Scanner_1",
                sub_step="MoveToScan",
                epoch_ms=1710000002500,
                formatted_ms="2024-03-09 16:00:02.500",
                normalized_signature="scanner_move_timeout",
                error_family="timeout",
                severity="error",
                status="error",
            )
        )
        db.commit()

        timeline_resp = client.get(f"/api/v1/tasks/{task_uuid}/movement-timeline", params={"cycle_no": 1})
        assert timeline_resp.status_code == 200
        timeline_rows = timeline_resp.json()
        assert timeline_rows

        error_resp = client.get(f"/api/v1/tasks/{task_uuid}/movement-timeline/errors", params={"cycle_no": 1})
        assert error_resp.status_code == 200
        error_rows = error_resp.json()
        assert error_rows
        assert error_rows[0]["normalized_signature"] == "scanner_move_timeout"
        assert error_rows[0]["error_family"] == "timeout"
        assert error_rows[0]["track"] == "Scanner_1 | Cycle 1"
    finally:
        cleanup_db = SessionLocal()
        try:
            task = cleanup_db.query(UploadTaskModel).filter(UploadTaskModel.task_uuid == task_uuid).one_or_none()
            if task is not None:
                cleanup_db.query(NormalizedEventModel).filter(NormalizedEventModel.task_id == task.id).delete()
                cleanup_db.query(StepSummaryModel).filter(StepSummaryModel.task_id == task.id).delete()
                cleanup_db.delete(task)
                cleanup_db.commit()
        finally:
            cleanup_db.close()
        db.close()
