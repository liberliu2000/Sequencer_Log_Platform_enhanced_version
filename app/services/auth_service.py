from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password,
    hash_session_token,
    hash_verification_code,
    issue_session_token,
    issue_verification_code,
    utcnow,
    verify_password,
)
from app.core.settings import get_settings
from app.models.db_models import RegistrationChallengeModel, UserModel, UserSessionModel
from app.services.email_service import EmailDeliveryError, EmailService


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
        self.email_service = EmailService()

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

    def find_registration_challenge(self, login_name: str) -> RegistrationChallengeModel | None:
        normalized = str(login_name or "").strip().lower()
        if not normalized:
            return None
        stmt = select(RegistrationChallengeModel).where(
            or_(
                func.lower(RegistrationChallengeModel.username) == normalized,
                func.lower(RegistrationChallengeModel.email) == normalized,
            )
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

        challenge = self.find_registration_challenge(username) or self.find_registration_challenge(email)
        now = utcnow()
        if challenge is None:
            challenge = RegistrationChallengeModel(
                username=username,
                email=email,
                password_hash=hash_password(password),
                registration_note=str(registration_note or "").strip() or None,
                code_hash="pending",
                expires_at=now,
                request_ip=request_ip,
                resend_count=0,
                attempt_count=0,
                created_at=now,
                updated_at=now,
            )
            self.db.add(challenge)
            self.db.flush()
        else:
            if challenge.consumed_at is not None:
                challenge.consumed_at = None
            challenge.username = username
            challenge.email = email
            challenge.password_hash = hash_password(password)
            challenge.registration_note = str(registration_note or "").strip() or None
            challenge.request_ip = request_ip
            challenge.updated_at = now

        self._assert_registration_resend_allowed(challenge)
        code = issue_verification_code()
        challenge.code_hash = hash_verification_code(challenge.id, code)
        challenge.expires_at = now + timedelta(minutes=self.settings.auth_verification_code_minutes)
        challenge.last_sent_at = now
        challenge.resend_count = int(challenge.resend_count or 0) + 1
        challenge.attempt_count = 0
        challenge.verified_at = None
        challenge.verification_token_hash = None
        challenge.verification_token_expires_at = None
        try:
            self.email_service.send_verification_code(
                recipient=challenge.email,
                username=challenge.username,
                code=code,
                expires_minutes=self.settings.auth_verification_code_minutes,
            )
        except EmailDeliveryError:
            self.db.rollback()
            raise
        self.db.commit()
        return {
            "status": "verification_sent",
            "login_name": challenge.username,
            "email": challenge.email,
            "verification_expires_at": challenge.expires_at.isoformat() if challenge.expires_at else None,
        }

    def resend_verification_code(self, *, login_name: str, request_ip: str | None = None) -> dict[str, Any]:
        challenge = self.find_registration_challenge(login_name)
        if not challenge or challenge.consumed_at is not None:
            raise AuthError("注册验证记录不存在。")
        if challenge.verified_at is not None:
            raise AuthError("邮箱已验证，请继续提交注册申请。")

        self._assert_registration_resend_allowed(challenge)
        now = utcnow()
        code = issue_verification_code()
        challenge.code_hash = hash_verification_code(challenge.id, code)
        challenge.expires_at = now + timedelta(minutes=self.settings.auth_verification_code_minutes)
        challenge.last_sent_at = now
        challenge.resend_count = int(challenge.resend_count or 0) + 1
        challenge.request_ip = request_ip
        challenge.updated_at = now
        self.email_service.send_verification_code(
            recipient=challenge.email,
            username=challenge.username,
            code=code,
            expires_minutes=self.settings.auth_verification_code_minutes,
        )
        self.db.commit()
        return {
            "status": "ok",
            "verification_expires_at": challenge.expires_at.isoformat() if challenge.expires_at else None,
        }

    def verify_email_code(self, *, login_name: str, code: str) -> dict[str, Any]:
        challenge = self.find_registration_challenge(login_name)
        if not challenge or challenge.consumed_at is not None:
            raise AuthError("验证码不存在，请重新发送。")
        if challenge.expires_at is None or challenge.expires_at < utcnow():
            raise AuthError("验证码已过期，请重新发送。")

        challenge.attempt_count = int(challenge.attempt_count or 0) + 1
        expected_hash = hash_verification_code(challenge.id, str(code or "").strip())
        if challenge.code_hash != expected_hash:
            self.db.commit()
            raise AuthError("验证码错误。")

        now = utcnow()
        verification_token = issue_session_token()
        challenge.verified_at = now
        challenge.verification_token_hash = hash_session_token(verification_token)
        challenge.verification_token_expires_at = now + timedelta(minutes=30)
        challenge.updated_at = now
        self.db.commit()
        return {
            "status": "ok",
            "verification_token": verification_token,
            "next_status": "verified_can_submit",
            "verified_email": challenge.email,
            "verified_username": challenge.username,
        }

    def register_user(self, *, verification_token: str, request_ip: str | None = None) -> dict[str, Any]:
        token_hash = hash_session_token(str(verification_token or "").strip())
        if not token_hash:
            raise AuthError("缺少邮箱验证成功后的注册凭证。")
        challenge = self.db.scalar(
            select(RegistrationChallengeModel).where(RegistrationChallengeModel.verification_token_hash == token_hash)
        )
        if not challenge:
            raise AuthError("注册凭证无效。")
        now = utcnow()
        if challenge.verified_at is None or challenge.verification_token_expires_at is None or challenge.verification_token_expires_at < now:
            raise AuthError("注册凭证已过期，请重新验证邮箱。")
        if challenge.consumed_at is not None:
            raise AuthError("该注册申请已提交，请勿重复提交。")
        if self.find_user(challenge.username):
            raise AuthError("用户名已存在。")
        existing_email = self.db.scalar(select(UserModel).where(func.lower(UserModel.email) == challenge.email.lower()))
        if existing_email:
            raise AuthError("邮箱已存在。")

        user = UserModel(
            username=challenge.username,
            email=challenge.email,
            password_hash=challenge.password_hash,
            status=USER_STATUS_PENDING_ADMIN_APPROVAL,
            email_verified=True,
            email_verified_at=challenge.verified_at,
            registration_note=challenge.registration_note,
            approval_requested_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        challenge.consumed_at = now
        challenge.code_hash = ""
        challenge.verification_token_hash = None
        challenge.verification_token_expires_at = None
        challenge.request_ip = request_ip
        challenge.updated_at = now
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
        self.db.commit()
        return user

    def logout(self, *, token: str) -> None:
        token_hash = hash_session_token(str(token or "").strip())
        session = self.db.scalar(select(UserSessionModel).where(UserSessionModel.token_hash == token_hash))
        if session and session.revoked_at is None:
            session.revoked_at = utcnow()
            self.db.commit()

    def change_password(self, *, user: UserModel, current_password: str, new_password: str) -> dict[str, Any]:
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

    def list_users(self) -> list[dict[str, Any]]:
        rows = list(self.db.scalars(select(UserModel).order_by(UserModel.created_at.desc(), UserModel.id.desc())))
        return [self.serialize_user(row) for row in rows]

    def update_user_status(self, *, user_id: int, action: str, actor: str) -> dict[str, Any]:
        user = self.get_user_by_id(user_id)
        now = utcnow()
        if action == "approve":
            if not user.email_verified:
                raise AuthError("用户尚未完成邮箱验证。")
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
            if not user.email_verified:
                raise AuthError("用户尚未完成邮箱验证。")
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

    def update_user_roles(self, *, user_id: int, is_reviewer: bool, is_admin: bool, actor: str) -> dict[str, Any]:
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

    def _assert_login_allowed(self, user: UserModel) -> None:
        if user.locked_until and user.locked_until > utcnow():
            raise AuthError(f"登录失败次数过多，请在 {user.locked_until.isoformat()} 后重试。")
        if user.status == USER_STATUS_PENDING_VERIFICATION:
            raise AuthError("账号尚未完成邮箱验证。")
        if user.status == USER_STATUS_PENDING_ADMIN_APPROVAL:
            raise AuthError("账号已完成邮箱验证，等待管理员审核。")
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
            USER_STATUS_PENDING_VERIFICATION: "账号尚未完成邮箱验证。",
            USER_STATUS_PENDING_ADMIN_APPROVAL: "账号已完成邮箱验证，等待管理员审核。",
            USER_STATUS_REJECTED: "注册申请已被拒绝。",
            USER_STATUS_DISABLED: "账号已被停用。",
        }
        return mapping.get(status, "账号当前不可登录。")

    def _assert_registration_resend_allowed(self, challenge: RegistrationChallengeModel) -> None:
        now = utcnow()
        if int(challenge.resend_count or 0) > 0 and challenge.last_sent_at and (now - challenge.last_sent_at).total_seconds() < self.settings.auth_verification_resend_seconds:
            raise AuthError("验证码发送过于频繁，请稍后再试。")
        if int(challenge.resend_count or 0) >= self.settings.auth_verification_max_daily_sends:
            raise AuthError("今日验证码发送次数已达上限。")
