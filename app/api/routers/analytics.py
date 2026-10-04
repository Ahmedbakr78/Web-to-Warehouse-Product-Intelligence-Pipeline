"""Analytics endpoints: KPIs, trends, leaderboards and SQL reports."""

from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.analytics import service as analytics
from app.api.deps import DbSession, ReadUser

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/kpi", summary="Headline KPI cards")
def kpi(session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=3650)] = 30) -> dict[str, Any]:
    return analytics.kpi_summary(session, days=days)


@router.get("/trend", summary="Daily KPI trend")
def trend(session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=3650)] = 90) -> list[dict[str, Any]]:
    return analytics.daily_trend(session, days=days)


@router.get("/price-trend", summary="Daily price-change trend")
def price_trend(session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=3650)] = 90) -> list[dict[str, Any]]:
    return analytics.price_change_timeline(session, days=days)


@router.get("/categories", summary="Category breakdown")
def categories(session: DbSession, _user: ReadUser, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict[str, Any]]:
    return analytics.category_breakdown(session, limit=limit)


@router.get("/brands", summary="Brand leaderboard")
def brands(session: DbSession, _user: ReadUser, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict[str, Any]]:
    return analytics.brand_leaderboard(session, limit=limit)


@router.get("/availability", summary="In-stock ratio per category")
def availability(session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    return analytics.availability_summary(session)


@router.get("/sources", summary="Source coverage and reliability")
def sources(session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    return analytics.source_health(session)


@router.get("/category-index", summary="Daily category price index")
def category_index(
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650)] = 60,
    category: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"since": None}
    where = ""
    if category:
        where = "AND category_name = :category"
        params["category"] = category
    import datetime as dt

    params["since"] = dt.date.today() - dt.timedelta(days=days)
    rows = session.execute(
        sa.text(
            f"""
            SELECT date_id, full_date, category_id, category_name, observation_count,
                   avg_price_usd, min_price_usd, max_price_usd, avg_rating, price_stddev, distinct_products
            FROM vw_category_price_index
            WHERE full_date >= :since {where}
            ORDER BY full_date, category_name
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/report/price-changes", summary="SQL report: price changes")
def report_price_changes(
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650)] = 30,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict[str, Any]]:
    return analytics.price_change_report(session, days=days, limit=limit)


@router.get("/report/catalog", summary="SQL report: scraped vs internal catalog")
def report_catalog(session: DbSession, _user: ReadUser, run_id: str | None = None) -> list[dict[str, Any]]:
    return analytics.catalog_reconciliation(session, run_id=run_id, limit=500)


@router.get("/report/compliance", summary="SQL report: robots.txt / rate-limit compliance evidence")
def report_compliance(session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=365)] = 7) -> dict[str, Any]:
    return analytics.compliance_report(session, days=days)


@router.get("/report/source-matrix", summary="SQL report: source x category coverage matrix")
def source_matrix(session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.text(
            """
            SELECT s.source_code,
                   p.category_id,
                   c.name AS category_name,
                   COUNT(DISTINCT p.product_id) AS products,
                   ROUND(CAST(AVG(s.price_usd) AS DECIMAL(24,6)), 2) AS avg_price_usd
            FROM fact_price_snapshot s
            JOIN dim_product p ON p.product_id = s.product_id
            LEFT JOIN dim_category c ON c.category_id = p.category_id
            GROUP BY s.source_code, p.category_id, c.name
            ORDER BY s.source_code, products DESC
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/export/products.csv", summary="Export the current product list as CSV")
def export_products(session: DbSession, _user: ReadUser, limit: Annotated[int, Query(ge=1, le=50_000)] = 5_000) -> str:
    import csv
    import io

    rows = session.execute(
        sa.text(
            """
            SELECT product_id, canonical_name, brand, category_name, availability, price, price_usd,
                   currency, rating, price_change_pct, last_seen_at, source_code, product_url
            FROM vw_product_current ORDER BY product_id LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow([row[column] for column in row.keys()])
    return buffer.getvalue()