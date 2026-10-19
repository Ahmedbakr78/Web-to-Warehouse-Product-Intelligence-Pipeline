"""Audit log and HTTP compliance audit endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.analytics import service as analytics
from app.api.deps import AdminUser, CurrentUser, DbSession, PaginationDep, ReadUser

router = APIRouter(tags=["audit"])


@router.get("/audit/me", summary="My recent audited activity")
def my_activity(
    session: DbSession,
    user: CurrentUser,
    pagination: PaginationDep,
    days: Annotated[int, Query(ge=1, le=3650)] = 30,
) -> dict[str, Any]:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    params: dict[str, Any] = {"user_id": user.user_id, "since": since}
    total = (
        session.execute(
            sa.text("SELECT COUNT(*) FROM app_audit_log WHERE user_id = :user_id AND created_at >= :since"),
            params,
        ).scalar()
        or 0
    )
    rows = (
        session.execute(
            sa.text(
                """
            SELECT audit_id, action, entity_type, entity_id, status, ip_address,
                   duration_ms, created_at
            FROM app_audit_log
            WHERE user_id = :user_id AND created_at >= :since
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "window_days": days,
    }


@router.get("/audit", summary="Application audit log (admin)")
def audit_log(
    session: DbSession,
    pagination: PaginationDep,
    _admin: AdminUser,
    action: str | None = None,
    user_id: int | None = None,
    days: Annotated[int | None, Query(ge=1, le=3650)] = None,
) -> dict[str, Any]:
    where = ["1 = 1"]
    params: dict[str, Any] = {}
    if action:
        where.append("action = :action")
        params["action"] = action
    if user_id:
        where.append("user_id = :user_id")
        params["user_id"] = user_id
    if days:
        where.append("created_at >= :since")
        params["since"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    clause = "WHERE " + " AND ".join(where)
    total = session.execute(sa.text(f"SELECT COUNT(*) FROM app_audit_log {clause}"), params).scalar() or 0
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT audit_id, user_id, user_email, action, entity_type, entity_id, status,
                   ip_address, duration_ms, created_at
            FROM app_audit_log {clause}
            ORDER BY created_at DESC LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get("/audit/actions", summary="Distinct audited actions")
def actions(session: DbSession, _admin: AdminUser) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            sa.text(
                "SELECT action, COUNT(*) AS count, MAX(created_at) AS last_seen FROM app_audit_log GROUP BY action ORDER BY count DESC"
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/audit/http", summary="Outbound HTTP compliance log")
def http_log(
    session: DbSession,
    _user: ReadUser,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    source_code: str | None = None,
) -> list[dict[str, Any]]:
    return analytics.http_log(session, limit=limit, source_code=source_code)


@router.get("/audit/compliance", summary="Compliance summary (robots.txt, cache, retries)")
def compliance(
    session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=365)] = 7
) -> dict[str, Any]:
    return analytics.compliance_report(session, days=days)
