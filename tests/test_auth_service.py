from __future__ import annotations

import sqlite3
from datetime import timedelta

from sqlalchemy.exc import OperationalError

from app.core.security import issue_session_token, utcnow
from app.models.db_models import UserModel, UserSessionModel
from app.services.auth_service import AuthService, USER_STATUS_APPROVED


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row
        self.rollback_called = False

    def execute(self, _stmt):
        return _FakeResult(self._row)

    def commit(self):
        raise OperationalError("UPDATE user_sessions ...", {}, sqlite3.OperationalError("database is locked"))

    def rollback(self):
        self.rollback_called = True


def test_resolve_token_tolerates_locked_last_seen_update():
    now = utcnow()
    user = UserModel(username="locked-user", email="locked@example.com", password_hash="x", status=USER_STATUS_APPROVED)
    session = UserSessionModel(
        user_id=1,
        token_hash="unused",
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=5),
        created_at=now,
    )
    fake_db = _FakeSession((session, user))

    service = AuthService(fake_db)  # type: ignore[arg-type]
    resolved = service.resolve_token(issue_session_token())

    assert resolved is user
    assert fake_db.rollback_called is True
