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
    return TestClient(app)
