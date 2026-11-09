"""Password hashing, JWT tokens, role checks and login throttling."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import jwt_secret, settings
from app.core.database import get_db
from app.models.access_control import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
_ITERATIONS = 310_000


def hash_password(password: str, iterations: int = _ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}"
        f"${base64.b64encode(digest).decode()}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt, digest = encoded.split("$")
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(iterations)
        )
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except Exception:
        return False


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        },
        jwt_secret(),
        algorithm="HS256",
    )


def current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
        user = db.scalar(select(User).where(User.id == int(payload["sub"])))
    except Exception as error:
        raise HTTPException(401, "Invalid or expired token.") from error
    if not user or not user.is_active or user.account_status != "ACTIVE":
        raise HTTPException(401, "Inactive, suspended or unverified account.")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Your role is not permitted to do this.")
        return user

    return dependency


def is_verified_auditor(db: Session, user: User) -> bool:
    """Auditors are verified once an administrator has activated their account."""
    return user.role == "AUDITOR" and user.account_status == "ACTIVE"


def require_verified_auditor(
    user: User = Depends(require_roles("AUDITOR")), db: Session = Depends(get_db)
) -> User:
    if not is_verified_auditor(db, user):
        raise HTTPException(
            403, "Auditor verification by an administrator is required first."
        )
    return user


# ---- login throttling (in-memory, per email + client IP) -----------------
_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()
_WINDOW, _MAX_FAILS = 300.0, 8


def _key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}|{email.lower()}"


def check_login_allowed(request: Request, email: str) -> None:
    key, now = _key(request, email), time.time()
    with _lock:
        recent = [t for t in _attempts.get(key, []) if now - t < _WINDOW]
        _attempts[key] = recent
        if len(recent) >= _MAX_FAILS:
            raise HTTPException(
                429, "Too many failed sign-in attempts. Try again in a few minutes."
            )


def record_login_failure(request: Request, email: str) -> None:
    with _lock:
        _attempts.setdefault(_key(request, email), []).append(time.time())


def clear_login_failures(request: Request, email: str) -> None:
    with _lock:
        _attempts.pop(_key(request, email), None)
