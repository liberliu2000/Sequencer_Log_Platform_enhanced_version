from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_ENABLED", "false")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_MODEL", "")

from app.main import app


@pytest.fixture()
def client():
    client = TestClient(app)
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"login_name": "Yanbo", "password": "MGItech_2026"},
    )
    if login_resp.status_code == 200:
        token = login_resp.json().get("token")
        if token:
            client.headers.update({"Authorization": f"Bearer {token}"})
    return client
