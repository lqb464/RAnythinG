"""JWT auth + external service token for RAnythinG v1.1."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import SessionLocal, UserRow

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-dev-only-not-for-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_MINUTES = int(os.getenv("JWT_ACCESS_MINUTES", "60"))
JWT_REFRESH_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "14"))
# When set, /api/external/* requires this Bearer token (any service client).
EXTERNAL_API_TOKEN = (os.getenv("EXTERNAL_API_TOKEN") or os.getenv("RANYTHING_API_TOKEN") or "").strip()
# When true (default if JWT_SECRET is set to non-placeholder), UI notebook APIs require JWT.
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "true").lower() in ("1", "true", "yes")

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": _now() + timedelta(minutes=JWT_ACCESS_MINUTES),
        "iat": _now(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "refresh",
        "exp": _now() + timedelta(days=JWT_REFRESH_DAYS),
        "iat": _now(),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected {expected_type} token")
    return payload


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass
class AuthUser:
    id: str
    email: str


def create_user(email: str, password: str) -> dict:
    email_n = _normalize_email(email)
    if "@" not in email_n or "." not in email_n.split("@")[-1]:
        raise ValueError("Invalid email")
    if len(password) < 6:
        raise ValueError("Password too short")

    # Filesystem mode without Postgres: store users in a local JSON sidecar via DB if available.
    if not os.getenv("DATABASE_URL"):
        from . import user_store

        return user_store.create_user(email_n, hash_password(password))

    user_id = str(uuid.uuid4())
    with SessionLocal() as db:
        if db.query(UserRow).filter(UserRow.email == email_n).first():
            raise ValueError("Email already registered")
        row = UserRow(
            id=user_id,
            email=email_n,
            password_hash=hash_password(password),
            created_at=datetime.now(),
        )
        db.add(row)
        db.commit()
        return {"id": user_id, "email": email_n}


def get_user_by_email(email: str) -> Optional[dict]:
    email_n = _normalize_email(email)
    if not os.getenv("DATABASE_URL"):
        from . import user_store

        return user_store.get_user_by_email(email_n)
    with SessionLocal() as db:
        row = db.query(UserRow).filter(UserRow.email == email_n).first()
        if not row:
            return None
        return {"id": row.id, "email": row.email, "password_hash": row.password_hash}


def get_user_by_id(user_id: str) -> Optional[dict]:
    if not os.getenv("DATABASE_URL"):
        from . import user_store

        return user_store.get_user_by_id(user_id)
    with SessionLocal() as db:
        row = db.get(UserRow, user_id)
        if not row:
            return None
        return {"id": row.id, "email": row.email, "password_hash": row.password_hash}


async def get_optional_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[AuthUser]:
    if not creds or not creds.credentials:
        return None
    try:
        payload = decode_token(creds.credentials, expected_type="access")
        uid = str(payload.get("sub") or "")
        email = str(payload.get("email") or "")
        if not uid:
            return None
        return AuthUser(id=uid, email=email)
    except Exception:
        return None


async def require_user(user: Optional[AuthUser] = Depends(get_optional_user)) -> AuthUser:
    required = os.getenv("AUTH_REQUIRED", "true").lower() in ("1", "true", "yes")
    if not required:
        return user or AuthUser(id="anonymous", email="anonymous@local")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_external_token(
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None, alias="X-API-Token"),
) -> None:
    """Protect /api/external/* when EXTERNAL_API_TOKEN is configured."""
    expected = (os.getenv("EXTERNAL_API_TOKEN") or os.getenv("RANYTHING_API_TOKEN") or EXTERNAL_API_TOKEN or "").strip()
    if not expected:
        return  # open mode for local solo demos without token
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_api_token:
        provided = x_api_token.strip()
    if not provided or not constant_time_eq(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing external API token")


def fingerprint_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
