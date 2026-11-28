"""Security: password hashing, JWT access/refresh tokens, API keys, RBAC."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.logging import get_logger

log = get_logger(__name__)

_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)

ROLE_RIGHTS: dict[str, set[str]] = {
    "admin": {
        "read",
        "write",
        "run_pipeline",
        "manage_sources",
        "manage_users",
        "manage_settings",
        "view_audit",
        "manage_keys",
        "query",
        "export",
    },
    "analyst": {"read", "write", "run_pipeline", "query", "export", "manage_alerts", "manage_views"},
    "viewer": {"read", "query", "export"},
}

ROLE_LEVEL = {"viewer": 1, "analyst": 2, "admin": 3}


# --------------------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Argon2id hash (the modern default - far stronger than PBKDF2/SHA-256)."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:  # pragma: no cover - corrupted hash in the database
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except Exception:  # pragma: no cover
        return False


def password_strength(password: str) -> tuple[bool, list[str]]:
    """Simple client/server side strength gate used by the Account screen."""
    problems: list[str] = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if not any(ch.isdigit() for ch in password):
        problems.append("at least one digit")
    if not any(ch.isupper() for ch in password):
        problems.append("at least one uppercase letter")
    if not any(ch.islower() for ch in password):
        problems.append("at least one lowercase letter")
    if not any(not ch.isalnum() for ch in password):
        problems.append("at least one symbol")
    return (not problems), problems


# --------------------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------------------
def create_access_token(
    subject: str | int,
    *,
    role: str = "viewer",
    email: str | None = None,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + dt.timedelta(minutes=expires_minutes or settings.access_token_expire_minutes),
        "type": "access",
        "iss": "product-intelligence-pipeline",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str | int, *, days: int | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + dt.timedelta(days=days or settings.refresh_token_expire_days),
        "type": "refresh",
        "iss": "product-intelligence-pipeline",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: str | None = "access") -> dict[str, Any]:
    """Decode and validate a JWT, raising :class:`AuthenticationError` on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer="product-intelligence-pipeline",
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("token has expired", details={"reason": "expired"}) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("invalid token", details={"reason": str(exc)[:120]}) from exc
    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError(f"expected a {expected_type} token", details={"type": payload.get("type")})
    return payload


# --------------------------------------------------------------------------------------
# API keys
# --------------------------------------------------------------------------------------
def generate_api_key() -> tuple[str, str, str]:
    """Return ``(plain_key, prefix, hashed_key)`` - the plain key is shown once."""
    plain = "pip_" + secrets.token_urlsafe(32)
    return plain, plain[:12], hash_api_key(plain)


def hash_api_key(plain: str) -> str:
    """SHA-256 with a server pepper; keys are high-entropy so this is safe."""
    return hashlib.sha256(f"{settings.secret_key}:{plain}".encode()).hexdigest()


def verify_api_key(plain: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_api_key(plain), hashed or "")


# --------------------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------------------
def has_right(role: str, right: str) -> bool:
    return right in ROLE_RIGHTS.get(role, set())


def require_right(role: str, right: str) -> None:
    if not has_right(role, right):
        raise PermissionDeniedError(
            f"role '{role}' is not allowed to perform '{right}'",
            details={"role": role, "required": right, "granted": sorted(ROLE_RIGHTS.get(role, set()))},
        )


def at_least(role: str, minimum: str) -> bool:
    return ROLE_LEVEL.get(role, 0) >= ROLE_LEVEL.get(minimum, 99)


__all__ = [
    "hash_password",
    "verify_password",
    "needs_rehash",
    "password_strength",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "generate_api_key",
    "hash_api_key",
    "verify_api_key",
    "has_right",
    "require_right",
    "at_least",
    "ROLE_RIGHTS",
    "ROLE_LEVEL",
]
