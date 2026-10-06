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
    PasswordChangeRequest,
    UserCreate,
    UserDeleteRequest,
    UserRead,
    UserStats,
    UserUpdate,
)
from app.api.security import ROLE_RIGHTS, at_least, generate_api_key, hash_password, verify_password
from app.core.config import settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    PermissionDeniedError,
    ProductNotFoundError,
    ValidationError,
)
from app.models.app_users import AppApiKey, AppAuditLog, AppNotification, AppSavedView, AppUser

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
    count_stmt = sa.select(sa.func.count()).select_from(User)
    if conditions:
        stmt = stmt.where(*conditions)
        # The count must apply the same filters, otherwise the page metadata lies
        # whenever a role or search term narrows the result set.
        count_stmt = count_stmt.where(*conditions)
    total = session.execute(count_stmt).scalar() or 0
    users = (
        session.execute(stmt.order_by(User.user_id).limit(pagination.page_size).offset(pagination.offset))
        .scalars()
        .all()
    )
    return Page.build([_to_read(user) for user in users], total, pagination.page, pagination.page_size)


@router.get("/me", response_model=UserRead, summary="My profile")
def me(user: CurrentUser) -> UserRead:
    return _to_read(user)


@router.get("/me/export", summary="Export my account data as JSON (portability)")
def export_me(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    from app.models.app_users import AppAlertRule

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)
    keys = session.execute(sa.select(AppApiKey).where(AppApiKey.user_id == user.user_id)).scalars().all()
    views = (
        session.execute(sa.select(AppSavedView).where(AppSavedView.user_id == user.user_id)).scalars().all()
    )
    alerts = (
        session.execute(sa.select(AppAlertRule).where(AppAlertRule.user_id == user.user_id)).scalars().all()
    )
    notifications = (
        session.execute(
            sa.select(AppNotification)
            .where(AppNotification.user_id == user.user_id)
            .order_by(AppNotification.created_at.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    activity = (
        session.execute(
            sa.text(
                """
            SELECT action, entity_type, entity_id, status, created_at
            FROM app_audit_log
            WHERE user_id = :user_id AND created_at >= :since
            ORDER BY created_at DESC LIMIT 200
            """
            ),
            {"user_id": user.user_id, "since": since},
        )
        .mappings()
        .all()
    )
    return {
        "exported_at": dt.datetime.now(dt.timezone.utc),
        "profile": _to_read(user).model_dump(mode="json"),
        "api_keys": [
            {
                "name": key.name,
                "prefix": key.prefix,
                "scopes": key.scopes,
                "is_active": key.is_active,
                "created_at": key.created_at,
                "last_used_at": key.last_used_at,
                "expires_at": key.expires_at,
            }
            for key in keys
        ],
        "saved_views": [
            {
                "name": view.name,
                "entity": view.entity,
                "is_favorite": view.is_favorite,
                "created_at": view.created_at,
            }
            for view in views
        ],
        "alert_rules": [
            {
                "name": alert.name,
                "metric": alert.metric,
                "operator": alert.operator,
                "threshold": alert.threshold,
                "channel": alert.channel,
                "is_active": alert.is_active,
                "created_at": alert.created_at,
            }
            for alert in alerts
        ],
        "notifications": [
            {
                "level": note.level,
                "title": note.title,
                "body": note.body,
                "entity_type": note.entity_type,
                "is_read": note.is_read,
                "created_at": note.created_at,
            }
            for note in notifications
        ],
        "recent_activity": [dict(row) for row in activity],
    }


#: Personal watchlist lives inside the profile preferences JSON, so it needs no
#: migration, syncs to every device with the profile, and rides along in the
#: portable data export. Capped so one account cannot grow the JSON unboundedly.
WATCHLIST_MAX_ITEMS = 200
WATCHLIST_KEY = "watchlist"


def _watchlist_ids(user: AppUser) -> list[int]:
    prefs = user.preferences or {}
    raw = prefs.get(WATCHLIST_KEY, [])
    seen: list[int] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            pid = int(item)
        except (TypeError, ValueError):
            continue
        if pid not in seen:
            seen.append(pid)
    return seen[:WATCHLIST_MAX_ITEMS]


def _save_watchlist(session: DbSession, user: AppUser, ids: list[int]) -> None:
    prefs = dict(user.preferences or {})
    prefs[WATCHLIST_KEY] = ids
    user.preferences = prefs
    session.flush()


def _watchlist_products(session: DbSession, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    rows = (
        session.execute(
            sa.text(
                """
            SELECT product_id, canonical_name, brand, category_name, price_usd,
                   currency, rating, availability, source_code, last_seen_at
            FROM vw_product_current WHERE product_id IN :ids
            """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": ids or [-1]},
        )
        .mappings()
        .all()
    )
    by_id = {row["product_id"]: dict(row) for row in rows}
    return [by_id[pid] for pid in ids if pid in by_id]


@router.get("/me/watchlist", summary="My watched products with live summaries")
def my_watchlist(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Starred products, resolved against the current warehouse view."""
    ids = _watchlist_ids(user)
    return {"count": len(ids), "product_ids": ids, "products": _watchlist_products(session, ids)}


@router.post("/me/watchlist/{product_id}", summary="Star a product into my watchlist")
def watch_product(product_id: int, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Idempotent add: watching twice is a no-op, unknown ids are 404."""
    exists = session.execute(
        sa.text("SELECT 1 FROM dim_product WHERE product_id = :pid"), {"pid": product_id}
    ).first()
    if exists is None:
        raise ProductNotFoundError(f"product {product_id} not found", details={"product_id": product_id})
    ids = _watchlist_ids(user)
    if product_id not in ids:
        ids.append(product_id)
        ids = ids[-WATCHLIST_MAX_ITEMS:]
        _save_watchlist(session, user, ids)
    return {"watched": True, "product_id": product_id, "count": len(ids)}


@router.delete("/me/watchlist/{product_id}", summary="Remove a product from my watchlist")
def unwatch_product(product_id: int, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Idempotent remove: unwatching what was never watched still succeeds."""
    ids = [pid for pid in _watchlist_ids(user) if pid != product_id]
    _save_watchlist(session, user, ids)
    return {"watched": False, "product_id": product_id, "count": len(ids)}


@router.delete("/me", response_model=Message, summary="Delete my account (password confirmation)")
def delete_me(payload: UserDeleteRequest, request: Request, session: DbSession, user: CurrentUser) -> Message:
    if not verify_password(payload.password, user.hashed_password):
        raise AuthenticationError("password is incorrect")
    email = user.email
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=None,
            user_email=email,
            action="user.self_delete",
            entity_type="app_user",
            entity_id=str(user.user_id),
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"email": email},
        )
    )
    session.flush()
    session.delete(user)
    return Message(message=f"Account '{email}' deleted. All personal data removed.")


@router.patch("/me", response_model=UserRead, summary="Update my profile & preferences")
def update_me(payload: UserUpdate, session: DbSession, user: CurrentUser) -> UserRead:
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field_name, value in data.items():
        setattr(user, field_name, value)
    session.flush()
    return _to_read(user)


@router.post("/me/password", response_model=Message, summary="Change my password")
def set_password(payload: PasswordChangeRequest, session: DbSession, user: CurrentUser) -> Message:
    """Self-service password change.

    Kept separate from `PATCH /users/me` so the current password is always
    required and the response never echoes the new secret.
    """
    if not verify_password(payload.current_password, user.hashed_password):
        raise AuthenticationError("Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise ValidationError("The new password must differ from the current one")

    user.hashed_password = hash_password(payload.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="user.password_changed",
            entity_type="app_user",
            entity_id=str(user.user_id),
            details={"self_service": True},
        )
    )
    session.flush()
    return Message(message="Password updated. Existing sessions remain active.")


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
        raise ValidationError("you cannot deactivate your own account")
    user.is_active = False
    return Message(message=f"User '{user.email}' deactivated")


@router.get("/{user_id}/api-keys", response_model=list[ApiKeyRead], summary="API keys of a user")
def list_keys(user_id: int, session: DbSession, user: CurrentUser) -> list[ApiKeyRead]:
    if user_id != user.user_id and not at_least(user.role, "admin"):
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
        raise PermissionDeniedError("you can only create keys for yourself")
    plain, prefix, hashed = generate_api_key()
    # A key can never be granted more than its owner already has.
    owner = session.get(AppUser, user_id)
    role_rights = ROLE_RIGHTS.get(owner.role if owner else "viewer", set())
    requested = payload.scopes
    if requested:
        beyond = sorted(set(requested) - role_rights)
        if beyond:
            raise PermissionDeniedError(
                f"cannot grant scope(s) the owner does not hold: {', '.join(beyond)}",
                details={"owner_role": owner.role if owner else "viewer", "beyond_role": beyond},
            )
    row = AppApiKey(
        user_id=user_id,
        name=payload.name,
        prefix=prefix,
        hashed_key=hashed,
        scopes=sorted(requested) if requested else None,
        is_active=True,
        expires_at=(
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=payload.expires_in_days)
            if payload.expires_in_days
            else None
        ),
        rate_limit_per_minute=payload.rate_limit_per_minute or settings.api_rate_limit_per_minute,
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
        raise PermissionDeniedError("you can only revoke your own keys")
    session.delete(row)
    return Message(message="API key revoked")
