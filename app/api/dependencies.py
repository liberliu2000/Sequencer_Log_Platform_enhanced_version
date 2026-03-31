from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from app.db.session import SessionLocal
from app.services.auth_service import AuthService


PUBLIC_API_PREFIXES = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/register/request-code",
    "/api/v1/auth/register/resend-code",
    "/api/v1/auth/register/verify-email",
}


def extract_bearer_token(request: Request) -> str | None:
    auth_header = str(request.headers.get("Authorization") or "").strip()
    if not auth_header.lower().startswith("bearer "):
        token = str(request.query_params.get("access_token") or "").strip()
        return token or None
    token = auth_header[7:].strip()
    return token or None


def authenticate_request(request: Request) -> dict[str, Any] | None:
    token = extract_bearer_token(request)
    if not token:
        return None
    db = SessionLocal()
    try:
        user = AuthService(db).resolve_token(token)
        if not user:
            return None
        return AuthService(db).serialize_user(user)
    finally:
        db.close()


def get_current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期。")
    return user


def require_reviewer_user(request: Request) -> dict[str, Any]:
    user = get_current_user(request)
    if not (user.get("is_reviewer") or user.get("is_admin")):
        raise HTTPException(status_code=403, detail="需要 reviewer 或 admin 权限。")
    return user


def require_admin_user(request: Request) -> dict[str, Any]:
    user = get_current_user(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要 admin 权限。")
    return user
