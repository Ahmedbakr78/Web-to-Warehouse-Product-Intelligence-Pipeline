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
from app.models.app_users import AppAuditLog, AppNotification, AppUser

log = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


def _to_read(user: AppUser) -> UserRead:
    data = UserRead.model_validate(user)
    data.permissions = sorted(ROLE_RIGHTS.get(user.role, set()))
    return data


def _tokens(user: AppUser) -> TokenResponse:
    access = create_access_token(user.user_id, role=user.role, email=user.email)
    refresh = create_refresh_token(user.user_id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        role=user.role,
        user=_to_read(user),
    )


def _audit(
    session: Session,
    user: AppUser | None,
    action: str,
    request: Request,
    status: str = "success",
    **details: Any,
) -> None:
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


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for tokens")
def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    email = payload.email.lower().strip()
    user = session.execute(sa.select(AppUser).where(AppUser.email == email)).scalars().first()

    if user is None:
        _audit(session, None, "auth.login", request, status="failure", email=email)
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
        _audit(session, user, "auth.login", request, status="failure")
        raise AuthenticationError("invalid email or password")

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
    return _tokens(user)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate an access token")
def refresh(payload: RefreshRequest, session: DbSession) -> TokenResponse:
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    user = session.get(AppUser, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("user not found or deactivated")
    return _tokens(user)


@router.post("/logout", response_model=Message, summary="Record a logout event")
def logout(request: Request, user: CurrentUser, session: DbSession) -> Message:
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
