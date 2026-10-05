"""Authentication endpoints: login, refresh, logout, change password, session info."""

from __future__ import annotations

import datetime as dt
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, client_ip
from app.api.schemas import (
    LoginRequest,
    Message,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
    UserRead,
)
from app.api.security import (
    ROLE_RIGHTS,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.models.app_users import AppAuditLog, AppNotification, AppSession, AppUser

log = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


def _to_read(user: AppUser) -> UserRead:
    data = UserRead.model_validate(user)
    data.permissions = sorted(ROLE_RIGHTS.get(user.role, set()))
    return data


def _tokens(user: AppUser, request: Request | None = None, session: Session | None = None) -> TokenResponse:
    """Mint an access/refresh pair and, when possible, record the browser session."""
    access = create_access_token(user.user_id, role=user.role, email=user.email)
    refresh = create_refresh_token(user.user_id)

    session_key: str | None = None
    if session is not None:
        try:
            row = _open_session(user, refresh, request)
            session.add(row)
            session.flush()
            session_key = row.session_key
        except Exception as exc:  # noqa: BLE001 - a session record is never worth a failed login
            log.warning("could not record the login session for %s: %s", user.email, exc)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        role=user.role,
        session_key=session_key,
        user=_to_read(user),
    )


def _open_session(user: AppUser, refresh_token: str, request: Request | None) -> AppSession:
    """Create the row that lets a user see and revoke this browser session."""
    import secrets

    from app.services.sessions import hash_refresh_token

    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=settings.refresh_token_expire_days)
    return AppSession(
        user_id=user.user_id,
        session_key=secrets.token_urlsafe(18),
        refresh_hash=hash_refresh_token(refresh_token),
        ip_address=client_ip(request)[:64] if request else None,
        user_agent=(request.headers.get("user-agent", "")[:512] if request else None),
        expires_at=expires,
    )


def _audit(
    session: Session,
    user: AppUser | None,
    action: str,
    request: Request,
    status: str = "success",
    durable: bool = False,
    **details: Any,
) -> None:
    """Record a security event.

    `durable=True` commits immediately. Failed-login evidence has to survive the
    exception that is about to be raised: the request dependency rolls the transaction
    back on error, which would otherwise discard the very record the brute-force
    counters are built from - so the lockout would never engage.
    """
    session.add(
        AppAuditLog(
            user_id=user.user_id if user else None,
            user_email=user.email if user else None,
            action=action,
            status=status,
            ip_address=client_ip(request)[:64],
            user_agent=request.headers.get("user-agent", "")[:255],
            details=details or None,
        )
    )
    if durable:
        session.commit()


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for tokens")
def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    from app.services import twofactor

    email = payload.email.lower().strip()
    user = session.execute(sa.select(AppUser).where(AppUser.email == email)).scalars().first()

    if user is None:
        _audit(session, None, "auth.login", request, status="failure", durable=True, email=email)
        raise AuthenticationError("invalid email or password")

    now = dt.datetime.now(dt.timezone.utc)
    if user.locked_until and user.locked_until.replace(tzinfo=dt.timezone.utc) > now:
        raise AuthenticationError(
            "account temporarily locked after repeated failed logins",
            details={"locked_until": user.locked_until.isoformat()},
        )

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + dt.timedelta(minutes=LOCK_MINUTES)
            user.failed_login_count = 0
        _audit(session, user, "auth.login", request, status="failure", durable=True)
        raise AuthenticationError("invalid email or password")

    # Second factor, when the account has one enrolled.
    if user.two_factor_enabled and user.totp_secret:
        guard = twofactor.guard_state(session, user)
        # The lockout exists to slow brute force, not to strand the account owner.
        # A recovery code is proof of possession in its own right, so it is accepted
        # even while the TOTP window is locked; otherwise mistyping three codes leaves
        # no way back in until the window rolls over.
        if guard.locked and not payload.recovery_code:
            _audit(session, user, "auth.login", request, status="failure", durable=True, reason="2fa_locked")
            raise AuthenticationError(
                "too many incorrect verification codes; try again shortly",
                details={"locked": True, "recovery_code_accepted": True},
            )
        if not _check_second_factor(user, payload, session, request):
            twofactor.record_failure(session, user, "invalid code")
            _audit(session, user, "auth.login", request, status="failure", durable=True, reason="2fa")
            raise AuthenticationError(
                "invalid verification code",
                details={"two_factor_required": True},
            )
    elif payload.totp_code:
        # A code supplied for an account with no second factor enrolled is a mistake
        # worth surfacing, not silently ignoring.
        _audit(session, user, "auth.login", request, status="failure", durable=True, reason="unexpected_2fa")
        raise AuthenticationError("this account has no two-factor authentication enabled")

    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)

    user.failed_login_count = 0
    user.locked_until = None
    user.login_count = (user.login_count or 0) + 1
    user.last_login_at = now
    user.last_login_ip = client_ip(request)[:64]

    if user.last_login_at:
        session.add(
            AppNotification(
                user_id=user.user_id,
                level="info",
                title="Welcome back",
                body=f"Signed in from {client_ip(request)} at {now:%Y-%m-%d %H:%M} UTC.",
                entity_type="session",
                entity_id=str(user.user_id),
            )
        )
    _audit(session, user, "auth.login", request)
    return _tokens(user, request, session)


def _check_second_factor(user: AppUser, payload: LoginRequest, session: Session, request: Request) -> bool:
    """TOTP first, then a single-use recovery code."""
    from app.services import twofactor

    if payload.totp_code:
        try:
            secret = twofactor.decrypt_secret(user.totp_secret or "")
        except Exception:  # noqa: BLE001 - a corrupt secret must not authenticate anyone
            log.error("stored 2FA secret for user %s could not be decrypted", user.user_id)
            return False
        if twofactor.verify_code(secret, payload.totp_code):
            return True

    if payload.recovery_code and twofactor.redeem_recovery_code(session, user, payload.recovery_code):
        _audit(session, user, "auth.2fa_recovery_used", request)
        log.info("user %s used a recovery code", user.email)
        return True

    return False


@router.post("/refresh", response_model=TokenResponse, summary="Rotate an access token")
def refresh(payload: RefreshRequest, session: DbSession) -> TokenResponse:
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    user = session.get(AppUser, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("user not found or deactivated")

    # A revoked session must not be refreshable, otherwise "sign out everywhere"
    # would only end the access token.
    if payload.session_key:
        from app.services.sessions import assert_session_active

        assert_session_active(session, payload.session_key, user.user_id)
    return _tokens(user, None, None)


@router.post("/logout", response_model=Message, summary="Record a logout event")
def logout(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    session_key: str | None = None,
) -> Message:
    if session_key:
        from app.services.sessions import revoke_session

        revoke_session(session, session_key, user.user_id, reason="signed out")
    _audit(session, user, "auth.logout", request)
    return Message(message="Signed out successfully")


@router.get("/me", response_model=UserRead, summary="Current user profile and permissions")
def me(user: CurrentUser) -> UserRead:
    return _to_read(user)


@router.post("/change-password", response_model=Message, summary="Change own password")
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> Message:
    if not verify_password(payload.current_password, user.hashed_password):
        _audit(session, user, "auth.change_password", request, status="failure")
        raise AuthenticationError("current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = dt.datetime.now(dt.timezone.utc)
    _audit(session, user, "auth.change_password", request)
    return Message(message="Password updated")


@router.get("/session", summary="Session metadata for the shell UI")
def session_info(user: CurrentUser) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "permissions": sorted(ROLE_RIGHTS.get(user.role, set())),
        "theme": user.theme,
        "accent": user.accent,
        "density": user.density,
        "timezone": user.timezone,
        "rows_per_page": user.rows_per_page,
        "last_login_at": user.last_login_at,
        "expires_in_minutes": settings.access_token_expire_minutes,
        "features": list(settings.__class__.model_fields),
    }


@router.get("/demo-accounts", summary="Documented demo credentials (development only)")
def demo_accounts() -> dict[str, Any]:
    if settings.is_production:
        return {"accounts": []}
    return {
        "accounts": [
            {"email": settings.seed_admin_email, "password": settings.seed_admin_password, "role": "admin"},
            {
                "email": settings.seed_analyst_email,
                "password": settings.seed_analyst_password,
                "role": "analyst",
            },
            {
                "email": settings.seed_viewer_email,
                "password": settings.seed_viewer_password,
                "role": "viewer",
            },
        ]
    }
