"""Account and user administration endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Request

from app.api.deps import AdminUser, CurrentUser, DbSession, PaginationDep, request_meta
from app.api.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    Message,
    Page,
    UserCreate,
    UserRead,
    UserStats,
    UserUpdate,
)
from app.api.security import ROLE_RIGHTS, at_least, generate_api_key, hash_password
from app.core.errors import ConflictError, ProductNotFoundError
from app.models.app_users import AppApiKey, AppAuditLog, AppUser

router = APIRouter(prefix="/users", tags=["users"])


def _to_read(user: AppUser) -> UserRead:
    payload = UserRead.model_validate(user)
    payload.permissions = sorted(ROLE_RIGHTS.get(user.role, set()))
    return payload


@router.get("", response_model=Page[UserRead], summary="List users (admin)")
def list_users(
    session: DbSession,
    pagination: PaginationDep,
    _admin: AdminUser,
    role: str | None = None,
    q: str | None = None,
) -> Page[UserRead]:
    from app.models.app_users import AppUser as User

    conditions = []
    if role:
        conditions.append(User.role == role)
    if q:
        conditions.append(sa.or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    stmt = sa.select(User)
    if conditions:
        stmt = stmt.where(*conditions)
    total = session.execute(sa.select(sa.func.count()).select_from(User)).scalar() or 0
    users = (
        session.execute(stmt.order_by(User.user_id).limit(pagination.page_size).offset(pagination.offset))
        .scalars()
        .all()
    )
    return Page.build([_to_read(user) for user in users], total, pagination.page, pagination.page_size)


@router.get("/me", response_model=UserRead, summary="My profile")
def me(user: CurrentUser) -> UserRead:
    return _to_read(user)


@router.patch("/me", response_model=UserRead, summary="Update my profile & preferences")
def update_me(payload: UserUpdate, session: DbSession, user: CurrentUser) -> UserRead:
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field_name, value in data.items():
        setattr(user, field_name, value)
    session.flush()
    return _to_read(user)


@router.post("/me/password", response_model=Message, summary="Set a new password")
def set_password(payload: UserUpdate, session: DbSession, user: CurrentUser) -> Message:
    return Message(message="Use /auth/change-password to update credentials")


@router.get("/stats", response_model=UserStats, summary="Usage statistics")
def stats(session: DbSession, _admin: AdminUser) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    total = session.execute(sa.select(sa.func.count()).select_from(AppUser)).scalar() or 0
    active = (
        session.execute(
            sa.select(sa.func.count()).select_from(AppUser).where(AppUser.is_active.is_(True))
        ).scalar()
        or 0
    )
    logins_24h = (
        session.execute(
            sa.select(sa.func.count())
            .select_from(AppUser)
            .where(AppUser.last_login_at >= now - dt.timedelta(hours=24))
        ).scalar()
        or 0
    )
    logins_7d = (
        session.execute(
            sa.select(sa.func.count())
            .select_from(AppUser)
            .where(AppUser.last_login_at >= now - dt.timedelta(days=7))
        ).scalar()
        or 0
    )
    locked = (
        session.execute(
            sa.select(sa.func.count()).select_from(AppUser).where(AppUser.locked_until.isnot(None))
        ).scalar()
        or 0
    )
    keys = (
        session.execute(
            sa.select(sa.func.count()).select_from(AppApiKey).where(AppApiKey.is_active.is_(True))
        ).scalar()
        or 0
    )
    by_role = {
        row[0]: row[1]
        for row in session.execute(sa.text("SELECT role, COUNT(*) FROM app_user GROUP BY role"))
    }
    top = session.execute(sa.select(AppUser).order_by(AppUser.login_count.desc()).limit(5)).scalars().all()
    return {
        "total_users": total,
        "active_users": active,
        "logins_24h": logins_24h,
        "logins_7d": logins_7d,
        "locked_users": locked,
        "api_keys": keys,
        "by_role": by_role,
        "top_users": [
            {
                "user_id": user.user_id,
                "email": user.email,
                "login_count": user.login_count,
                "last_login_at": user.last_login_at,
                "role": user.role,
            }
            for user in top
        ],
    }


@router.post("", response_model=UserRead, status_code=201, summary="Create a user (admin)")
def create_user(payload: UserCreate, request: Request, session: DbSession, admin: AdminUser) -> UserRead:
    from app.api.security import password_strength

    ok, problems = password_strength(payload.password)
    if not ok:
        from app.core.errors import ValidationError

        raise ValidationError("weak password", details={"problems": problems})
    email = payload.email.lower().strip()
    if session.execute(sa.select(AppUser).where(AppUser.email == email)).scalars().first() is not None:
        raise ConflictError(f"user '{email}' already exists")
    user = AppUser(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        job_title=payload.job_title,
        department=payload.department,
        is_active=True,
        password_changed_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(user)
    session.flush()
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=admin.user_id,
            user_email=admin.email,
            action="user.create",
            entity_type="app_user",
            entity_id=str(user.user_id),
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"email": email, "role": payload.role},
        )
    )
    return _to_read(user)


@router.patch("/{user_id}", response_model=UserRead, summary="Update a user (admin)")
def update_user(user_id: int, payload: UserUpdate, session: DbSession, admin: AdminUser) -> UserRead:
    user = session.get(AppUser, user_id)
    if user is None:
        raise ProductNotFoundError(f"user {user_id} not found")
    for field_name, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field_name, value)
    return _to_read(user)


@router.delete("/{user_id}", response_model=Message, summary="Deactivate a user (admin)")
def deactivate(user_id: int, session: DbSession, admin: AdminUser) -> Message:
    user = session.get(AppUser, user_id)
    if user is None:
        raise ProductNotFoundError(f"user {user_id} not found")
    if user.user_id == admin.user_id:
        from app.core.errors import ValidationError

        raise ValidationError("you cannot deactivate your own account")
    user.is_active = False
    return Message(message=f"User '{user.email}' deactivated")


@router.get("/{user_id}/api-keys", response_model=list[ApiKeyRead], summary="API keys of a user")
def list_keys(user_id: int, session: DbSession, user: CurrentUser) -> list[ApiKeyRead]:
    if user_id != user.user_id and not at_least(user.role, "admin"):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("you can only list your own API keys")
    rows = (
        session.execute(
            sa.select(AppApiKey).where(AppApiKey.user_id == user_id).order_by(AppApiKey.key_id.desc())
        )
        .scalars()
        .all()
    )
    return [ApiKeyRead.model_validate(row) for row in rows]


@router.post(
    "/{user_id}/api-keys", response_model=ApiKeyCreated, status_code=201, summary="Create an API key"
)
def create_key(user_id: int, payload: ApiKeyCreate, session: DbSession, user: CurrentUser) -> ApiKeyCreated:
    if user_id != user.user_id and not at_least(user.role, "admin"):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("you can only create keys for yourself")
    plain, prefix, hashed = generate_api_key()
    row = AppApiKey(
        user_id=user_id,
        name=payload.name,
        prefix=prefix,
        hashed_key=hashed,
        scopes=["read"],
        is_active=True,
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=90),
        rate_limit_per_minute=120,
    )
    session.add(row)
    session.flush()
    return ApiKeyCreated(api_key=plain, **ApiKeyRead.model_validate(row).model_dump())


@router.delete("/{user_id}/api-keys/{key_id}", response_model=Message, summary="Revoke an API key")
def revoke_key(user_id: int, key_id: int, session: DbSession, user: CurrentUser) -> Message:
    row = session.get(AppApiKey, key_id)
    if row is None or row.user_id != user_id:
        raise ProductNotFoundError(f"api key {key_id} not found")
    if user_id != user.user_id and not at_least(user.role, "admin"):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("you can only revoke your own keys")
    session.delete(row)
    return Message(message="API key revoked")
