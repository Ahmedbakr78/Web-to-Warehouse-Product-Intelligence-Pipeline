"""Product catalogue endpoints: list, search, detail, price history, categories."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.analytics import service as analytics
from app.api.deps import DbSession, PaginationDep, ReadUser
from app.api.schemas import Page, ProductDetail, ProductSummary
from app.core.errors import ProductNotFoundError
from app.ingestion.cleaning import normalise_name_key
from app.models.dimensions import DimProduct

router = APIRouter(prefix="/products", tags=["products"])

SORTABLE = {
    "canonical_name": "v.canonical_name",
    "name": "v.canonical_name",
    "price": "v.price_usd",
    "price_change_pct": "v.price_change_pct",
    "rating": "v.rating",
    "last_seen_at": "v.last_seen_at",
    "first_seen_at": "v.first_seen_at",
    "observation_count": "v.observation_count",
    "category_name": "v.category_name",
    "brand": "v.brand",
}

BASE_FROM = "FROM vw_product_current v"


@router.get("", response_model=Page[ProductSummary], summary="List / filter products")
def list_products(
    session: DbSession,
    pagination: PaginationDep,
    _user: ReadUser,
    q: Annotated[str | None, Query(description="Free-text search on name, brand, category")] = None,
    category: Annotated[str | None, Query(description="Category name or path")] = None,
    brand: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query(description="Source code")] = None,
    availability: Annotated[str | None, Query()] = None,
    in_stock: Annotated[bool | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    min_change_pct: Annotated[
        float | None,
        Query(
            ge=-100,
            le=100,
            description="Signed lower bound on price_change_pct. Use a negative value "
            "(for example -5) to keep only products that fell by 5% or more.",
        ),
    ] = None,
    max_change_pct: Annotated[
        float | None,
        Query(
            ge=-100,
            le=100,
            description="Signed upper bound on price_change_pct. Use a positive value "
            "(for example 5) to keep only products that rose by 5% or more.",
        ),
    ] = None,
    new_since_days: Annotated[
        int | None, Query(ge=0, le=3650, description="First seen within N days")
    ] = None,
    observed_within_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
) -> Page[ProductSummary]:
    where: list[str] = []
    params: dict[str, Any] = {}

    if q:
        needle = f"%{q.strip()}%"
        where.append(
            "(v.canonical_name LIKE :q OR v.brand LIKE :q OR v.category_name LIKE :q OR v.product_url LIKE :q)"
        )
        params["q"] = needle
    if category:
        where.append(
            "(v.category_path = :category OR v.category_name = :category OR v.category_path LIKE :category_like)"
        )
        params["category"] = category
        params["category_like"] = f"{category}%"
    if brand:
        where.append("v.brand = :brand")
        params["brand"] = brand
    if source:
        where.append("v.source_code = :source")
        params["source"] = source
    if availability:
        where.append("v.availability = :availability")
        params["availability"] = availability
    if in_stock is not None:
        where.append("v.in_stock = :in_stock")
        params["in_stock"] = in_stock
    if is_active is not None:
        where.append("v.is_active = :is_active")
        params["is_active"] = is_active
    if min_price is not None:
        where.append("v.price_usd >= :min_price")
        params["min_price"] = min_price
    if max_price is not None:
        where.append("v.price_usd <= :max_price")
        params["max_price"] = max_price
    if min_rating is not None:
        where.append("v.rating >= :min_rating")
        params["min_rating"] = min_rating
    if min_change_pct is not None:
        # Signed lower bound: min_change_pct=-5 means "moved by 5% or more".
        where.append("v.price_change_pct <= :min_change_pct")
        params["min_change_pct"] = min_change_pct
    if max_change_pct is not None:
        # Signed upper bound: max_change_pct=5 means "moved by 5% or more".
        where.append("v.price_change_pct >= :max_change_pct")
        params["max_change_pct"] = max_change_pct
    if new_since_days is not None:
        where.append("v.first_seen_at >= :new_since")
        params["new_since"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=new_since_days)
    if observed_within_days is not None:
        where.append("v.last_seen_at >= :seen_since")
        params["seen_since"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=observed_within_days)

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sort = SORTABLE.get((pagination.sort_by or "").lower(), "v.last_seen_at")
    direction = "ASC" if str(pagination.sort_dir).lower() == "asc" else "DESC"

    total = session.execute(sa.text(f"SELECT COUNT(*) {BASE_FROM} {clause}"), params).scalar() or 0
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT v.product_id, v.canonical_name, v.brand, v.category_name, v.category_path,
                   v.availability, v.price, v.price_usd, v.currency, v.rating, v.in_stock,
                   v.price_change_pct, v.price_change_abs, v.is_active, v.last_seen_at,
                   v.first_seen_at, v.observation_count, v.product_url, v.image_url,
                   v.source_code, v.match_strategy, v.match_score
            {BASE_FROM} {clause}
            -- Portable "NULLs last" (MySQL has no NULLS LAST modifier).
            ORDER BY ({sort} IS NULL) ASC, {sort} {direction}
            LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/facets", summary="Facet counts for the products screen")
def facets(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    categories = (
        session.execute(
            sa.text(
                """
            SELECT category_name, COUNT(*) AS count FROM vw_product_current
            WHERE category_name IS NOT NULL
            GROUP BY category_name ORDER BY count DESC LIMIT 40
            """
            )
        )
        .mappings()
        .all()
    )
    brands = (
        session.execute(
            sa.text(
                """
            SELECT brand, COUNT(*) AS count FROM vw_product_current
            WHERE brand IS NOT NULL GROUP BY brand ORDER BY count DESC LIMIT 40
            """
            )
        )
        .mappings()
        .all()
    )
    sources = (
        session.execute(
            sa.text(
                """
            SELECT source_code, COUNT(*) AS count FROM vw_product_current
            WHERE source_code IS NOT NULL GROUP BY source_code ORDER BY count DESC
            """
            )
        )
        .mappings()
        .all()
    )
    availability = (
        session.execute(
            sa.text(
                """
            SELECT availability, COUNT(*) AS count FROM vw_product_current
            WHERE availability IS NOT NULL GROUP BY availability ORDER BY count DESC
            """
            )
        )
        .mappings()
        .all()
    )
    price_band = (
        session.execute(
            sa.text(
                """
            SELECT CASE
                     WHEN price_usd < 25 THEN 'a_0_25'
                     WHEN price_usd < 100 THEN 'b_25_100'
                     WHEN price_usd < 500 THEN 'c_100_500'
                     WHEN price_usd < 1000 THEN 'd_500_1000'
                     ELSE 'e_1000_plus' END AS band,
                   COUNT(*) AS count
            FROM vw_product_current WHERE price_usd IS NOT NULL GROUP BY band ORDER BY band
            """
            )
        )
        .mappings()
        .all()
    )
    return {
        "categories": [dict(row) for row in categories],
        "brands": [dict(row) for row in brands],
        "sources": [dict(row) for row in sources],
        "availability": [dict(row) for row in availability],
        "price_bands": [dict(row) for row in price_band],
    }


@router.get("/categories", summary="Category tree with live counts")
def categories(session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    return analytics.category_tree(session)


@router.get("/{product_id}", response_model=ProductDetail, summary="Product detail")
def product_detail(
    product_id: int, session: DbSession, _user: ReadUser, history_limit: int = 400
) -> ProductDetail:
    payload = analytics.product_detail(session, product_id)
    if not payload:
        raise ProductNotFoundError(f"product {product_id} not found", details={"product_id": product_id})
    payload["history"] = analytics.price_history(session, product_id, limit=history_limit)
    return ProductDetail(**payload)


@router.get("/{product_id}/history", summary="Price history time series")
def product_history(product_id: int, session: DbSession, _user: ReadUser, limit: int = 500) -> dict[str, Any]:
    rows = analytics.price_history(session, product_id, limit=limit)
    if not rows:
        raise ProductNotFoundError(f"product {product_id} not found")
    return {
        "product_id": product_id,
        "points": len(rows),
        "first": rows[0],
        "last": rows[-1],
        "min_price": min((row["price_usd"] for row in rows if row["price_usd"] is not None), default=None),
        "max_price": max((row["price_usd"] for row in rows if row["price_usd"] is not None), default=None),
        "avg_price": round(
            sum(row["price_usd"] for row in rows if row["price_usd"] is not None)
            / max(1, len([row for row in rows if row["price_usd"] is not None])),
            2,
        ),
        "history": rows,
    }


@router.get("/{product_id}/duplicates", summary="Similar products (duplicate candidates)")
def product_duplicates(
    product_id: int, session: DbSession, _user: ReadUser, limit: int = 10
) -> dict[str, Any]:
    from app.ingestion.dedupe import combined_similarity

    product = session.get(DimProduct, product_id)
    if product is None:
        raise ProductNotFoundError(f"product {product_id} not found")

    block = (product.normalized_name or "")[:4]
    candidates = (
        session.execute(
            sa.select(DimProduct)
            .where(DimProduct.product_id != product_id, DimProduct.normalized_name.like(f"{block}%"))
            .limit(60)
        )
        .scalars()
        .all()
    )
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        score, parts = combined_similarity(
            product.canonical_name,
            candidate.canonical_name,
            brand_a=product.brand,
            brand_b=candidate.brand,
        )
        scored.append(
            {
                "product_id": candidate.product_id,
                "name": candidate.canonical_name,
                "score": score,
                "parts": parts,
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"product_id": product_id, "name": product.canonical_name, "candidates": scored[:limit]}


@router.get("/{product_id}/catalog", summary="Catalog links for a product")
def product_catalog(product_id: int, session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            sa.text(
                """
            SELECT match_id, run_id, catalog_sku, catalog_name, catalog_brand, catalog_price,
                   price_gap_abs, price_gap_pct, match_status, match_strategy, similarity_score
            FROM vw_catalog_reconciliation WHERE product_id = :pid ORDER BY matched_at DESC
            """
            ),
            {"pid": product_id},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/search/suggest", summary="Type-ahead suggestions")
def suggest(
    session: DbSession, _user: ReadUser, q: Annotated[str, Query(min_length=2)], limit: int = 10
) -> list[dict[str, Any]]:
    key = normalise_name_key(q)
    rows = (
        session.execute(
            sa.text(
                """
            SELECT product_id, canonical_name, brand, category_name, price_usd, currency, image_url
            FROM vw_product_current
            WHERE canonical_name LIKE :like OR normalized_name LIKE :like
            ORDER BY canonical_name LIMIT :limit
            """
            ),
            {"like": f"%{key or q}%", "limit": min(limit, 25)},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/compare/ids", summary="Side-by-side comparison")
def compare(
    session: DbSession, _user: ReadUser, ids: Annotated[str, Query(description="Comma separated product ids")]
) -> list[dict[str, Any]]:
    wanted = [int(part) for part in ids.split(",") if part.strip().isdigit()][:6]
    if not wanted:
        return []
    placeholders = ",".join(f":id{index}" for index in range(len(wanted)))
    params = {f"id{index}": value for index, value in enumerate(wanted)}
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT product_id, canonical_name, brand, category_name, price_usd, currency, rating,
                   availability, in_stock, price_change_pct, observation_count, last_seen_at, image_url
            FROM vw_product_current WHERE product_id IN ({placeholders})
            """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/count/active", include_in_schema=False)
def active_count(session: DbSession) -> dict[str, int]:
    return {
        "active": session.execute(
            sa.select(sa.func.count()).select_from(DimProduct).where(DimProduct.is_active.is_(True))
        ).scalar()
        or 0,
        "inactive": session.execute(
            sa.select(sa.func.count()).select_from(DimProduct).where(DimProduct.is_active.is_(False))
        ).scalar()
        or 0,
    }
