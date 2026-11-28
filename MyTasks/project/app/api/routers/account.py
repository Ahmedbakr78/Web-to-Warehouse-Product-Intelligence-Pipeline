"""Account self-service for two-factor authentication and signed-in devices.

The enrolment flow is deliberately two-step:

1. `POST /2fa/setup` generates a secret and returns the `otpauth://` URI once. Nothing
   is enabled yet.
2. The user confirms with a real code via `POST /2fa/activate`. Only then is
   ``two_factor_enabled`` set and the recovery codes issued.

That way a user cannot lock themselves out by enrolling a mistyped secret, and the
secret is never stored in a state where it could be read back out of the database.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import Message
from app.core.errors import AuthenticationError, ValidationError
from app.core.logging import get_logger
from app.models.app_users import AppAuditLog

log = get_logger(__name__)

router = APIRouter(prefix="/account", tags=["account"])


# --------------------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------------------
class TwoFactorSetupResponse(BaseModel):
    """Returned once, at setup. The secret is never retrievable afterwards."""

    secret: str = Field(description="Base32 shared secret; show it as a QR code")
    otpauth_uri: str = Field(description="Scan this with an authenticator app")
    digits: int = 6
    period: int = 30


class TwoFactorActivateRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, description="A code from the app, to prove it works")
    secret: str = Field(min_length=16, max_length=64, description="The secret returned by setup")


class CodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class RecoveryCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class RevokeRequest(BaseModel):
    session_key: str | None = Field(default=None, description="Omit to revoke every other session")


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _audit(session, user, action: str, request: Request, **details: Any) -> None:
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action=action,
            entity_type="app_user",
            entity_id=str(user.user_id),
            ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip()[:64],
            user_agent=request.headers.get("user-agent", "")[:255],
            details=details or None,
        )
    )


def _require_password(user, password: str) -> None:
    """Both 2FA and mass-revocation require the password, not just the session."""
    from app.api.security import verify_password

    if not verify_password(password, user.hashed_password):
        raise AuthenticationError("password is incorrect")


# --------------------------------------------------------------------------------------
# Two-factor authentication
# --------------------------------------------------------------------------------------
@router.get("/2fa/status", summary="Is two-factor authentication enrolled?")
def two_factor_status(user: CurrentUser) -> dict[str, Any]:
    from app.core.db import session_scope
    from app.services.twofactor import guard_state

    with session_scope() as check:
        guard = guard_state(check, user)
    return {
        "enabled": bool(user.two_factor_enabled and user.totp_secret),
        "enrolled_at": user.two_factor_enrolled_at,
        "recovery_codes_remaining": len(user.recovery_codes or []),
        "attempts_remaining": max(0, 3 - guard.failures),
        "locked": guard.locked,
    }


@router.post(
    "/2fa/setup",
    response_model=TwoFactorSetupResponse,
    summary="Begin two-factor enrolment (returns the secret once)",
)
def two_factor_setup(request: Request, session: DbSession, user: CurrentUser) -> TwoFactorSetupResponse:
    """Generate a secret. 2FA is not active until `/2fa/activate` succeeds."""
    from app.services.twofactor import generate_secret, otpauth_uri

    if user.two_factor_enabled and user.totp_secret:
        raise ValidationError(
            "two-factor authentication is already enabled; disable it first",
            details={"hint": "POST /api/v1/account/2fa/disable"},
        )
    secret = generate_secret()
    # The secret is returned in this response and never written down, so an incomplete
    # enrolment leaves no usable secret behind.
    _audit(session, user, "auth.2fa_setup_started", request)
    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=otpauth_uri(secret, user.email),
    )


@router.post("/2fa/activate", summary="Confirm enrolment with a real code")
def two_factor_activate(
    payload: TwoFactorActivateRequest, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    """Verify a code against the offered secret, then enable 2FA and issue recovery codes."""
    from app.services.twofactor import (
        encrypt_secret,
        generate_recovery_codes,
        hash_recovery_code,
        verify_code,
    )

    if not verify_code(payload.secret, payload.code):
        _audit(session, user, "auth.2fa_activate_failed", request)
        raise AuthenticationError(
            "that code does not match; check the time on your device and try again",
            details={"hint": "authenticators need roughly the same clock as the server"},
        )

    recovery = generate_recovery_codes()
    user.totp_secret = encrypt_secret(payload.secret)
    user.two_factor_enabled = True
    user.two_factor_enrolled_at = dt.datetime.now(dt.timezone.utc)
    user.recovery_codes = [hash_recovery_code(code) for code in recovery]
    _audit(session, user, "auth.2fa_activated", request)
    log.info("2FA enabled for %s", user.email)
    return {
        "enabled": True,
        # Shown exactly once. These are the only copies.
        "recovery_codes": recovery,
        "message": "Store these recovery codes now. Each one works once.",
    }


@router.post("/2fa/disable", summary="Turn two-factor authentication off")
def two_factor_disable(
    payload: CodeRequest, request: Request, session: DbSession, user: CurrentUser
) -> Message:
    """Requires a current code, so a stolen access token alone cannot weaken the account."""
    from app.services.twofactor import decrypt_secret, verify_code

    if not user.two_factor_enabled:
        return Message(message="Two-factor authentication is not enabled")
    if not user.totp_secret:
        raise ValidationError("no two-factor secret is stored for this account")
    try:
        secret = decrypt_secret(user.totp_secret)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"stored secret is unusable: {exc}") from exc
    if not verify_code(secret, payload.code):
        _audit(session, user, "auth.2fa_disable_failed", request)
        raise AuthenticationError("incorrect verification code")

    user.totp_secret = None
    user.two_factor_enabled = False
    user.two_factor_enrolled_at = None
    user.recovery_codes = []
    _audit(session, user, "auth.2fa_disabled", request)
    return Message(message="Two-factor authentication disabled")


@router.post("/2fa/recovery-codes", summary="Issue a fresh set of recovery codes")
def two_factor_regenerate_codes(
    payload: CodeRequest, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    from app.services.twofactor import (
        decrypt_secret,
        generate_recovery_codes,
        hash_recovery_code,
        verify_code,
    )

    if not user.two_factor_enabled or not user.totp_secret:
        raise ValidationError("two-factor authentication is not enabled")
    if not verify_code(decrypt_secret(user.totp_secret), payload.code):
        raise AuthenticationError("incorrect verification code")
    codes = generate_recovery_codes()
    user.recovery_codes = [hash_recovery_code(code) for code in codes]
    _audit(session, user, "auth.2fa_recovery_regenerated", request)
    return {"recovery_codes": codes, "message": "These replace the previous set."}


@router.post("/2fa/verify", summary="Check a code without changing anything")
def two_factor_verify(payload: CodeRequest, user: CurrentUser) -> dict[str, Any]:
    """Lets the Account screen confirm the device is set up correctly."""
    from app.services.twofactor import decrypt_secret, verify_code

    if not user.two_factor_enabled or not user.totp_secret:
        raise ValidationError("two-factor authentication is not enabled")
    return {"valid": verify_code(decrypt_secret(user.totp_secret), payload.code)}


# --------------------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------------------
@router.get("/sessions", summary="Devices signed in to this account")
def sessions(session: DbSession, user: CurrentUser, current: str | None = None) -> dict[str, Any]:
    from app.services.sessions import list_sessions

    rows = list_sessions(session, user.user_id, current_key=current)
    for row in rows:
        row["device"] = _device_label(row["user_agent"])
    return {
        "total": len(rows),
        "active": sum(1 for row in rows if row["is_active"]),
        "sessions": rows,
    }


@router.post("/sessions/revoke", summary="Sign out one device, or every other device")
def revoke_sessions(
    payload: RevokeRequest, request: Request, session: DbSession, user: CurrentUser
) -> Message:
    from app.services.sessions import revoke_all, revoke_session

    if payload.session_key:
        if not revoke_session(session, payload.session_key, user.user_id, reason="revoked by user"):
            raise ValidationError("session not found")
        _audit(session, user, "auth.session_revoked", request, session_key=payload.session_key)
        return Message(message="That device has been signed out")

    count = revoke_all(session, user.user_id)
    _audit(session, user, "auth.sessions_revoked_all", request, count=count)
    return Message(message=f"Signed out of {count} other device(s)", detail={"revoked": count})


@router.post("/sessions/revoke-others", summary="Sign out every other device, keeping this one")
def revoke_others(
    current: Annotated[str, Field(min_length=8, max_length=64)],
    request: Request,
    session: DbSession,
    user: CurrentUser,
) -> Message:
    from app.services.sessions import revoke_all

    count = revoke_all(session, user.user_id, keep=current)
    _audit(session, user, "auth.sessions_revoked_all", request, count=count, kept=current)
    return Message(message=f"Signed out of {count} other device(s)", detail={"revoked": count})


@router.post("/sessions/verify-password", summary="Confirm the password for a sensitive action")
def verify_password(password: str, user: CurrentUser) -> Message:
    _require_password(user, password)
    return Message(message="Password confirmed")


def _device_label(user_agent: str | None) -> str:
    from app.services.sessions import describe_agent

    return describe_agent(user_agent)


__all__ = ["router"]
