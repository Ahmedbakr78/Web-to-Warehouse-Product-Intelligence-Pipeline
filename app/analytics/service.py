"""Analytics service: every dashboard number is produced by a SQL query.

Functions return plain dictionaries so the REST layer can serialise them directly and
the CLI can pretty-print the same results.  All queries are dialect portable and use
the ``vw_*`` views defined in ``db/views.sql``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Base

log = get_logger(__name__)


def _rows(session: Session, statement: Any, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = session.execute(statement, params or {})
    keys = list(result.keys())
    return [dict(zip(keys, row, strict=False)) for row in result.fetchall()]


def _scalar(session: Session, statement: Any, params: dict[str, Any] | None = None, default: Any = None) -> Any:
    try:
        return session.execute(statement, params or {}).scalar()
    except Exception as exc:  # pragma: no cover - missing view/table
        log.debug("scalar query failed: %s", exc)
        return default


def _one(session: Session, statement: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = _rows(session, statement, params)
    return rows[0] if rows else {}


def table_counts(session: Session) -> dict[str, int]:
    """Row counts for the main tables (used by the health endpoint and the CLI)."""
    out: dict[str, int] = {}
    quote = session.bind.dialect.identifier_preparer.quote if session.bind else '"{}"'
    for table in (
        "dim_product", "dim_category", "dim_source", "dim_currency", "dim_date",
        "fact_price_snapshot", "fact_catalog_snapshot", "chg_price_change",
        "chg_product_event", "agg_category_daily", "catalog_product", "etl_run",
        "dq_rule_result", "stg_raw_observation", "ingestion_http_log", "app_user",
    ):
        try:
            out[table] = session.execute(sa.text(f"SELECT COUNT(*) FROM {quote(table)}")).scalar() or 0
        except Exception:
            out[table] = 0
    return out


# --------------------------------------------------------------------------------------
# KPI / dashboard
# --------------------------------------------------------------------------------------
def kpi_summary(session: Session, days: int = 30) -> dict[str, Any]:
    """Headline numbers for the dashboard cards."""
    counts = table_counts(session)
    latest = _one(
        session,
        sa.text(
            """
            SELECT COUNT(*) AS products,
                   COUNT(DISTINCT source_code) AS sources,
                   ROUND(CAST(AVG(price_usd) AS DECIMAL(24,6)), 2) AS avg_price,
                   ROUND(CAST(MIN(price_usd) AS DECIMAL(24,6)), 2) AS min_price,
                   ROUND(CAST(MAX(price_usd) AS DECIMAL(24,6)), 2) AS max_price,
                   ROUND(CAST(AVG(rating) AS DECIMAL(24,6)), 2) AS avg_rating,
                   SUM(CASE WHEN in_stock THEN 1 ELSE 0 END) AS in_stock_count,
                   MAX(captured_at) AS last_observation_at
            FROM fact_price_snapshot
            WHERE captured_at >= :since
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    )
    changes = _one(
        session,
        sa.text(
            """
            SELECT COUNT(*) AS total_changes,
                   SUM(CASE WHEN direction = 'decrease' THEN 1 ELSE 0 END) AS decreases,
                   SUM(CASE WHEN direction = 'increase' THEN 1 ELSE 0 END) AS increases,
                   SUM(CASE WHEN is_significant THEN 1 ELSE 0 END) AS significant,
                   ROUND(CAST(AVG(ABS(change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct,
                   ROUND(CAST(MAX(ABS(change_pct)) AS DECIMAL(24,6)), 2) AS max_abs_change_pct
            FROM chg_price_change
            WHERE detected_at >= :since
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    )
    events = _rows(
        session,
        sa.text(
            """
            SELECT event_type, COUNT(*) AS count
            FROM chg_product_event
            WHERE detected_at >= :since
            GROUP BY event_type
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    )
    quality = _one(
        session,
        sa.text(
            """
            SELECT run_id, rules_passed, rules_warned, rules_failed, rules_total, dq_score
            FROM vw_quality_latest
            ORDER BY started_at DESC
            """
        ),
    )
    catalog = _one(
        session,
        sa.text(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN match_status = 'matched' THEN 1 ELSE 0 END) AS matched,
                   SUM(CASE WHEN is_price_mismatch THEN 1 ELSE 0 END) AS price_mismatches
            FROM fact_catalog_snapshot
            WHERE matched_at >= :since
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    )
    return {
        "window_days": days,
        "counts": counts,
        "latest": latest,
        "changes": changes,
        "events": {row["event_type"]: row["count"] for row in events},
        "quality": quality,
        "catalog": catalog,
        "generated_at": dt.datetime.now(dt.timezone.utc),
    }


def daily_trend(session: Session, days: int = 90) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT full_date, date_id, products_observed, observations, avg_price_usd, avg_rating, in_stock_pct
            FROM vw_daily_kpis
            WHERE full_date >= :since
            ORDER BY full_date
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days)},
    )


def price_change_timeline(session: Session, days: int = 90) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT full_date,
                   COUNT(*) AS changes,
                   SUM(CASE WHEN direction = 'increase' THEN 1 ELSE 0 END) AS increases,
                   SUM(CASE WHEN direction = 'decrease' THEN 1 ELSE 0 END) AS decreases,
                   ROUND(CAST(AVG(ABS(change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct,
                   ROUND(CAST(MAX(ABS(change_pct)) AS DECIMAL(24,6)), 2) AS max_abs_change_pct
            FROM vw_price_changes
            WHERE full_date >= :since
            GROUP BY full_date
            ORDER BY full_date
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days)},
    )


def top_movers(session: Session, limit: int = 20, direction: str | None = None) -> list[dict[str, Any]]:
    clause = "WHERE is_significant"
    params: dict[str, Any] = {"limit": limit}
    if direction in {"increase", "decrease"}:
        clause += " AND direction = :direction"
        params["direction"] = direction
    return _rows(
        session,
        sa.text(
            f"""
            SELECT product_id, canonical_name, category_name, source_code, full_date,
                   previous_price, new_price, change_abs, change_pct, direction, magnitude_band
            FROM vw_top_movers
            {clause}
            ORDER BY ABS(change_pct) DESC
            LIMIT :limit
            """
        ),
        params,
    )


def category_breakdown(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT a.category_id,
                   c.name AS category_name,
                   SUM(a.product_count) AS observations,
                   ROUND(CAST(AVG(a.avg_price) AS DECIMAL(24,6)), 2) AS avg_price,
                   ROUND(CAST(MIN(a.min_price) AS DECIMAL(24,6)), 2) AS min_price,
                   ROUND(CAST(MAX(a.max_price) AS DECIMAL(24,6)), 2) AS max_price,
                   ROUND(CAST(AVG(a.avg_rating) AS DECIMAL(24,6)), 2) AS avg_rating,
                   SUM(a.new_product_count) AS new_products,
                   SUM(a.price_change_count) AS price_changes
            FROM agg_category_daily a
            JOIN dim_category c ON c.category_id = a.category_id
            GROUP BY a.category_id, c.name
            ORDER BY observations DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )


def brand_leaderboard(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT brand, category_name, product_count, avg_price_usd, avg_rating,
                   in_stock_observations, last_seen_at
            FROM vw_brand_summary
            ORDER BY product_count DESC, avg_price_usd DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )


def source_health(session: Session) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT source_code, source_name, kind, enabled, rate_limit_per_minute,
                   products_seen, observations, avg_price_usd, avg_rating,
                   last_observation_at, success_rate_pct, avg_duration_seconds
            FROM vw_source_coverage
            ORDER BY observations DESC
            """
        )
    )


def availability_summary(session: Session) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT category_name, observations, in_stock_count, in_stock_pct, out_of_stock_count
            FROM vw_availability_summary
            ORDER BY observations DESC
            LIMIT 20
            """
        )
    )


def category_tree(session: Session) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT category_id, name, slug, level, path, parent_id, product_count,
                   active_products, avg_price_usd
            FROM vw_category_tree
            ORDER BY level, path
            """
        )
    )


def new_products(session: Session, days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT product_id, canonical_name, brand, category_name, source_code,
                   price, price_usd, currency, rating, availability, first_seen_at
            FROM vw_new_products
            WHERE first_seen_at >= :since
            ORDER BY first_seen_at DESC
            LIMIT :limit
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days), "limit": limit},
    )


def removed_products(session: Session, days: int = 90, limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT product_id, canonical_name, brand, category_name, source_code,
                   days_missing, removed_date, last_known_price_usd, last_known_rating
            FROM vw_removed_products
            WHERE detected_at >= :since
            ORDER BY detected_at DESC
            LIMIT :limit
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days), "limit": limit},
    )


def category_changes(session: Session, days: int = 90, limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT event_id, product_id, canonical_name, source_code,
                   old_category, new_category, change_date
            FROM vw_category_changes
            WHERE detected_at >= :since
            ORDER BY detected_at DESC
            LIMIT :limit
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days), "limit": limit},
    )


def catalog_reconciliation(session: Session, run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    clause = ""
    if run_id:
        clause = "WHERE run_id = :run_id"
        params["run_id"] = run_id
    return _rows(
        session,
        sa.text(
            f"""
            SELECT match_id, run_id, catalog_sku, catalog_name, catalog_brand, catalog_category,
                   catalog_price, supplier, product_id, scraped_name, scraped_brand,
                   scraped_category, scraped_price_usd, price_gap_abs, price_gap_pct,
                   match_status, match_strategy, similarity_score, category_match,
                   brand_match, is_price_mismatch, matched_at
            FROM vw_catalog_reconciliation
            {clause}
            ORDER BY ABS(COALESCE(price_gap_pct, 0)) DESC
            LIMIT :limit
            """
        ),
        params,
    )


def price_history(session: Session, product_id: int, limit: int = 500) -> list[dict[str, Any]]:
    return _rows(
        session,
        sa.text(
            """
            SELECT snapshot_id, product_id, source_code, full_date, captured_at,
                   price, price_usd, currency, rating, availability,
                   is_first_sighting, price_change_abs, price_change_pct
            FROM vw_price_history
            WHERE product_id = :product_id
            ORDER BY captured_at
            LIMIT :limit
            """
        ),
        {"product_id": product_id, "limit": limit},
    )


def product_detail(session: Session, product_id: int) -> dict[str, Any]:
    product = _one(
        session,
        sa.text("SELECT * FROM vw_product_index WHERE product_id = :pid"),
        {"pid": product_id},
    )
    if not product:
        return {}
    product["changes"] = _rows(
        session,
        sa.text(
            """
            SELECT change_id, full_date, source_code, previous_price, new_price,
                   change_abs, change_pct, direction, magnitude_band
            FROM vw_price_changes
            WHERE product_id = :pid
            ORDER BY detected_at DESC
            LIMIT 25
            """
        ),
        {"pid": product_id},
    )
    product["events"] = _rows(
        session,
        sa.text(
            """
            SELECT event_type, source_code, full_date, old_value, new_value, severity, detected_at
            FROM vw_product_events
            WHERE product_id = :pid
            ORDER BY detected_at DESC
            LIMIT 25
            """
        ),
        {"pid": product_id},
    )
    product["catalog"] = _rows(
        session,
        sa.text(
            """
            SELECT catalog_sku, catalog_name, catalog_price, price_gap_abs, price_gap_pct,
                   match_status, match_strategy, similarity_score
            FROM vw_catalog_reconciliation
            WHERE product_id = :pid
            LIMIT 5
            """
        ),
        {"pid": product_id},
    )
    product["source_snapshot"] = _one(
        session,
        sa.text(
            """
            SELECT source_code, source_product_id, match_strategy, match_score, extra
            FROM dim_product WHERE product_id = :pid
            """
        ),
        {"pid": product_id},
    )
    return product


def pipeline_runs(session: Session, limit: int = 25) -> list[dict[str, Any]]:
    """Run history. ``run_trigger`` is renamed to ``trigger`` in Python because the
    literal word is reserved in MySQL 8.4 and cannot be used as a SQL alias."""
    rows = _rows(
        session,
        sa.text(
            """
            SELECT run_id, status, run_trigger, target_database, started_at, finished_at, duration_ms,
                   records_extracted, records_valid, records_rejected, records_inserted,
                   records_updated, duplicates_merged, new_products, price_changes,
                   removed_products, catalog_matched, dq_score, yield_pct, error_message
            FROM vw_pipeline_health
            ORDER BY started_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(row) | {"trigger": row["run_trigger"]} for row in rows or []]


def run_detail(session: Session, run_id: str) -> dict[str, Any]:
    run = _one(session, sa.text("SELECT * FROM etl_run WHERE run_id = :run_id"), {"run_id": run_id})
    if not run:
        return {}
    run["dq"] = _rows(
        session,
        sa.text(
            """
            SELECT rule_code, rule_name, dimension, severity, status, observed_value,
                   expected_value, records_checked, records_failed, message, evaluated_at
            FROM dq_rule_result WHERE run_id = :run_id ORDER BY rule_code
            """
        ),
        {"run_id": run_id},
    )
    run["http"] = _rows(
        session,
        sa.text(
            """
            SELECT source_code, host, status_code, ROUND(CAST(AVG(elapsed_ms) AS DECIMAL(24,6)), 1) AS avg_ms,
                   SUM(response_bytes) AS bytes, SUM(CASE WHEN NOT robots_allowed THEN 1 ELSE 0 END) AS blocked,
                   SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) AS cached,
                   COUNT(*) AS requests
            FROM ingestion_http_log WHERE run_id = :run_id
            GROUP BY source_code, host, status_code
            ORDER BY requests DESC
            """
        ),
        {"run_id": run_id},
    )
    run["reconciliation"] = _rows(
        session,
        sa.text(
            """
            SELECT match_status, COUNT(*) AS count,
                   SUM(CASE WHEN is_price_mismatch THEN 1 ELSE 0 END) AS price_mismatches,
                   ROUND(CAST(AVG(similarity_score) AS DECIMAL(24,6)), 4) AS avg_similarity
            FROM fact_catalog_snapshot WHERE run_id = :run_id GROUP BY match_status
            """
        ),
        {"run_id": run_id},
    )
    run["stage_timings"] = _one(
        session,
        sa.text(
            """
            SELECT dq_score,
                   (SELECT COUNT(*) FROM fact_price_snapshot WHERE run_id = :run_id) AS snapshots
            FROM etl_run WHERE run_id = :run_id
            """
        ),
        {"run_id": run_id},
    )
    return run


def price_change_report(session: Session, days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    """SQL deliverable: price changes with magnitude bands."""
    return _rows(
        session,
        sa.text(
            """
            SELECT pc.full_date, pc.canonical_name, pc.brand, pc.category_name, pc.source_code,
                   pc.previous_price, pc.new_price, pc.change_abs, pc.change_pct,
                   pc.direction, pc.magnitude_band, pc.is_significant, pc.detected_at
            FROM vw_price_changes pc
            WHERE pc.full_date >= :since
            ORDER BY ABS(pc.change_pct) DESC
            LIMIT :limit
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days), "limit": limit},
    )


def category_drift_report(session: Session, days: int = 90) -> list[dict[str, Any]]:
    """SQL deliverable: which categories gained/lost products."""
    return _rows(
        session,
        sa.text(
            """
            SELECT c.name AS category_name,
                   COUNT(DISTINCT CASE WHEN e.event_type = 'new' THEN e.product_id END) AS products_added,
                   COUNT(DISTINCT CASE WHEN e.event_type = 'removed' THEN e.product_id END) AS products_removed,
                   COUNT(DISTINCT CASE WHEN e.event_type = 'category_changed' THEN e.product_id END) AS products_recategorised,
                   COUNT(DISTINCT CASE WHEN e.event_type = 'new' THEN e.product_id END)
                     - COUNT(DISTINCT CASE WHEN e.event_type = 'removed' THEN e.product_id END) AS net_change
            FROM dim_category c
            LEFT JOIN dim_product p ON p.category_id = c.category_id
            LEFT JOIN chg_product_event e ON e.product_id = p.product_id AND e.detected_at >= :since
            GROUP BY c.name
            ORDER BY net_change DESC, products_added DESC
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    )


def compliance_report(session: Session, days: int = 7) -> dict[str, Any]:
    """Evidence that the pipeline respected robots.txt and rate limits."""
    return _one(
        session,
        sa.text(
            """
            SELECT COUNT(*) AS requests,
                   SUM(CASE WHEN NOT robots_allowed THEN 1 ELSE 0 END) AS blocked_requests,
                   SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) AS cached_requests,
                   SUM(CASE WHEN retry_count > 0 THEN 1 ELSE 0 END) AS retried_requests,
                   SUM(response_bytes) AS total_bytes,
                   ROUND(CAST(AVG(elapsed_ms) AS DECIMAL(24,6)), 1) AS avg_elapsed_ms,
                   ROUND(CAST(MAX(elapsed_ms) AS DECIMAL(24,6)), 1) AS max_elapsed_ms,
                   COUNT(DISTINCT host) AS hosts
            FROM ingestion_http_log
            WHERE requested_at >= :since
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    )


def http_log(session: Session, limit: int = 100, source_code: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    clause = ""
    if source_code:
        clause = "WHERE source_code = :source_code"
        params["source_code"] = source_code
    return _rows(
        session,
        sa.text(
            f"""
            SELECT log_id, run_id, source_code, method, url, host, status_code, elapsed_ms,
                   response_bytes, robots_allowed, robots_rule, from_cache, retry_count, error, requested_at
            FROM vw_http_audit
            {clause}
            ORDER BY requested_at DESC
            LIMIT :limit
            """
        ),
        params,
    )


def query_explain(session: Session, view_name: str) -> list[dict[str, Any]]:
    """Show the plan of a view (dialect-aware) - used by the Query Lab screen."""
    safe = view_name if view_name.replace("_", "").isalnum() else ""
    if not safe:
        return []
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    try:
        if dialect == "postgresql":
            statement = sa.text(f'EXPLAIN (FORMAT JSON) SELECT * FROM "{safe}" LIMIT 5')
        elif dialect == "mysql":
            statement = sa.text(f"EXPLAIN SELECT * FROM `{safe}` LIMIT 5")
        else:
            statement = sa.text(f'EXPLAIN QUERY PLAN SELECT * FROM "{safe}" LIMIT 5')
        return _rows(session, statement)
    except Exception as exc:  # pragma: no cover - informational
        log.debug("explain failed for %s: %s", safe, exc)
        return []


def list_views(session: Session) -> list[dict[str, Any]]:
    """Enumerate the analytical views available in the current database."""
    inspector = sa.inspect(session.bind)
    try:
        views = inspector.get_view_names()
    except Exception:  # pragma: no cover
        views = []
    return [{"name": name} for name in sorted(views)]


__all__ = [
    "table_counts",
    "kpi_summary",
    "daily_trend",
    "price_change_timeline",
    "top_movers",
    "category_breakdown",
    "brand_leaderboard",
    "source_health",
    "availability_summary",
    "category_tree",
    "new_products",
    "removed_products",
    "category_changes",
    "catalog_reconciliation",
    "price_history",
    "product_detail",
    "pipeline_runs",
    "run_detail",
    "price_change_report",
    "category_drift_report",
    "compliance_report",
    "http_log",
    "query_explain",
    "list_views",
]