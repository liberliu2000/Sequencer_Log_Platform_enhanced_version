import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.db_models import (
    AnnouncementModel,
    NormalizedEventModel,
    SolutionMessageKeywordModel,
    SolutionModuleLinkModel,
    SolutionRecordModel,
    SolutionReviewRecordModel,
    SolutionTagLinkModel,
    SolutionTaskClusterLinkModel,
    SolutionTaskLinkModel,
    StepSummaryModel,
    UploadTaskModel,
    UserModel,
    UserSessionModel,
)


def test_health(client: TestClient):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root_endpoint(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Streamlit Parity Console" in resp.text
    assert "web-assets/app.js" in resp.text
    assert "/api/v1/health" in resp.text
    assert "LLM 诊断" in resp.text


def test_web_assets_js_route(client: TestClient):
    resp = client.get("/web-assets/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert "renderCurrentPage" in resp.text


def test_favicon_endpoint(client: TestClient):
    resp = client.get("/favicon.ico")
    assert resp.status_code == 204


def test_cors_preflight_for_protected_api_is_not_blocked_by_auth():
    test_client = TestClient(app)
    resp = test_client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "http://172.19.56.195:1122",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin")


def test_cors_preflight_for_upload_api_is_not_blocked_by_auth():
    test_client = TestClient(app)
    resp = test_client.options(
        "/api/v1/tasks/upload",
        headers={
            "Origin": "http://172.19.56.195:1122",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin")
    assert "POST" in str(resp.headers.get("access-control-allow-methods") or "").upper()


def test_module_prefixes_and_error_code_generation(client: TestClient):
    prefixes_resp = client.get("/api/v1/module-prefixes")
    assert prefixes_resp.status_code == 200
    payload = prefixes_resp.json()
    assert payload["items"]
    optics_prefix = payload["module_prefixes"].get("optics")
    assert optics_prefix == "OP"

    generate_resp = client.post("/api/v1/error-code/generate", json={"module": "optics"})
    assert generate_resp.status_code == 200
    generated = generate_resp.json()
    assert generated["module"] == "optics"
    assert generated["prefix"] == "OP"
    assert generated["error_code"].startswith("OP")
    assert len(generated["error_code"]) == 6


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


def test_system_runtime_endpoint(client: TestClient):
    resp = client.get("/api/v1/system/runtime")
    assert resp.status_code == 200
    payload = resp.json()
    assert "cpu" in payload
    assert "memory" in payload
    assert "disk" in payload
    assert "policy" in payload
    assert "guard" in payload
    assert payload["current_user"]["is_admin"] is True


def test_solution_repository_import_and_ask(client: TestClient):
    seed = uuid4().hex[:8]
    error_name = f"Imported solution {seed}"
    file_payload = [
        {
            "module": "scheduler",
            "error_name": error_name,
            "message": f"Scheduler transition failure {seed}",
            "normalized_signature": f"import_sig_{seed}",
            "trigger_scenario": f"Scheduler received duplicated callback {seed}",
            "root_cause_analysis": "状态机缺少幂等保护，重复触发后进入非法状态。",
            "verified_solution": "增加状态判重逻辑，并在进入 running 前补充一致性检查。",
            "workaround": "清理重复事件后重试任务。",
            "task_clusters": ["流程执行"],
            "message_keywords": ["scheduler", seed],
        }
    ]

    import_resp = client.post(
        "/api/v1/solution-repository/import",
        data={"preserve_error_codes": "true"},
        files={
            "file": (
                "solutions.json",
                json.dumps(file_payload, ensure_ascii=False).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert import_resp.status_code == 200
    import_item = import_resp.json()["item"]
    assert import_item["created"] == 1
    assert import_item["failed"] == 0
    assert import_item["items"][0]["error_code"].startswith("SC")

    ask_resp = client.post("/api/v1/solution-repository/ask", json={"question": f"{seed} 这个问题应该怎么处理？"})
    assert ask_resp.status_code == 200
    ask_item = ask_resp.json()["item"]
    assert ask_item["candidate_count"] >= 1
    assert ask_item["matches"]
    assert any(row["error_name"] == error_name for row in ask_item["matches"])

    db = SessionLocal()
    try:
        row = db.query(SolutionRecordModel).filter(SolutionRecordModel.error_name == error_name).one_or_none()
        if row is not None:
            db.query(SolutionTaskLinkModel).filter(SolutionTaskLinkModel.solution_id == row.id).delete()
            db.query(SolutionModuleLinkModel).filter(SolutionModuleLinkModel.solution_id == row.id).delete()
            db.query(SolutionTaskClusterLinkModel).filter(SolutionTaskClusterLinkModel.solution_id == row.id).delete()
            db.query(SolutionTagLinkModel).filter(SolutionTagLinkModel.solution_id == row.id).delete()
            db.query(SolutionMessageKeywordModel).filter(SolutionMessageKeywordModel.solution_id == row.id).delete()
            db.delete(row)
            db.commit()
    finally:
        db.close()


def test_register_and_admin_review_flow(client: TestClient):
    seed = uuid4().hex[:8]
    username = f"user_{seed}"
    email = f"{username}@example.com"

    register_resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "Password_123", "registration_note": "pytest"},
    )
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

def test_reset_password_by_username_email_flow(client: TestClient):
    seed = uuid4().hex[:8]
    username = f"reset_{seed}"
    email = f"{username}@example.com"

    register_resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "Password_123"},
    )
    assert register_resp.status_code == 200

    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.username == username).one()
        user_id = user.id
    finally:
        db.close()

    approve_resp = client.post(f"/api/v1/admin/users/{user_id}/status", json={"action": "approve"})
    assert approve_resp.status_code == 200

    reset_resp = client.post(
        "/api/v1/auth/reset-password",
        json={"username": username, "email": email, "new_password": "Reset_45678"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["user"]["username"] == username

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"login_name": username, "password": "Reset_45678"},
    )
    assert login_resp.status_code == 200

    cleanup_db = SessionLocal()
    try:
        user = cleanup_db.query(UserModel).filter(UserModel.username == username).one_or_none()
        if user is not None:
            cleanup_db.query(UserSessionModel).filter(UserSessionModel.user_id == user.id).delete()
            cleanup_db.delete(user)
            cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_announcements_public_and_admin_flow(client: TestClient):
    create_resp = client.post(
        "/api/v1/admin/announcements",
        json={"title": "pytest announcement", "summary": "announce summary", "is_pinned": True},
    )
    assert create_resp.status_code == 200
    item = create_resp.json()["item"]
    assert item["is_pinned"] is True
    assert item["updated_by"] == "Yanbo"

    list_resp = client.get("/api/v1/announcements")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(row["id"] == item["id"] for row in items)

    update_resp = client.put(
        f"/api/v1/admin/announcements/{item['id']}",
        json={"title": "updated announcement", "summary": "updated summary", "is_pinned": False},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["item"]
    assert updated["title"] == "updated announcement"
    assert updated["summary"] == "updated summary"
    assert updated["is_pinned"] is False

    delete_resp = client.delete(f"/api/v1/admin/announcements/{item['id']}")
    assert delete_resp.status_code == 200

    list_resp_after_delete = client.get("/api/v1/announcements")
    assert list_resp_after_delete.status_code == 200
    items_after_delete = list_resp_after_delete.json()["items"]
    assert all(row["id"] != item["id"] for row in items_after_delete)


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
        assert str(timeline_rows[0]["start"]).endswith("+08:00")
        assert str(timeline_rows[0]["end"]).endswith("+08:00")
        assert isinstance(timeline_rows[0]["start_time_sec"], str)

        error_resp = client.get(f"/api/v1/tasks/{task_uuid}/movement-timeline/errors", params={"cycle_no": 1})
        assert error_resp.status_code == 200
        error_rows = error_resp.json()
        assert error_rows
        assert str(error_rows[0]["time"]).endswith("+08:00")
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


def test_scope_catalog_and_timeline_filters_api(client: TestClient):
    seed = uuid4().hex[:8]
    task_uuid = f"scope_api_{seed}"
    chip_a1 = "40.M1_UL_HLAA1QY03261"
    chip_a2 = "40.M1_UR_HLAA2QY03263"
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
        db.add_all(
            [
                StepSummaryModel(
                    task_id=task.id,
                    cycle_no=31,
                    sub_step="Move slide from imager to chuck stage",
                    component="Workflow",
                    instrument_scope="Whole Instrument",
                    side_scope="A1",
                    side_group="A",
                    chip_name=chip_a1,
                    start_epoch_ms=1710000000000,
                    end_epoch_ms=1710000003000,
                    duration_ms=3000,
                    start_time_text="2024-03-09 16:00:00",
                    end_time_text="2024-03-09 16:00:03",
                    side_confidence=0.98,
                ),
                StepSummaryModel(
                    task_id=task.id,
                    cycle_no=31,
                    sub_step="Move slide from imager to chuck stage",
                    component="Workflow",
                    instrument_scope="Whole Instrument",
                    side_scope="A2",
                    side_group="A",
                    chip_name=chip_a2,
                    start_epoch_ms=1710000001000,
                    end_epoch_ms=1710000004700,
                    duration_ms=3700,
                    start_time_text="2024-03-09 16:00:01",
                    end_time_text="2024-03-09 16:00:04",
                    side_confidence=0.98,
                ),
            ]
        )
        db.add_all(
            [
                NormalizedEventModel(
                    task_id=task.id,
                    source_file=f"{task_uuid}.log",
                    parser_name="service_log",
                    level="INFO",
                    message="Move slide from imager to chuck stage start. A1",
                    raw_text="Move slide from imager to chuck stage start. A1",
                    cycle_no=31,
                    component="Workflow",
                    sub_step="Move slide from imager to chuck stage",
                    epoch_ms=1710000000000,
                    formatted_ms="2024-03-09 16:00:00.000",
                    instrument_scope="Whole Instrument",
                    side_scope="A1",
                    side_group="A",
                    chip_name=chip_a1,
                ),
                NormalizedEventModel(
                    task_id=task.id,
                    source_file=f"{task_uuid}.log",
                    parser_name="service_log",
                    level="INFO",
                    message="Move slide from imager to chuck stage start. A2",
                    raw_text="Move slide from imager to chuck stage start. A2",
                    cycle_no=31,
                    component="Workflow",
                    sub_step="Move slide from imager to chuck stage",
                    epoch_ms=1710000001000,
                    formatted_ms="2024-03-09 16:00:01.000",
                    instrument_scope="Whole Instrument",
                    side_scope="A2",
                    side_group="A",
                    chip_name=chip_a2,
                ),
            ]
        )
        db.commit()

        scope_resp = client.get(f"/api/v1/tasks/{task_uuid}/scope-catalog")
        assert scope_resp.status_code == 200
        scope_payload = scope_resp.json()
        assert {row["side_scope"] for row in scope_payload["sides"] if row["side_scope"]} == {"A1", "A2"}
        assert {row["chip_name"] for row in scope_payload["chips"] if row["chip_name"]} == {chip_a1, chip_a2}

        timeline_all = client.get(f"/api/v1/tasks/{task_uuid}/movement-timeline")
        assert timeline_all.status_code == 200
        assert {row["side_scope"] for row in timeline_all.json()} == {"A1", "A2"}

        timeline_a1 = client.get(f"/api/v1/tasks/{task_uuid}/movement-timeline", params={"side_scope": "A1", "track_granularity": "side_chip"})
        assert timeline_a1.status_code == 200
        assert {row["side_scope"] for row in timeline_a1.json()} == {"A1"}
        assert {row["chip_name"] for row in timeline_a1.json()} == {chip_a1}

        timeline_chip = client.get(f"/api/v1/tasks/{task_uuid}/movement-timeline", params={"chip_name": chip_a2, "track_granularity": "side_chip"})
        assert timeline_chip.status_code == 200
        assert {row["side_scope"] for row in timeline_chip.json()} == {"A2"}
        assert {row["chip_name"] for row in timeline_chip.json()} == {chip_a2}

        cycle_a2 = client.get(f"/api/v1/tasks/{task_uuid}/cycle-summary", params={"side_scope": "A2", "unit": "s"})
        assert cycle_a2.status_code == 200
        assert {row["side_scope"] for row in cycle_a2.json()} == {"A2"}
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
