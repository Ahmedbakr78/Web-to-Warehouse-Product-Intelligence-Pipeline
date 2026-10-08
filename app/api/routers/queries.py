"""Read-only SQL console + query plan explorer (analyst/admin only)."""

from __future__ import annotations

import re
import time
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter

from app.analytics import service as analytics
from app.api.deps import CurrentUser, DbSession, QueryUser
from app.api.schemas import Message, QueryHistoryRead, QueryHistorySave, QueryRequest, QueryResponse
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/queries", tags=["query-lab"])

#: Tables that hold secrets and are never readable from the query lab, even
#: though the read-only validator would otherwise let a SELECT through.
FORBIDDEN_TABLES = ("app_user", "app_api_key", "app_session", "app_webhook")

#: Unsaved history kept per user; pinned snippets (`is_saved`) are exempt.
HISTORY_KEEP = 200


def _forbid_secrets(statement: str) -> None:
    from app.api.query_guard import _scan

    masked, _ = _scan(statement.lower())
    for table in FORBIDDEN_TABLES:
        if re.search(rf"\b{re.escape(table)}\b", masked):
            raise ValidationError(
                f"querying '{table}' is not allowed from the query lab",
                details={"forbidden": list(FORBIDDEN_TABLES)},
            )


def _bounded(statement: str, limit: int) -> tuple[str, dict[str, Any]]:
    """Enforce the row cap inside the SQL itself.

    The previous implementation fetched `limit + 1` rows client-side, which
    still made the database plan and materialise the unbounded result. Wrapping
    the statement pushes the cap into the engine. EXPLAIN plans describe a
    statement rather than returning its rows, so they run unwrapped.

    The newline before the closing paren is load-bearing: the editor appends
    ``-- reference: <table>`` comments, and without it the wrapper suffix
    would be swallowed by a trailing line comment.
    """
    from app.api.query_guard import is_explain

    if is_explain(statement):
        return statement, {}
    return (
        f"SELECT * FROM ({statement}\n) AS query_lab LIMIT :query_lab_limit",
        {"query_lab_limit": limit},
    )


def _record(
    session: DbSession, user: CurrentUser, sql: str, limit: int, row_count: int, duration: float, truncated: bool
) -> None:
    from app.models.app_users import AppQueryHistory

    session.add(
        AppQueryHistory(
            user_id=user.user_id,
            sql=sql,
            limit=limit,
            row_count=row_count,
            duration_ms=duration,
            truncated=truncated,
        )
    )
    session.flush()
    # Prune unsaved runs past the keep window; pinned snippets are never pruned.
    stale = (
        session.execute(
            sa.select(AppQueryHistory.history_id)
            .where(AppQueryHistory.user_id == user.user_id, AppQueryHistory.is_saved.is_(False))
            .order_by(AppQueryHistory.history_id.desc())
            .offset(HISTORY_KEEP)
        )
        .scalars()
        .all()
    )
    if stale:
        session.execute(sa.delete(AppQueryHistory).where(AppQueryHistory.history_id.in_(stale)))
        session.flush()


@router.post("/execute", response_model=QueryResponse, summary="Run a read-only SELECT")
def execute(payload: QueryRequest, session: DbSession, user: QueryUser) -> QueryResponse:
    from app.api.query_guard import clean_for_execution, validate_readonly

    # Defense in depth: the Pydantic model already validated, but re-check here
    # so direct calls can never bypass the guard.
    try:
        validate_readonly(payload.sql)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    _forbid_secrets(payload.sql)
    statement = clean_for_execution(payload.sql)
    if not statement:
        raise ValidationError("SQL statement is empty")
    sql, params = _bounded(statement, payload.limit)
    started = time.perf_counter()
    try:
        result = session.execute(sa.text(sql), params)
        columns = list(result.keys())
        rows = result.fetchmany(payload.limit + 1)
    except sa.exc.SQLAlchemyError as exc:
        # Syntax errors, unknown tables/columns and dialect complaints become a
        # 422 with the database message instead of a 500 internal_error, so the
        # editor can tell the user which name to fix in the schema browser.
        message = str(getattr(exc, "orig", exc) or exc).strip().splitlines()[0][:500]
        raise ValidationError(
            f"database refused the statement: {message}",
            details={"hint": "check table and column names against the schema browser"},
        ) from exc
    truncated = len(rows) > payload.limit
    rows = rows[: payload.limit]
    duration = round((time.perf_counter() - started) * 1000, 2)
    log.info("query lab user=%s rows=%d duration_ms=%s", user.user_id, len(rows), duration)
    _record(session, user, statement, payload.limit, len(rows), duration, truncated)
    return QueryResponse(
        columns=columns,
        rows=[[_jsonify(value) for value in row] for row in rows],
        row_count=len(rows),
        duration_ms=duration,
        truncated=truncated,
    )


@router.get("/history", response_model=list[QueryHistoryRead], summary="My query history and snippets")
def history(
    session: DbSession,
    user: CurrentUser,
    saved_only: bool = False,
    limit: int = 50,
) -> list[QueryHistoryRead]:
    from app.models.app_users import AppQueryHistory

    limit = max(1, min(limit, HISTORY_KEEP))
    conditions = [AppQueryHistory.user_id == user.user_id]
    if saved_only:
        conditions.append(AppQueryHistory.is_saved.is_(True))
    rows = (
        session.execute(
            sa.select(AppQueryHistory)
            .where(*conditions)
            .order_by(AppQueryHistory.is_saved.desc(), AppQueryHistory.history_id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [QueryHistoryRead.model_validate(row) for row in rows]


@router.post("/history/{history_id}/save", response_model=QueryHistoryRead, summary="Pin as a named snippet")
def save_snippet(history_id: int, payload: QueryHistorySave, session: DbSession, user: CurrentUser) -> QueryHistoryRead:
    from app.models.app_users import AppQueryHistory

    row = session.get(AppQueryHistory, history_id)
    if row is None or row.user_id != user.user_id:
        raise NotFoundError(f"query {history_id} not found")
    row.name = payload.name
    row.is_saved = True
    session.flush()
    return QueryHistoryRead.model_validate(row)


@router.delete("/history/{history_id}", response_model=Message, summary="Delete one history entry")
def delete_entry(history_id: int, session: DbSession, user: CurrentUser) -> Message:
    from app.models.app_users import AppQueryHistory

    row = session.get(AppQueryHistory, history_id)
    if row is None or row.user_id != user.user_id:
        raise NotFoundError(f"query {history_id} not found")
    session.delete(row)
    session.flush()
    return Message(message=f"Query {history_id} deleted")


@router.delete("/history", response_model=Message, summary="Clear unsaved history")
def clear_history(session: DbSession, user: CurrentUser) -> Message:
    from app.models.app_users import AppQueryHistory

    result = session.execute(
        sa.delete(AppQueryHistory).where(
            AppQueryHistory.user_id == user.user_id, AppQueryHistory.is_saved.is_(False)
        )
    )
    session.flush()
    return Message(message=f"Cleared {result.rowcount or 0} unsaved querie(s); snippets kept")


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
        {
            "title": "Top price drops (30 days)",
            "sql": "SELECT canonical_name, category_name, previous_price, new_price, change_pct\nFROM vw_price_changes\nWHERE ABS(change_pct) > 5 AND full_date >= CURRENT_DATE - 30\nORDER BY change_pct LIMIT 25;",
        },
        {
            "title": "Category price index",
            "sql": "SELECT category_name, full_date, avg_price_usd, price_stddev, distinct_products\nFROM vw_category_price_index\nORDER BY full_date DESC LIMIT 50;",
        },
        {
            "title": "New products vs internal catalog",
            "sql": "SELECT n.canonical_name, n.category_name, n.price_usd, c.catalog_name\nFROM vw_new_products n\nLEFT JOIN vw_catalog_reconciliation c ON c.product_id = n.product_id\nORDER BY n.first_seen_at DESC LIMIT 25;",
        },
        {
            "title": "Sources ranked by coverage",
            "sql": "SELECT source_code, products_seen, observations, avg_price_usd, success_rate_pct\nFROM vw_source_coverage ORDER BY observations DESC;",
        },
        {
            "title": "Data quality failures",
            "sql": "SELECT rule_code, rule_name, dimension, severity, status, message\nFROM dq_rule_result WHERE status <> 'pass' ORDER BY evaluated_at DESC LIMIT 50;",
        },
        {
            "title": "Cross-store price spread",
            "sql": "SELECT v.canonical_name, COUNT(DISTINCT v.source_code) AS stores,\n       ROUND(MIN(v.price_usd), 2) AS min_usd, ROUND(MAX(v.price_usd), 2) AS max_usd\nFROM vw_product_current v\nJOIN dim_product p ON p.product_id = v.product_id\nWHERE v.is_active AND v.price_usd IS NOT NULL\nGROUP BY p.fingerprint\nHAVING COUNT(DISTINCT v.source_code) > 1\nORDER BY max_usd - min_usd DESC LIMIT 25;",
        },
        {
            "title": "Catalogue price bands",
            "sql": "SELECT CASE WHEN price_usd IS NULL THEN 'no price' WHEN price_usd < 10 THEN 'under $10'\n            WHEN price_usd < 50 THEN '$10-$50' WHEN price_usd < 200 THEN '$50-$200'\n            WHEN price_usd < 1000 THEN '$200-$1k' ELSE 'over $1k' END AS band,\n       COUNT(*) AS listings\nFROM vw_product_current WHERE is_active GROUP BY band ORDER BY listings DESC;",
        },
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


__all__ = ["FORBIDDEN_TABLES", "HISTORY_KEEP"]
