from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password,
    hash_session_token,
    issue_session_token,
    utcnow,
    verify_password,
)
from app.core.settings import get_settings
from app.models.db_models import UserModel, UserSessionModel


USER_STATUS_PENDING_VERIFICATION = "pending_verification"
USER_STATUS_PENDING_ADMIN_APPROVAL = "pending_admin_approval"
USER_STATUS_APPROVED = "approved"
USER_STATUS_REJECTED = "rejected"
USER_STATUS_DISABLED = "disabled"

ROLE_ADMIN = "admin"
ROLE_REVIEWER = "reviewer"
ROLE_SUBMITTER = "submitter"


class AuthError(ValueError):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def serialize_user(self, user: UserModel) -> dict[str, Any]:
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "status": user.status,
            "roles": self.roles_for_user(user),
            "is_admin": user.is_admin,
            "is_reviewer": user.is_reviewer,
            "email_verified": user.email_verified,
            "force_password_change": user.force_password_change,
            "approval_requested_at": user.approval_requested_at.isoformat() if user.approval_requested_at else None,
            "approved_at": user.approved_at.isoformat() if user.approved_at else None,
            "rejected_at": user.rejected_at.isoformat() if user.rejected_at else None,
            "disabled_at": user.disabled_at.isoformat() if user.disabled_at else None,
            "approved_by": user.approved_by,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "registration_note": user.registration_note,
        }

    def roles_for_user(self, user: UserModel) -> list[str]:
        roles = [ROLE_SUBMITTER]
        if user.is_reviewer:
            roles.append(ROLE_REVIEWER)
        if user.is_admin:
            roles.append(ROLE_ADMIN)
        return roles

    def find_user(self, login_name: str) -> UserModel | None:
        normalized = str(login_name or "").strip().lower()
        if not normalized:
            return None
        stmt = select(UserModel).where(
            or_(
                func.lower(UserModel.username) == normalized,
                func.lower(UserModel.email) == normalized,
            )
        )
        return self.db.scalar(stmt)

    def find_user_by_username_and_email(self, *, username: str, email: str) -> UserModel | None:
        normalized_username = str(username or "").strip().lower()
        normalized_email = str(email or "").strip().lower()
        if not normalized_username or not normalized_email:
            return None
        stmt = select(UserModel).where(
            func.lower(UserModel.username) == normalized_username,
            func.lower(UserModel.email) == normalized_email,
        )
        return self.db.scalar(stmt)

    def get_user_by_id(self, user_id: int) -> UserModel:
        user = self.db.get(UserModel, user_id)
        if not user:
            raise AuthError("用户不存在。")
        return user

    def start_registration(
        self,
        *,
        username: str,
        password: str,
        email: str,
        registration_note: str | None = None,
        request_ip: str | None = None,
    ) -> dict[str, Any]:
        return self.register_user(
            username=username,
            password=password,
            email=email,
            registration_note=registration_note,
            request_ip=request_ip,
        )

    def register_user(
        self,
        *,
        username: str,
        password: str,
        email: str,
        registration_note: str | None = None,
        request_ip: str | None = None,
    ) -> dict[str, Any]:
        username = str(username or "").strip()
        email = str(email or "").strip().lower()
        password = str(password or "")
        if len(username) < 3:
            raise AuthError("用户名至少需要 3 个字符。")
        if "@" not in email or "." not in email.split("@")[-1]:
            raise AuthError("邮箱格式无效。")
        if len(password) < 8:
            raise AuthError("密码至少需要 8 个字符。")
        if self.find_user(username):
            raise AuthError("用户名已存在。")
        existing_email = self.db.scalar(select(UserModel).where(func.lower(UserModel.email) == email))
        if existing_email:
            raise AuthError("邮箱已存在。")

        now = utcnow()
        user = UserModel(
            username=username,
            email=email,
            password_hash=hash_password(password),
            status=USER_STATUS_PENDING_ADMIN_APPROVAL,
            email_verified=False,
            email_verified_at=None,
            registration_note=str(registration_note or "").strip() or None,
            approval_requested_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return {
            "user": self.serialize_user(user),
            "next_status": USER_STATUS_PENDING_ADMIN_APPROVAL,
        }

    def login(self, *, login_name: str, password: str, ip_address: str | None = None, user_agent: str | None = None) -> dict[str, Any]:
        user = self.find_user(login_name)
        if not user:
            raise AuthError("用户名或密码错误。")
        self._assert_login_allowed(user)
        if not verify_password(password, user.password_hash):
            self._mark_failed_login(user)
            raise AuthError("用户名或密码错误。")
        if user.status != USER_STATUS_APPROVED:
            raise AuthError(self._status_message(user.status))

        now = utcnow()
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.updated_at = now

        plain_token = issue_session_token()
        session = UserSessionModel(
            user_id=user.id,
            token_hash=hash_session_token(plain_token),
            expires_at=now + timedelta(hours=self.settings.auth_session_hours),
            last_seen_at=now,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(user)
        return {
            "token": plain_token,
            "expires_at": session.expires_at.isoformat(),
            "user": self.serialize_user(user),
        }

    def resolve_token(self, token: str) -> UserModel | None:
        token_hash = hash_session_token(str(token or "").strip())
        if not token_hash:
            return None
        stmt = (
            select(UserSessionModel, UserModel)
            .join(UserModel, UserModel.id == UserSessionModel.user_id)
            .where(UserSessionModel.token_hash == token_hash)
        )
        row = self.db.execute(stmt).first()
        if not row:
            return None
        session, user = row
        now = utcnow()
        if session.revoked_at is not None or session.expires_at < now:
            return None
        if user.status != USER_STATUS_APPROVED:
            return None
        session.last_seen_at = now
        try:
            self.db.commit()
        except OperationalError:
            # If SQLite is briefly write-locked, keep authentication successful
            # and skip this best-effort metadata update.
            self.db.rollback()
        return user

    def logout(self, *, token: str) -> None:
        token_hash = hash_session_token(str(token or "").strip())
        session = self.db.scalar(select(UserSessionModel).where(UserSessionModel.token_hash == token_hash))
        if session and session.revoked_at is None:
            session.revoked_at = utcnow()
            self.db.commit()

    def change_password(self, *, user: UserModel, current_password: str, new_password: str) -> dict[str, Any]:
        self._validate_new_password(new_password)
        if len(str(new_password or "")) < 8:
            raise AuthError("新密码至少需要 8 个字符。")
        if not verify_password(current_password, user.password_hash):
            raise AuthError("当前密码错误。")
        user.password_hash = hash_password(new_password)
        user.force_password_change = False
        user.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(user)
        return self.serialize_user(user)

    def reset_password_by_identity(self, *, username: str, email: str, new_password: str) -> dict[str, Any]:
        self._validate_new_password(new_password)
        user = self.find_user_by_username_and_email(username=username, email=email)
        if not user:
            raise AuthError("用户名和邮箱不匹配。")
        user.password_hash = hash_password(new_password)
        user.force_password_change = False
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = utcnow()
        self._revoke_user_sessions(user.id)
        self.db.commit()
        self.db.refresh(user)
        return self.serialize_user(user)

    def list_users(self) -> list[dict[str, Any]]:
        rows = list(self.db.scalars(select(UserModel).order_by(UserModel.created_at.desc(), UserModel.id.desc())))
        return [self.serialize_user(row) for row in rows]

    def update_user_status(self, *, user_id: int, action: str, actor: str) -> dict[str, Any]:
        user = self.get_user_by_id(user_id)
        now = utcnow()
        if action == "approve":
            user.status = USER_STATUS_APPROVED
            user.approved_at = now
            user.rejected_at = None
            user.disabled_at = None
            user.approved_by = actor
        elif action == "reject":
            if user.status == USER_STATUS_APPROVED:
                raise AuthError("已激活用户请使用 disable。")
            user.status = USER_STATUS_REJECTED
            user.rejected_at = now
            user.approved_by = actor
        elif action == "disable":
            user.status = USER_STATUS_DISABLED
            user.disabled_at = now
            user.approved_by = actor
        elif action == "enable":
            user.status = USER_STATUS_APPROVED
            user.disabled_at = None
            user.approved_at = user.approved_at or now
            user.approved_by = actor
        else:
            raise AuthError("不支持的用户状态操作。")
        user.updated_at = now
        self.db.commit()
        self.db.refresh(user)
        return self.serialize_user(user)

    def update_user_roles(
        self,
        *,
        user_id: int,
        is_reviewer: bool,
        is_admin: bool,
        actor: str,
    ) -> dict[str, Any]:
        user = self.get_user_by_id(user_id)
        user.is_reviewer = bool(is_reviewer or is_admin)
        user.is_admin = bool(is_admin)
        user.approved_by = actor
        user.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(user)
        return self.serialize_user(user)

    def ensure_default_admin(self) -> dict[str, Any]:
        username = self.settings.auth_default_admin_username
        password = self.settings.auth_default_admin_password
        existing = self.find_user(username)
        if existing:
            changed = False
            if existing.force_password_change and not verify_password(password, existing.password_hash):
                existing.password_hash = hash_password(password)
                changed = True
            if existing.status != USER_STATUS_APPROVED:
                existing.status = USER_STATUS_APPROVED
                changed = True
            if not existing.email_verified:
                existing.email_verified = True
                existing.email_verified_at = existing.email_verified_at or utcnow()
                changed = True
            if not existing.is_admin:
                existing.is_admin = True
                changed = True
            if not existing.is_reviewer:
                existing.is_reviewer = True
                changed = True
            if existing.force_password_change is False:
                existing.force_password_change = True
                changed = True
            if changed:
                existing.updated_at = utcnow()
                self.db.commit()
                self.db.refresh(existing)
            return self.serialize_user(existing)

        now = utcnow()
        admin = UserModel(
            username=username,
            email=f"{username.lower()}@local.admin",
            password_hash=hash_password(password),
            status=USER_STATUS_APPROVED,
            is_reviewer=True,
            is_admin=True,
            email_verified=True,
            email_verified_at=now,
            force_password_change=True,
            approval_requested_at=now,
            approved_at=now,
            approved_by="system",
            created_at=now,
            updated_at=now,
        )
        self.db.add(admin)
        self.db.commit()
        self.db.refresh(admin)
        return self.serialize_user(admin)

    def _validate_new_password(self, new_password: str) -> None:
        if len(str(new_password or "")) < 8:
            raise AuthError("新密码至少需要 8 个字符。")

    def _revoke_user_sessions(self, user_id: int) -> None:
        now = utcnow()
        sessions = list(self.db.scalars(select(UserSessionModel).where(UserSessionModel.user_id == user_id)))
        for session in sessions:
            session.revoked_at = now

    def _assert_login_allowed(self, user: UserModel) -> None:
        if user.locked_until and user.locked_until > utcnow():
            raise AuthError(f"登录失败次数过多，请在 {user.locked_until.isoformat()} 后重试。")
        if user.status == USER_STATUS_PENDING_VERIFICATION:
            raise AuthError("账号正在等待管理员审核。")
        if user.status == USER_STATUS_PENDING_ADMIN_APPROVAL:
            raise AuthError("账号正在等待管理员审核。")
        if user.status == USER_STATUS_REJECTED:
            raise AuthError("注册申请已被拒绝。")
        if user.status == USER_STATUS_DISABLED:
            raise AuthError("账号已被停用。")

    def _mark_failed_login(self, user: UserModel) -> None:
        now = utcnow()
        user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= self.settings.auth_max_failed_logins:
            user.locked_until = now + timedelta(minutes=self.settings.auth_lock_minutes)
            user.failed_login_attempts = 0
        user.updated_at = now
        self.db.commit()

    def _status_message(self, status: str) -> str:
        mapping = {
            USER_STATUS_PENDING_VERIFICATION: "账号正在等待管理员审核。",
            USER_STATUS_PENDING_ADMIN_APPROVAL: "账号正在等待管理员审核。",
            USER_STATUS_REJECTED: "注册申请已被拒绝。",
            USER_STATUS_DISABLED: "账号已被停用。",
        }
        return mapping.get(status, "账号当前不可登录。")
