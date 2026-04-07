from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import extract_bearer_token, get_current_user, require_admin_user
from app.db.session import get_db
from app.services.auth_service import AuthError, AuthService


router = APIRouter()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/auth/register")
def register(payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        item = AuthService(db).register_user(
            username=str(payload.get("username") or ""),
            password=str(payload.get("password") or ""),
            email=str(payload.get("email") or ""),
            registration_note=payload.get("registration_note"),
            request_ip=_client_ip(request),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item


@router.post("/auth/register/request-code")
def request_register_code(payload: dict, request: Request, db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail="邮箱验证码功能已下线，请直接提交注册申请并等待管理员审核。")


@router.post("/auth/register/resend-code")
def resend_verification_code(payload: dict, request: Request, db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail="邮箱验证码功能已下线，请直接提交注册申请并等待管理员审核。")


@router.post("/auth/register/verify-email")
def verify_email_code(payload: dict, db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail="邮箱验证码功能已下线，请直接提交注册申请并等待管理员审核。")


@router.post("/auth/login")
def login(payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        item = AuthService(db).login(
            login_name=str(payload.get("login_name") or ""),
            password=str(payload.get("password") or ""),
            ip_address=_client_ip(request),
            user_agent=str(request.headers.get("User-Agent") or "")[:512] or None,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return item


@router.post("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    token = extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=400, detail="缺少 token")
    AuthService(db).logout(token=token)
    return {"status": "ok", "user": current_user}


@router.get("/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/auth/change-password")
def change_password(payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    service = AuthService(db)
    try:
        user = service.get_user_by_id(int(current_user["id"]))
        item = service.change_password(
            user=user,
            current_password=str(payload.get("current_password") or ""),
            new_password=str(payload.get("new_password") or ""),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "user": item}


@router.post("/auth/reset-password")
def reset_password(payload: dict, db: Session = Depends(get_db)):
    service = AuthService(db)
    try:
        item = service.reset_password_by_identity(
            username=str(payload.get("username") or ""),
            email=str(payload.get("email") or ""),
            new_password=str(payload.get("new_password") or ""),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "user": item}


@router.get("/admin/users")
def list_users(db: Session = Depends(get_db), current_user: dict = Depends(require_admin_user)):
    items = AuthService(db).list_users()
    return {"items": items, "total": len(items), "current_user": current_user}


@router.post("/admin/users/{user_id}/status")
def update_user_status(user_id: int, payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(require_admin_user)):
    try:
        item = AuthService(db).update_user_status(
            user_id=user_id,
            action=str(payload.get("action") or ""),
            actor=str(current_user.get("username") or "admin"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "item": item}


@router.post("/admin/users/{user_id}/roles")
def update_user_roles(user_id: int, payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(require_admin_user)):
    try:
        item = AuthService(db).update_user_roles(
            user_id=user_id,
            is_reviewer=bool(payload.get("is_reviewer")),
            is_admin=bool(payload.get("is_admin")),
            actor=str(current_user.get("username") or "admin"),
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "item": item}
