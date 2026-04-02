from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000


def utcnow() -> datetime:
    return datetime.utcnow()


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"{PASSWORD_SCHEME}${iterations}${salt}${digest.hex()}"


def verify_password(password: str, encoded_password: str) -> bool:
    try:
        scheme, iteration_text, salt, expected_hash = encoded_password.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iteration_text),
        )
        return hmac.compare_digest(digest.hex(), expected_hash)
    except Exception:
        return False


def issue_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_verification_code(length: int = 6) -> str:
    length = max(4, min(length, 8))
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def hash_verification_code(user_id: int, code: str) -> str:
    return hashlib.sha256(f"{user_id}:{code}".encode("utf-8")).hexdigest()


def expires_after(minutes: int) -> datetime:
    return utcnow() + timedelta(minutes=minutes)
