"""Change-feed endpoints: price changes, new/removed products, category drift."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.analytics import service as analytics
from app.api.deps import DbSession, PaginationDep, ReadUser
from app.api.schemas import Page, PriceChangeRead
from app.api.sorting import build_order_by
from app.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/changes", tags=["changes"])


@router.get("/price", response_model=Page[PriceChangeRead], summary="Detected price changes")
def price_changes(
    session: DbSession,
    pagination: PaginationDep,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650)] = 90,
    direction: Annotated[str | None, Query(pattern="^(increase|decrease)$")] = None,
    category: str | None = None,
    brand: str | None = None,
    source: str | None = None,
    significant_only: Annotated[bool, Query()] = False,
    min_abs_change_pct: Annotated[float | None, Query(ge=0)] = None,
) -> Page[PriceChangeRead]:
    where = ["pc.full_date >= :since"]
    params: dict[str, Any] = {"since": dt.date.today() - dt.timedelta(days=days)}
    if direction:
        where.append("pc.direction = :direction")
        params["direction"] = direction
    if category:
        where.append("pc.category_name = :category")
        params["category"] = category
    if brand:
        where.append("pc.brand = :brand")
        params["brand"] = brand
    if source:
        where.append("pc.source_code = :source")
        params["source"] = source
    if significant_only:
        where.append("pc.is_significant")
    if min_abs_change_pct is not None:
        where.append("ABS(pc.change_pct) >= :min_abs")
        params["min_abs"] = min_abs_change_pct

    clause = "WHERE " + " AND ".join(where)
    order_by = build_order_by(
        pagination.sort_by,
        pagination.sort_dir,
        {
            "change_pct": "pc.change_pct",
            "detected_at": "pc.detected_at",
            "name": "pc.canonical_name",
            "previous_price": "pc.previous_price",
            "new_price": "pc.new_price",
        },
        "ABS(pc.change_pct)",
    )

    total = (
        session.execute(sa.text(f"SELECT COUNT(*) FROM vw_price_changes pc {clause}"), params).scalar() or 0
    )
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT pc.change_id, pc.product_id, pc.canonical_name, pc.brand, pc.category_name,
                   pc.source_code, pc.previous_price, pc.new_price, pc.previous_price_usd,
                   pc.new_price_usd, pc.change_abs, pc.change_pct, pc.direction,
                   pc.magnitude_band, pc.is_significant, pc.currency, pc.detected_at, pc.full_date
            FROM vw_price_changes pc {clause}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/top-movers", summary="Largest absolute price movements")
def top_movers(
    session: DbSession,
    _user: ReadUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    direction: Annotated[str | None, Query(pattern="^(increase|decrease)$")] = None,
) -> list[dict[str, Any]]:
    return analytics.top_movers(session, limit=limit, direction=direction)


@router.get("/events", summary="Product lifecycle events")
def events(
    session: DbSession,
    pagination: PaginationDep,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650)] = 180,
    event_type: Annotated[
        str | None, Query(pattern="^(new|removed|recurring|reactivated|category_changed)$")
    ] = None,
    category: str | None = None,
) -> Page[dict[str, Any]]:
    where = ["e.full_date >= :since"]
    params: dict[str, Any] = {"since": dt.date.today() - dt.timedelta(days=days)}
    if event_type:
        where.append("e.event_type = :event_type")
        params["event_type"] = event_type
    if category:
        where.append("p.category_id IN (SELECT category_id FROM dim_category WHERE name = :category)")
        params["category"] = category
    clause = "WHERE " + " AND ".join(where)
    total = (
        session.execute(
            sa.text(
                f"SELECT COUNT(*) FROM vw_product_events e JOIN dim_product p ON p.product_id = e.product_id {clause}"
            ),
            params,
        ).scalar()
        or 0
    )
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT e.event_id, e.product_id, e.canonical_name, e.brand, e.source_code,
                   e.event_type, e.severity, e.old_value, e.new_value, e.days_missing,
                   e.detected_at, e.full_date, e.is_active
            FROM vw_product_events e
            JOIN dim_product p ON p.product_id = e.product_id
            {clause}
            ORDER BY e.detected_at DESC
            LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/new", summary="Newly discovered products")
def new_products(
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650)] = 30,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    return analytics.new_products(session, days=days, limit=limit)


@router.get("/removed", summary="Products that disappeared from a source")
def removed_products(
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650)] = 180,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    return analytics.removed_products(session, days=days, limit=limit)


@router.get("/categories", summary="Products whose category changed")
def category_changes(
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650)] = 180,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    return analytics.category_changes(session, days=days, limit=limit)


@router.get("/category-drift", summary="SQL report: assortment movement per category")
def category_drift(
    session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=3650)] = 90
) -> list[dict[str, Any]]:
    return analytics.category_drift_report(session, days=days)


@router.get("/summary", summary="Change summary for the KPI cards")
def summary(
    session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=3650)] = 30
) -> dict[str, Any]:
    return analytics.change_event_summary(session, days=days)
