"""Health, readiness and meta endpoints (no authentication required)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.analytics import service as analytics_service
from app.api.deps import DbOptional
from app.api.schemas import HealthResponse
from app.core.config import settings
from app.core.db import ping
from app.core.features import feature_catalogue, feature_names
from app.core.logging import get_logger
from app.ingestion.base import list_sources
from app.models import table_count

log = get_logger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness + dependency health")
def health() -> HealthResponse:
    database = ping()
    sources = list_sources()
    return HealthResponse(
        status="ok" if database["connected"] else "degraded",
        version=settings.app_version,
        environment=settings.app_env,
        database=database,
        sources=[
            {
                "code": source["code"],
                "name": source["name"],
                "kind": source["kind"],
                "enabled": source["enabled"],
                "rate_limit_per_minute": source["rate_limit_per_minute"],
            }
            for source in sources
        ],
        timestamp=dt.datetime.now(dt.timezone.utc),
    )


@router.get("/health/ready", summary="Readiness probe")
def readiness() -> dict[str, Any]:
    database = ping()
    return {
        "ready": bool(database["connected"]),
        "checks": {
            "database": "pass" if database["connected"] else "fail",
            "schema": "pass" if (database.get("tables") or 0) >= table_count() else "fail",
            "views": "pass",
        },
        "database": database,
    }


@router.get("/meta", summary="API metadata, limits and feature catalogue")
def meta() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "timezone": settings.app_timezone,
        "active_database": settings.active_database,
        "dialect": settings.dialect_name,
        "tables": table_count(),
        "limits": {
            "max_page_size": 200,
            "default_page_size": 25,
            "max_query_rows": 5000,
            "pipeline_limit_per_source": settings.max_products_per_source,
            "dedupe_threshold": settings.dedupe_similarity_threshold,
        },
        "compliance": {
            "respect_robots_txt": settings.respect_robots_txt,
            "user_agent": settings.ingest_user_agent,
            "requests_per_minute": settings.requests_per_minute,
            "crawl_delay_fallback_seconds": settings.crawl_delay_fallback_seconds,
            "cache_enabled": settings.cache_enabled,
        },
        "features": feature_names(),
        "feature_groups": feature_catalogue()["total_groups"],
    }


@router.get("/meta/features", summary="Structured feature catalogue (groups, icons, features)")
def meta_features() -> dict[str, Any]:
    return feature_catalogue()


@router.get("/meta/tables", summary="Physical tables managed by the ORM")
def tables() -> dict[str, Any]:
    from app.models import TABLE_GROUPS, all_tables

    return {"tables": all_tables(), "groups": {key: list(value) for key, value in TABLE_GROUPS.items()}}


@router.get("/version", summary="Version string")
def version() -> dict[str, str]:
    return {"version": settings.app_version, "name": settings.app_name}


@router.get("/stats/tables", summary="Row counts per table")
def stats(session: DbOptional) -> dict[str, Any]:
    try:
        return {"counts": analytics_service.table_counts(session)}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/ping", include_in_schema=False)
def ping_endpoint() -> dict[str, str]:
    return {"pong": "ok"}


@router.get("/debug/db", include_in_schema=False)
def debug_db(session: DbOptional) -> dict[str, Any]:
    session.execute(text("SELECT 1"))
    bound = session.bind
    return {"ok": True, "dialect": bound.dialect.name if bound is not None else None}
