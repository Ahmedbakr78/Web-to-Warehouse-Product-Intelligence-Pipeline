"""Read-only SQL console + query plan explorer (analyst/admin only)."""

from __future__ import annotations

import time
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.analytics import service as analytics
from app.api.deps import DbSession, QueryUser
from app.api.schemas import QueryRequest, QueryResponse
from app.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/queries", tags=["query-lab"])


@router.post("/execute", response_model=QueryResponse, summary="Run a read-only SELECT")
def execute(payload: QueryRequest, session: DbSession, _user: QueryUser) -> QueryResponse:
    started = time.perf_counter()
    statement = payload.sql.strip().rstrip(";")
    result = session.execute(sa.text(statement))
    columns = list(result.keys())
    rows = result.fetchmany(payload.limit + 1)
    truncated = len(rows) > payload.limit
    rows = rows[: payload.limit]
    duration = round((time.perf_counter() - started) * 1000, 2)
    return QueryResponse(
        columns=columns,
        rows=[[_jsonify(value) for value in row] for row in rows],
        row_count=len(rows),
        duration_ms=duration,
        truncated=truncated,
    )


@router.get("/views", summary="Analytical views available for querying")
def views(session: DbSession, _user: QueryUser) -> list[dict[str, Any]]:
    return analytics.list_views(session)


@router.get("/tables", summary="Physical tables available for querying")
def tables(_user: QueryUser) -> dict[str, Any]:
    from app.models import TABLE_GROUPS, all_tables

    return {"tables": all_tables(), "groups": {key: list(value) for key, value in TABLE_GROUPS.items()}}


@router.get("/examples", summary="Starter queries shown in the UI")
def examples(_user: QueryUser) -> list[dict[str, str]]:
    return [
        {"title": "Top price drops (30 days)",
         "sql": "SELECT canonical_name, category_name, previous_price, new_price, change_pct\nFROM vw_price_changes\nWHERE ABS(change_pct) > 5 AND full_date >= CURRENT_DATE - 30\nORDER BY change_pct LIMIT 25;"},
        {"title": "Category price index",
         "sql": "SELECT category_name, full_date, avg_price_usd, price_stddev, distinct_products\nFROM vw_category_price_index\nORDER BY full_date DESC LIMIT 50;"},
        {"title": "New products vs internal catalog",
         "sql": "SELECT n.canonical_name, n.category_name, n.price_usd, c.catalog_name\nFROM vw_new_products n\nLEFT JOIN vw_catalog_reconciliation c ON c.product_id = n.product_id\nORDER BY n.first_seen_at DESC LIMIT 25;"},
        {"title": "Sources ranked by coverage",
         "sql": "SELECT source_code, products_seen, observations, avg_price_usd, success_rate_pct\nFROM vw_source_coverage ORDER BY observations DESC;"},
        {"title": "Data quality failures",
         "sql": "SELECT rule_code, rule_name, dimension, severity, status, message\nFROM dq_rule_result WHERE status <> 'pass' ORDER BY evaluated_at DESC LIMIT 50;"},
    ]


def _jsonify(value: Any) -> Any:
    import datetime as dt
    import decimal
    import uuid

    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    return value
