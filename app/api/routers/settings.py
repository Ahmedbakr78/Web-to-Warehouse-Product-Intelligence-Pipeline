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
def upsert(key: str, payload: SettingUpdate, session: DbSession, _admin: AdminUser) -> SettingRead:
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=payload.value, value_type=payload.value_type)
        session.add(row)
    row.value = payload.value
    row.value_type = payload.value_type
    session.flush()
    return SettingRead.model_validate(row)


@router.delete("/{key}", response_model=Message, summary="Delete a setting (admin)")
def delete(key: str, session: DbSession, _admin: AdminUser) -> Message:
    row = session.get(AppSetting, key)
    if row is None:
        raise ProductNotFoundError(f"setting '{key}' not found")
    session.delete(row)
    return Message(message=f"Setting '{key}' deleted")


@router.get("/groups", summary="Settings grouped by category")
def grouped(session: DbSession, user: OptionalUser) -> dict[str, Any]:
    rows = list_settings(session, user)
    groups: dict[str, list[SettingRead]] = {}
    for row in rows:
        groups.setdefault(row.category, []).append(row)
    return groups
