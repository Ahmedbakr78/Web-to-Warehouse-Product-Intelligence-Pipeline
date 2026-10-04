"""Source registry endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ReadUser
from app.core.errors import SourceNotFoundError
from app.ingestion.base import get_source, get_source_class, list_sources
from app.ingestion.robots import get_robots_cache

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", summary="Registered sources with compliance metadata")
def sources(_user: ReadUser) -> list[dict[str, Any]]:
    return list_sources()


@router.get("/robots", summary="robots.txt decisions cached by the ingestion layer")
def robots(_user: ReadUser) -> dict[str, Any]:
    cache = get_robots_cache()
    return {"stats": dict(cache.stats), "user_agent": cache.user_agent, "ttl_seconds": cache.ttl_seconds}


@router.get("/{code}", summary="One source definition")
def source(code: str, _user: ReadUser) -> dict[str, Any]:
    try:
        return get_source_class(code)().health_check()
    except SourceNotFoundError:
        raise


@router.get("/{code}/preview", summary="Fetch a few raw records without loading them")
def preview(code: str, _user: ReadUser, limit: int = 5) -> dict[str, Any]:
    from app.ingestion.base import transform_product

    source = get_source(code)
    records = []
    try:
        for index, raw in enumerate(source.fetch(limit=limit)):
            if index >= limit:
                break
            record = transform_product(raw)
            records.append(
                {
                    "source_product_id": record.source_product_id,
                    "canonical_name": record.canonical_name,
                    "raw_name": record.raw_name,
                    "category": record.category,
                    "price": record.price,
                    "currency": record.currency,
                    "price_usd": record.price_usd,
                    "rating": record.rating,
                    "availability": record.availability,
                    "quality_flags": record.quality_flags,
                    "is_valid": record.is_valid,
                    "reject_reason": record.reject_reason,
                    "product_url": record.product_url,
                }
            )
    finally:
        source.close()
    return {
        "code": code,
        "requested": limit,
        "returned": len(records),
        "http_calls": source.http_calls,
        "errors": source.errors,
        "records": records,
    }
