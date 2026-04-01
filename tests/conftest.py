from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_ENABLED", "false")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_MODEL", "")

from app.main import app
from app.db.session import SessionLocal
from app.models.db_models import UserModel
from app.services.auth_service import AuthService


@pytest.fixture()
def client():
    db = SessionLocal()
    try:
        AuthService(db).ensure_default_admin()
        user = db.query(UserModel).filter(UserModel.username == "Yanbo").one_or_none()
        if user is not None:
            user.failed_login_attempts = 0
            user.locked_until = None
            db.commit()
    finally:
        db.close()

    client = TestClient(app)
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"login_name": "Yanbo", "password": "MGItech2026"},
    )
    if login_resp.status_code == 200:
        token = login_resp.json().get("token")
        if token:
            client.headers.update({"Authorization": f"Bearer {token}"})
    return client
