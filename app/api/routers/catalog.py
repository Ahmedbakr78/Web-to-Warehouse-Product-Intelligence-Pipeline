"""Internal catalog endpoints: SKUs, reconciliation results, price-gap analysis."""

from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.api.deps import DbSession, PaginationDep, ReadUser
from app.api.schemas import CatalogMatchRead, Page

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/reconciliation", response_model=Page[CatalogMatchRead], summary="Scraped vs internal catalog")
def reconciliation(
    session: DbSession,
    pagination: PaginationDep,
    _user: ReadUser,
    run_id: str | None = None,
    match_status: str | None = None,
    only_mismatches: Annotated[bool, Query()] = False,
) -> Page[CatalogMatchRead]:
    where = ["1 = 1"]
    params: dict[str, Any] = {}
    if run_id:
        where.append("run_id = :run_id")
        params["run_id"] = run_id
    if match_status:
        where.append("match_status = :match_status")
        params["match_status"] = match_status
    if only_mismatches:
        where.append("is_price_mismatch")
    clause = "WHERE " + " AND ".join(where)
    total = (
        session.execute(sa.text(f"SELECT COUNT(*) FROM vw_catalog_reconciliation {clause}"), params).scalar()
        or 0
    )
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT match_id, run_id, catalog_sku, catalog_name, catalog_brand, catalog_category, catalog_price,
                   supplier, product_id, scraped_name, scraped_brand, scraped_category, scraped_price_usd,
                   price_gap_abs, price_gap_pct, match_status, match_strategy, similarity_score,
                   category_match, brand_match, is_price_mismatch, matched_at
            FROM vw_catalog_reconciliation {clause}
            ORDER BY ABS(COALESCE(price_gap_pct, 0)) DESC
            LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/products", response_model=Page[dict[str, Any]], summary="Internal catalog SKUs")
def products(
    session: DbSession,
    pagination: PaginationDep,
    _user: ReadUser,
    q: str | None = None,
    status: str | None = None,
) -> Page[dict[str, Any]]:
    where = ["1 = 1"]
    params: dict[str, Any] = {}
    if q:
        where.append("(name LIKE :q OR sku LIKE :q OR brand LIKE :q)")
        params["q"] = f"%{q}%"
    if status:
        where.append("status = :status")
        params["status"] = status
    clause = "WHERE " + " AND ".join(where)
    total = session.execute(sa.text(f"SELECT COUNT(*) FROM catalog_product {clause}"), params).scalar() or 0
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT sku, name, brand, category, supplier, cost_price, list_price, currency,
                   qty_on_hand, status, product_url, updated_at
            FROM catalog_product {clause}
            ORDER BY sku LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/summary", summary="Reconciliation KPIs")
def summary(session: DbSession, _user: ReadUser, run_id: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    clause = ""
    if run_id:
        clause = "WHERE run_id = :run_id"
        params["run_id"] = run_id
    totals = (
        session.execute(
            sa.text(
                f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN match_status = 'matched' THEN 1 ELSE 0 END) AS matched,
                   SUM(CASE WHEN match_status = 'unmatched' THEN 1 ELSE 0 END) AS unmatched,
                   SUM(CASE WHEN is_price_mismatch THEN 1 ELSE 0 END) AS price_mismatches,
                   ROUND(CAST(AVG(similarity_score) AS DECIMAL(24,6)), 4) AS avg_similarity,
                   ROUND(CAST(AVG(price_gap_pct) AS DECIMAL(24,6)), 2) AS avg_price_gap_pct
            FROM vw_catalog_reconciliation {clause}
            """
            ),
            params,
        )
        .mappings()
        .one()
    )
    by_strategy = (
        session.execute(
            sa.text(
                f"""
            SELECT match_strategy, COUNT(*) AS count FROM vw_catalog_reconciliation {clause}
            GROUP BY match_strategy ORDER BY count DESC
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    by_supplier = (
        session.execute(
            sa.text(
                f"""
            SELECT supplier, COUNT(*) AS skus, ROUND(CAST(AVG(price_gap_pct) AS DECIMAL(24,6)), 2) AS avg_gap_pct
            FROM vw_catalog_reconciliation {clause}
            GROUP BY supplier ORDER BY skus DESC
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return {
        "totals": dict(totals),
        "by_strategy": [dict(row) for row in by_strategy],
        "by_supplier": [dict(row) for row in by_supplier],
        "run_id": run_id,
    }


@router.get("/opportunities", summary="Top pricing opportunities (cheaper / dearer than market)")
def opportunities(
    session: DbSession, _user: ReadUser, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            sa.text(
                """
            SELECT catalog_sku, catalog_name, supplier, catalog_price, scraped_name, scraped_price_usd,
                   price_gap_abs, price_gap_pct,
                   CASE WHEN price_gap_pct < 0 THEN 'we_are_dearer' ELSE 'we_are_cheaper' END AS position
            FROM vw_catalog_reconciliation
            WHERE is_price_mismatch AND price_gap_pct IS NOT NULL
            ORDER BY ABS(price_gap_pct) DESC LIMIT :limit
            """
            ),
            {"limit": limit},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
