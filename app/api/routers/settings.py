"""Global application settings."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter

from app.api.deps import AdminUser, DbSession, OptionalUser
from app.api.schemas import Message, SettingRead, SettingUpdate
from app.core.errors import ProductNotFoundError
from app.models.app_users import AppSetting

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[SettingRead], summary="List settings")
def list_settings(session: DbSession, user: OptionalUser) -> list[SettingRead]:
    stmt = sa.select(AppSetting)
    if user is None or user.role != "admin":
        stmt = stmt.where(AppSetting.is_public.is_(True))
    rows = session.execute(stmt.order_by(AppSetting.category, AppSetting.key)).scalars().all()
    return [SettingRead.model_validate(row) for row in rows]


@router.put("/{key}", response_model=SettingRead, summary="Upsert a setting (admin)")
def upsert(key: str, payload: SettingUpdate, session: DbSession, admin: AdminUser) -> SettingRead:
    from app.models.app_users import AppAuditLog

    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=payload.value, value_type=payload.value_type or "string")
        session.add(row)
        session.flush()
    row.value = payload.value
    if payload.value_type is not None:
        row.value_type = payload.value_type
    if payload.category is not None:
        row.category = payload.category
    if payload.description is not None:
        row.description = payload.description
    if payload.is_public is not None:
        row.is_public = payload.is_public
    row.updated_by = admin.email
    session.flush()
    session.add(
        AppAuditLog(
            user_id=admin.user_id,
            user_email=admin.email,
            action="setting.updated",
            entity_type="app_setting",
            entity_id=key,
            details={"value_type": row.value_type, "category": row.category},
        )
    )
    session.flush()
    return SettingRead.model_validate(row)


@router.delete("/{key}", response_model=Message, summary="Delete a setting (admin)")
def delete(key: str, session: DbSession, admin: AdminUser) -> Message:
    from app.models.app_users import AppAuditLog

    row = session.get(AppSetting, key)
    if row is None:
        raise ProductNotFoundError(f"setting '{key}' not found")
    session.add(
        AppAuditLog(
            user_id=admin.user_id,
            user_email=admin.email,
            action="setting.deleted",
            entity_type="app_setting",
            entity_id=key,
        )
    )
    session.delete(row)
    session.flush()
    return Message(message=f"Setting '{key}' deleted")


@router.get("/groups", summary="Settings grouped by category")
def grouped(session: DbSession, user: OptionalUser) -> dict[str, Any]:
    rows = list_settings(session, user)
    groups: dict[str, list[SettingRead]] = {}
    for row in rows:
        groups.setdefault(row.category, []).append(row)
    return groups
