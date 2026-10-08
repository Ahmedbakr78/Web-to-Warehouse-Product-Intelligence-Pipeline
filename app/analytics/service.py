"""Analytics service: every dashboard number is produced by a SQL query.

Functions return plain dictionaries so the REST layer can serialise them directly and
the CLI can pretty-print the same results.  All queries are dialect portable and use
the ``vw_*`` views defined in ``db/views.sql``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger

log = get_logger(__name__)


def _rows(session: Session, statement: Any, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = session.execute(statement, params or {})
    keys = list(result.keys())
    return [dict(zip(keys, row, strict=False)) for row in result.fetchall()]


def _scalar(
    session: Session, statement: Any, params: dict[str, Any] | None = None, default: Any = None
) -> Any:
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
    preparer = session.bind.dialect.identifier_preparer if session.bind else None
    quote_fn = preparer.quote if preparer is not None else (lambda name: f'"{name}"')
    for table in (
        "dim_product",
        "dim_category",
        "dim_source",
        "dim_currency",
        "dim_date",
        "fact_price_snapshot",
        "fact_catalog_snapshot",
        "chg_price_change",
        "chg_product_event",
        "agg_category_daily",
        "catalog_product",
        "etl_run",
        "dq_rule_result",
        "stg_raw_observation",
        "ingestion_http_log",
        "app_user",
    ):
        try:
            out[table] = session.execute(sa.text(f"SELECT COUNT(*) FROM {quote_fn(table)}")).scalar() or 0
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


def change_event_summary(session: Session, days: int = 30) -> dict[str, Any]:
    """Lifecycle event counters plus a price-change timeline for the KPI cards."""
    row = _one(
        session,
        sa.text(
            """
            SELECT COUNT(*) AS total_events,
                   SUM(CASE WHEN event_type = 'new' THEN 1 ELSE 0 END) AS new_products,
                   SUM(CASE WHEN event_type = 'removed' THEN 1 ELSE 0 END) AS removed_products,
                   SUM(CASE WHEN event_type = 'category_changed' THEN 1 ELSE 0 END) AS category_changes,
                   SUM(CASE WHEN event_type = 'recurring' THEN 1 ELSE 0 END) AS recurring
            FROM chg_product_event WHERE detected_at >= :since
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    )
    timeline = price_change_timeline(session, days=days)
    return {**row, "timeline": timeline}


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
        ),
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
        ),
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
        ),
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


def catalog_reconciliation(
    session: Session, run_id: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
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


def http_log(
    session: Session,
    limit: int = 100,
    source_code: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Outbound HTTP audit rows, newest first, optionally scoped to a run or source."""
    params: dict[str, Any] = {"limit": limit}
    filters: list[str] = []
    if source_code:
        filters.append("source_code = :source_code")
        params["source_code"] = source_code
    if run_id:
        filters.append("run_id = :run_id")
        params["run_id"] = run_id
    clause = f"WHERE {' AND '.join(filters)}" if filters else ""
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


def price_volatility(
    session: Session, limit: int = 20, min_observations: int = 3
) -> list[dict[str, Any]]:
    """Most volatile products: widest price range relative to their average."""
    return _rows(
        session,
        sa.text(
            """
            SELECT product_id, canonical_name, brand, category_name, source_code,
                   observations, avg_price_usd, min_price_usd, max_price_usd,
                   range_pct, price_stddev, changes_observed, last_observation_at
            FROM vw_price_volatility
            WHERE observations >= :min_observations
            -- Portable NULLS LAST: MySQL has no NULLS LAST syntax.
            ORDER BY range_pct IS NULL, range_pct DESC, price_stddev DESC
            LIMIT :limit
            """
        ),
        {"limit": limit, "min_observations": min_observations},
    )


def discount_leaders(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Deepest current discounts off list price."""
    return _rows(
        session,
        sa.text(
            """
            SELECT product_id, canonical_name, brand, category_name, source_code,
                   price, list_price, currency, price_usd, discount_pct,
                   savings_amount, availability, in_stock, last_seen_at
            FROM vw_discount_leaders
            ORDER BY discount_pct DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )


def rating_leaders(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Best-rated products, damped by vote count so one 5-star review cannot win."""
    return _rows(
        session,
        sa.text(
            """
            SELECT product_id, canonical_name, brand, category_name, source_code,
                   price_usd, rating, rating_count, damped_score,
                   availability, in_stock, observation_count, last_seen_at
            FROM vw_rating_leaders
            -- Portable NULLS LAST: products with a rating but no vote count
            -- (damped_score NULL) sink below genuinely top-rated ones.
            ORDER BY damped_score IS NULL, damped_score DESC, rating_count DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )


def list_views(session: Session) -> list[dict[str, Any]]:
    """Enumerate the analytical views available in the current database."""
    if session.bind is None:
        return []
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
    "price_volatility",
    "discount_leaders",
    "rating_leaders",
    "availability_summary",
    "category_tree",
    "change_event_summary",
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
    "compare_runs",
    "price_buckets",
    "cross_source_spread",
    "category_movers",
    "lifecycle_timeline",
    "price_anomalies",
    "source_overlap",
    "data_freshness",
    "inventory_risk",
    "currency_exposure",
    "best_value",
    "brand_momentum",
    "weekday_pattern",
]


# --------------------------------------------------------------------------------------
# Run comparison (diff two pipeline runs)
# --------------------------------------------------------------------------------------
RUN_METRIC_COLUMNS: tuple[str, ...] = (
    "records_extracted",
    "records_valid",
    "records_rejected",
    "records_inserted",
    "records_updated",
    "duplicates_merged",
    "new_products",
    "price_changes",
    "removed_products",
    "catalog_matched",
    "dq_passed",
    "dq_failed",
)


def compare_runs(
    session: Session,
    base_run_id: str,
    target_run_id: str,
    sample_limit: int = 25,
) -> dict[str, Any]:
    """Compare two ETL runs: metric deltas, DQ regressions and record-level movement.

    ``base`` is the earlier reference run, ``target`` the later one being judged.
    Returns an empty ``{}`` when either run is unknown so callers can surface 404s.
    """
    base = _one(session, sa.text("SELECT * FROM etl_run WHERE run_id = :rid"), {"rid": base_run_id})
    target = _one(session, sa.text("SELECT * FROM etl_run WHERE run_id = :rid"), {"rid": target_run_id})
    if not base or not target:
        return {}

    metrics: list[dict[str, Any]] = []
    for column in RUN_METRIC_COLUMNS:
        before = base.get(column) or 0
        after = target.get(column) or 0
        delta = after - before
        metrics.append(
            {
                "metric": column,
                "base": before,
                "target": after,
                "delta": delta,
                "delta_pct": round(delta / before * 100, 2) if before else None,
            }
        )

    base_score = base.get("dq_score")
    target_score = target.get("dq_score")

    base_dq = {
        row["rule_code"]: row["status"]
        for row in _rows(
            session,
            sa.text("SELECT rule_code, status FROM dq_rule_result WHERE run_id = :rid"),
            {"rid": base_run_id},
        )
    }
    target_dq = {
        row["rule_code"]: row["status"]
        for row in _rows(
            session,
            sa.text("SELECT rule_code, status FROM dq_rule_result WHERE run_id = :rid"),
            {"rid": target_run_id},
        )
    }
    regressions = sorted(
        code for code, status in target_dq.items() if status != "pass" and base_dq.get(code, "pass") == "pass"
    )
    fixes = sorted(
        code
        for code, status in target_dq.items()
        if status == "pass" and base_dq.get(code) not in (None, "pass")
    )

    def _snapshot_rows(run_id: str) -> list[dict[str, Any]]:
        """One row per product touched by a run: id, display name and USD price."""
        return _rows(
            session,
            sa.text(
                """
                SELECT p.product_id, p.canonical_name, f.price_usd
                FROM fact_price_snapshot f
                JOIN dim_product p ON p.product_id = f.product_id
                WHERE f.run_id = :rid
                """
            ),
            {"rid": run_id},
        )

    base_rows = _snapshot_rows(base_run_id)
    target_rows = _snapshot_rows(target_run_id)

    def _index(rows: list[dict[str, Any]]) -> tuple[dict[int, str], dict[int, float]]:
        names = {row["product_id"]: row["canonical_name"] for row in rows}
        prices = {row["product_id"]: float(row["price_usd"]) for row in rows if row["price_usd"] is not None}
        return names, prices

    base_names, base_prices = _index(base_rows)
    target_names, target_prices = _index(target_rows)

    added_ids = sorted(set(target_names) - set(base_names))
    dropped_ids = sorted(set(base_names) - set(target_names))
    added = [{"product_id": pid, "canonical_name": target_names[pid]} for pid in added_ids[:sample_limit]]
    dropped = [{"product_id": pid, "canonical_name": base_names[pid]} for pid in dropped_ids[:sample_limit]]

    price_moves: list[dict[str, Any]] = sorted(
        (
            {
                "product_id": pid,
                "canonical_name": target_names.get(pid) or base_names.get(pid),
                "base_price": round(base_prices[pid], 4),
                "target_price": round(target_prices[pid], 4),
                "delta": round(delta, 4),
                "delta_pct": (round(delta / base_prices[pid] * 100, 2) if base_prices[pid] else None),
            }
            for pid, delta in (
                (pid, target_prices[pid] - base_prices[pid])
                for pid in set(base_prices) & set(target_prices)
                if base_prices[pid] != target_prices[pid]
            )
        ),
        key=lambda item: abs(float(item["delta"])),
        reverse=True,
    )

    base_ms = base.get("duration_ms") or 0
    target_ms = target.get("duration_ms") or 0

    return {
        "base": _run_head(base),
        "target": _run_head(target),
        "metrics": metrics,
        "dq": {
            "base_score": base_score,
            "target_score": target_score,
            "score_delta": (
                round(target_score - base_score, 4)
                if base_score is not None and target_score is not None
                else None
            ),
            "regressions": regressions,
            "fixed": fixes,
        },
        "catalogue": {
            "added_count": len(added_ids),
            "dropped_count": len(dropped_ids),
            "added": added,
            "dropped": dropped,
            "truncated": len(added_ids) > sample_limit or len(dropped_ids) > sample_limit,
        },
        "prices": {
            "changed_count": len(price_moves),
            "moves": price_moves[:sample_limit],
            "truncated": len(price_moves) > sample_limit,
        },
        "performance": {
            "base_duration_ms": base_ms,
            "target_duration_ms": target_ms,
            "delta_ms": target_ms - base_ms,
            "delta_pct": round((target_ms - base_ms) / base_ms * 100, 2) if base_ms else None,
        },
    }


def price_buckets(session: Session) -> list[dict[str, Any]]:
    """Histogram of the live catalogue across fixed USD price bands.

    One row per band (plus an ``unknown`` row for priceless records), so the
    dashboard can draw a donut without binning client-side. The band order is
    produced by a repeated CASE rather than the alias, which keeps the query
    portable across PostgreSQL, MySQL and SQLite.
    """
    band = """
        CASE
            WHEN price_usd IS NULL THEN 'unknown'
            WHEN price_usd < 10 THEN 'under_10'
            WHEN price_usd < 50 THEN 'from_10_to_50'
            WHEN price_usd < 200 THEN 'from_50_to_200'
            WHEN price_usd < 1000 THEN 'from_200_to_1000'
            ELSE 'over_1000'
        END"""
    order = """
        CASE
            WHEN price_usd IS NULL THEN 5
            WHEN price_usd < 10 THEN 0
            WHEN price_usd < 50 THEN 1
            WHEN price_usd < 200 THEN 2
            WHEN price_usd < 1000 THEN 3
            ELSE 4
        END"""
    return _rows(
        session,
        sa.text(
            f"""
            SELECT {band} AS bucket,
                   COUNT(*) AS listings,
                   SUM(CASE WHEN in_stock THEN 1 ELSE 0 END) AS in_stock_count,
                   ROUND(CAST(AVG(rating) AS DECIMAL(24,6)), 2) AS avg_rating
            FROM vw_product_current
            WHERE is_active
            GROUP BY {band}
            ORDER BY MIN({order})
            """
        ),
    )


def cross_source_spread(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Products listed by two or more sources, ranked by price disagreement.

    Rows are grouped by the dedupe fingerprint, so the same product sold in
    several stores collapses to one line with min/max/average USD prices and a
    spread percent. Zero-average groups (free apps) are excluded because their
    spread is undefined.
    """
    return _rows(
        session,
        sa.text(
            """
            SELECT MIN(v.canonical_name) AS canonical_name,
                   MIN(v.brand) AS brand,
                   MIN(v.category_name) AS category_name,
                   COUNT(DISTINCT v.source_code) AS sources,
                   COUNT(*) AS listings,
                   ROUND(CAST(MIN(v.price_usd) AS DECIMAL(24,6)), 2) AS min_price_usd,
                   ROUND(CAST(MAX(v.price_usd) AS DECIMAL(24,6)), 2) AS max_price_usd,
                   ROUND(CAST(AVG(v.price_usd) AS DECIMAL(24,6)), 2) AS avg_price_usd,
                   ROUND(CAST((MAX(v.price_usd) - MIN(v.price_usd))
                              / NULLIF(AVG(v.price_usd), 0) * 100 AS DECIMAL(24,6)), 2) AS spread_pct
            FROM vw_product_current v
            JOIN dim_product p ON p.product_id = v.product_id
            WHERE v.is_active AND v.price_usd IS NOT NULL
            GROUP BY p.fingerprint
            HAVING COUNT(DISTINCT v.source_code) > 1 AND AVG(v.price_usd) > 0
            ORDER BY spread_pct DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )


def category_movers(session: Session, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
    """Categories ranked by average absolute price-change magnitude."""
    return _rows(
        session,
        sa.text(
            """
            SELECT c.name AS category_name,
                   COUNT(*) AS changes,
                   SUM(CASE WHEN pc.direction = 'increase' THEN 1 ELSE 0 END) AS increases,
                   SUM(CASE WHEN pc.direction = 'decrease' THEN 1 ELSE 0 END) AS decreases,
                   ROUND(CAST(AVG(ABS(pc.change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct,
                   ROUND(CAST(MAX(ABS(pc.change_pct)) AS DECIMAL(24,6)), 2) AS max_abs_change_pct
            FROM vw_price_changes pc
            JOIN dim_product p ON p.product_id = pc.product_id
            LEFT JOIN dim_category c ON c.category_id = p.category_id
            WHERE pc.full_date >= :since AND pc.change_pct IS NOT NULL
            GROUP BY c.name
            ORDER BY avg_abs_change_pct DESC
            LIMIT :limit
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days), "limit": limit},
    )


def lifecycle_timeline(session: Session, days: int = 90) -> list[dict[str, Any]]:
    """Daily lifecycle counts (new/removed/recategorised) plus price changes.

    Lifecycle events and price changes live in different tables, so both are
    aggregated per day and merged in Python over the union of observed dates.
    """
    events = _rows(
        session,
        sa.text(
            """
            SELECT d.full_date AS full_date,
                   SUM(CASE WHEN e.event_type = 'new' THEN 1 ELSE 0 END) AS new_products,
                   SUM(CASE WHEN e.event_type = 'removed' THEN 1 ELSE 0 END) AS removed_products,
                   SUM(CASE WHEN e.event_type = 'category_changed' THEN 1 ELSE 0 END) AS recategorised,
                   COUNT(*) AS total_events
            FROM chg_product_event e
            JOIN dim_date d ON d.date_id = e.date_id
            WHERE d.full_date >= :since
            GROUP BY d.full_date
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days)},
    )
    changes = _rows(
        session,
        sa.text(
            """
            SELECT d.full_date AS full_date, COUNT(*) AS price_changes
            FROM chg_price_change pc
            JOIN dim_date d ON d.date_id = pc.date_id
            WHERE d.full_date >= :since
            GROUP BY d.full_date
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days)},
    )
    by_date: dict[str, dict[str, Any]] = {}
    for row in events:
        by_date[str(row["full_date"])] = {
            "full_date": row["full_date"],
            "new_products": row["new_products"],
            "removed_products": row["removed_products"],
            "recategorised": row["recategorised"],
            "total_events": row["total_events"],
            "price_changes": 0,
        }
    for row in changes:
        key = str(row["full_date"])
        if key in by_date:
            by_date[key]["price_changes"] = row["price_changes"]
        else:
            by_date[key] = {
                "full_date": row["full_date"],
                "new_products": 0,
                "removed_products": 0,
                "recategorised": 0,
                "total_events": 0,
                "price_changes": row["price_changes"],
            }
    return [by_date[key] for key in sorted(by_date)]


def price_anomalies(
    session: Session, limit: int = 20, threshold_std: float = 2.0
) -> list[dict[str, Any]]:
    """Live listings priced far from their own category's going rate.

    The z-score is computed against the category mean/stddev derived inline,
    so no extra table is needed. The portable variance expression is the same
    one the category views use (SQLite has no STDDEV). Zero-variance
    categories are excluded because every z-score there is undefined.
    """
    return _rows(
        session,
        sa.text(
            """
            SELECT v.product_id, v.canonical_name, v.brand, v.category_name, v.source_code,
                   ROUND(CAST(v.price_usd AS DECIMAL(24,6)), 2) AS price_usd,
                   ROUND(CAST(cat.mean_price AS DECIMAL(24,6)), 2) AS category_mean_usd,
                   ROUND(CAST((v.price_usd - cat.mean_price) / cat.std_price AS DECIMAL(24,6)), 2) AS z_score
            FROM vw_product_current v
            JOIN (
                SELECT category_name,
                       AVG(price_usd) AS mean_price,
                       SQRT(CASE WHEN (AVG(price_usd) * AVG(price_usd) - AVG(price_usd * price_usd)) < 0
                                 THEN 0
                                 ELSE (AVG(price_usd) * AVG(price_usd) - AVG(price_usd * price_usd))
                            END) AS std_price
                FROM vw_product_current
                WHERE is_active AND price_usd IS NOT NULL AND category_name IS NOT NULL
                GROUP BY category_name
            ) cat ON cat.category_name = v.category_name
            WHERE v.is_active AND v.price_usd IS NOT NULL
              AND cat.std_price > 0
              AND ABS((v.price_usd - cat.mean_price) / cat.std_price) >= :threshold
            ORDER BY ABS((v.price_usd - cat.mean_price) / cat.std_price) DESC
            LIMIT :limit
            """
        ),
        {"threshold": threshold_std, "limit": limit},
    )


def source_overlap(session: Session) -> list[dict[str, Any]]:
    """Pairwise catalogue overlap between sources, via the dedupe fingerprint.

    One row per source pair that shares at least one product. The self-join
    uses a strict ``>`` on the codes so each unordered pair appears exactly
    once on every dialect.
    """
    return _rows(
        session,
        sa.text(
            """
            SELECT l.source_code AS source_a,
                   r.source_code AS source_b,
                   COUNT(*) AS shared_products
            FROM dim_product l
            JOIN dim_product r
              ON r.fingerprint = l.fingerprint
             AND r.source_code > l.source_code
            GROUP BY l.source_code, r.source_code
            HAVING COUNT(*) > 0
            ORDER BY shared_products DESC
            """
        ),
    )


def data_freshness(session: Session, stale_days: int = 7) -> list[dict[str, Any]]:
    """Per-source catalogue freshness: last sighting, stale share, product counts."""
    return _rows(
        session,
        sa.text(
            """
            SELECT p.source_code,
                   COUNT(*) AS products,
                   SUM(CASE WHEN p.is_active THEN 1 ELSE 0 END) AS active_products,
                   MAX(p.last_seen_at) AS last_seen_at,
                   SUM(CASE WHEN p.last_seen_at < :cutoff THEN 1 ELSE 0 END) AS stale_products,
                   ROUND(CAST(100.0 * SUM(CASE WHEN p.last_seen_at < :cutoff THEN 1 ELSE 0 END)
                              / NULLIF(COUNT(*), 0) AS DECIMAL(24,6)), 2) AS stale_pct
            FROM dim_product p
            GROUP BY p.source_code
            ORDER BY stale_pct DESC, products DESC
            """
        ),
        {"cutoff": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=stale_days)},
    )


def inventory_risk(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Categories under stock pressure: out-of-stock counts plus recent increases.

    Joins the availability rollup to the price-change feed so a category that
    is both hard to buy and getting more expensive surfaces first.
    """
    return _rows(
        session,
        sa.text(
            """
            SELECT a.category_name,
                   a.observations,
                   a.in_stock_count,
                   a.in_stock_pct,
                   a.out_of_stock_count,
                   COALESCE(m.price_increases, 0) AS price_increases,
                   m.avg_abs_change_pct AS avg_abs_change_pct
            FROM vw_availability_summary a
            LEFT JOIN (
                SELECT c.name AS category_name,
                       SUM(CASE WHEN pc.direction = 'increase' THEN 1 ELSE 0 END) AS price_increases,
                       ROUND(CAST(AVG(ABS(pc.change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct
                FROM vw_price_changes pc
                JOIN dim_product p ON p.product_id = pc.product_id
                LEFT JOIN dim_category c ON c.category_id = p.category_id
                WHERE pc.change_pct IS NOT NULL
                GROUP BY c.name
            ) m ON m.category_name = a.category_name
            ORDER BY a.out_of_stock_count DESC, COALESCE(m.price_increases, 0) DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )


def currency_exposure(session: Session) -> list[dict[str, Any]]:
    """Live catalogue mix by original listing currency.

    Shows where the warehouse's FX normalisation actually matters: how many
    listings arrive in each currency and their average USD price.
    """
    return _rows(
        session,
        sa.text(
            """
            SELECT currency,
                   COUNT(*) AS listings,
                   COUNT(DISTINCT source_code) AS sources,
                   SUM(CASE WHEN in_stock THEN 1 ELSE 0 END) AS in_stock_count,
                   ROUND(CAST(AVG(price_usd) AS DECIMAL(24,6)), 2) AS avg_price_usd
            FROM vw_product_current
            WHERE is_active
            GROUP BY currency
            ORDER BY listings DESC
            """
        ),
    )


def best_value(
    session: Session, limit: int = 20, min_rating: float = 4.0, min_votes: int = 10
) -> list[dict[str, Any]]:
    """Best value-for-money: highly rated listings ranked by rating per USD.

    Only listings with enough votes qualify, so a lone 5-star review cannot
    win. Free listings are excluded because their score is undefined.
    """
    return _rows(
        session,
        sa.text(
            """
            SELECT product_id, canonical_name, brand, category_name, source_code,
                   price_usd, rating, rating_count, availability,
                   ROUND(CAST(rating / NULLIF(price_usd, 0) AS DECIMAL(24,6)), 4) AS value_score
            FROM vw_product_current
            WHERE is_active AND price_usd IS NOT NULL AND price_usd > 0
              AND rating IS NOT NULL AND rating >= :min_rating
              AND rating_count IS NOT NULL AND rating_count >= :min_votes
            ORDER BY rating / NULLIF(price_usd, 0) DESC
            LIMIT :limit
            """
        ),
        {"min_rating": min_rating, "min_votes": min_votes, "limit": limit},
    )


def brand_momentum(session: Session, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
    """Brands ranked by average signed price change: winners first, losers last.

    Unlike the magnitude-based movers, the sign is kept, so this answers
    "which brands are getting more expensive" rather than "which move most".
    """
    return _rows(
        session,
        sa.text(
            """
            SELECT pc.brand AS brand,
                   COUNT(*) AS changes,
                   SUM(CASE WHEN pc.direction = 'increase' THEN 1 ELSE 0 END) AS increases,
                   SUM(CASE WHEN pc.direction = 'decrease' THEN 1 ELSE 0 END) AS decreases,
                   ROUND(CAST(AVG(pc.change_pct) AS DECIMAL(24,6)), 2) AS avg_change_pct,
                   ROUND(CAST(AVG(ABS(pc.change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct
            FROM vw_price_changes pc
            WHERE pc.full_date >= :since AND pc.change_pct IS NOT NULL
              AND pc.brand IS NOT NULL
            GROUP BY pc.brand
            ORDER BY avg_change_pct DESC
            LIMIT :limit
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days), "limit": limit},
    )


def weekday_pattern(session: Session, days: int = 90) -> list[dict[str, Any]]:
    """Price-change activity by weekday: which days move the market.

    Monday-first ordering is produced by a CASE on the day name, which keeps
    the query portable across PostgreSQL, MySQL and SQLite.
    """
    order = """
        CASE d.day_name
            WHEN 'Monday' THEN 0 WHEN 'Tuesday' THEN 1 WHEN 'Wednesday' THEN 2
            WHEN 'Thursday' THEN 3 WHEN 'Friday' THEN 4 WHEN 'Saturday' THEN 5
            WHEN 'Sunday' THEN 6 ELSE 7
        END"""
    return _rows(
        session,
        sa.text(
            f"""
            SELECT d.day_name AS day_name,
                   MAX(CASE WHEN d.is_weekend THEN 1 ELSE 0 END) AS is_weekend,
                   COUNT(*) AS changes,
                   SUM(CASE WHEN pc.direction = 'increase' THEN 1 ELSE 0 END) AS increases,
                   SUM(CASE WHEN pc.direction = 'decrease' THEN 1 ELSE 0 END) AS decreases,
                   ROUND(CAST(AVG(ABS(pc.change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct
            FROM chg_price_change pc
            JOIN dim_date d ON d.date_id = pc.date_id
            WHERE d.full_date >= :since AND pc.change_pct IS NOT NULL
            GROUP BY d.day_name
            ORDER BY MIN({order})
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days)},
    )


def _run_head(run: dict[str, Any]) -> dict[str, Any]:
    """Compact run header used by the comparison payload."""
    return {
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "trigger": run.get("trigger"),
        "target_database": run.get("target_database"),
        "dag_id": run.get("dag_id"),
        "task_id": run.get("task_id"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "duration_ms": run.get("duration_ms"),
        "dq_score": run.get("dq_score"),
    }
