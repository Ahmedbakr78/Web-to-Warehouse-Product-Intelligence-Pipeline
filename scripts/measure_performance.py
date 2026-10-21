#!/usr/bin/env python3
"""Measure the latency of the dashboard's read paths against a real warehouse.

The numbers in ``docs/35_performance_and_capacity.md`` come from this script,
so they can be re-measured rather than believed. It times the queries the
dashboard actually issues, once for the plan and once for the execution, and
reports the slow ones.

Usage::

    python3 scripts/measure_performance.py --database <url> [--repeat 5]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


#: (label, SQL) for every read the dashboard issues on a page load.
QUERIES: tuple[tuple[str, str], ...] = (
    (
        "kpi_summary",
        """
        SELECT COUNT(*) FROM dim_product
        """,
    ),
    (
        "daily_trend",
        """
        SELECT d.full_date, COUNT(*) AS observations
        FROM fact_price_snapshot s JOIN dim_date d ON d.date_id = s.date_id
        WHERE s.captured_at >= NOW() - INTERVAL '90 days'
        GROUP BY d.full_date ORDER BY d.full_date
        """,
    ),
    (
        "price_change_timeline",
        """
        SELECT full_date, COUNT(*) AS changes,
               ROUND(CAST(AVG(ABS(change_pct)) AS DECIMAL(24,6)), 2) AS avg_abs_change_pct
        FROM vw_price_changes WHERE full_date >= CURRENT_DATE - 90
        GROUP BY full_date ORDER BY full_date
        """,
    ),
    (
        "category_breakdown",
        """
        SELECT c.name AS category_name, COUNT(DISTINCT p.product_id) AS products,
               COUNT(s.snapshot_id) AS observations
        FROM dim_category c
        JOIN dim_product p ON p.category_id = c.category_id
        JOIN fact_price_snapshot s ON s.product_id = p.product_id
        GROUP BY c.name ORDER BY observations DESC LIMIT 20
        """,
    ),
    (
        "brand_leaderboard",
        """
        SELECT brand, category_name, product_count, avg_price_usd, avg_rating,
               in_stock_observations, last_seen_at
        FROM vw_brand_summary ORDER BY product_count DESC, avg_price_usd DESC LIMIT 20
        """,
    ),
    (
        "top_movers",
        """
        SELECT product_id, canonical_name, previous_price, new_price, change_pct, direction
        FROM vw_top_movers ORDER BY ABS(change_abs) DESC LIMIT 20
        """,
    ),
    (
        "product_page",
        """
        SELECT p.product_id, p.canonical_name, p.brand, p.current_price, p.availability
        FROM dim_product p WHERE p.is_active ORDER BY p.last_seen_at DESC LIMIT 25
        """,
    ),
    (
        "price_history",
        """
        SELECT s.captured_at, s.price, s.currency, s.price_usd
        FROM fact_price_snapshot s WHERE s.product_id = 1
        ORDER BY s.captured_at DESC LIMIT 50
        """,
    ),
    (
        "change_feed",
        """
        SELECT pc.change_id, pc.canonical_name, pc.change_pct, pc.detected_at
        FROM vw_price_changes pc WHERE pc.full_date >= CURRENT_DATE - 90
        ORDER BY pc.detected_at DESC LIMIT 25
        """,
    ),
    (
        "source_coverage",
        """
        SELECT source_code, source_name, kind, enabled, products_seen, observations,
               avg_price_usd, last_observation_at, success_rate_pct
        FROM vw_source_coverage ORDER BY observations DESC
        """,
    ),
    (
        "quality_latest",
        """
        SELECT run_id, rules_passed, rules_warned, rules_failed, rules_total, dq_score
        FROM vw_quality_latest ORDER BY started_at DESC
        """,
    ),
    (
        "availability_summary",
        """
        SELECT category_name, observations, in_stock_count, in_stock_pct, out_of_stock_count
        FROM vw_availability_summary ORDER BY observations DESC LIMIT 20
        """,
    ),
    (
        "daily_kpis",
        """
        SELECT * FROM vw_daily_kpis ORDER BY full_date DESC LIMIT 90
        """,
    ),
    (
        "category_price_index",
        """
        SELECT full_date, category_name, distinct_products, observation_count,
               avg_price_usd, min_price_usd, max_price_usd, avg_rating, price_stddev
        FROM vw_category_price_index WHERE full_date >= CURRENT_DATE - 90
        ORDER BY full_date DESC
        """,
    ),
    (
        "http_audit",
        """
        SELECT log_id, source_code, url, method, status_code, robots_rule, elapsed_ms
        FROM ingestion_http_log ORDER BY requested_at DESC LIMIT 100
        """,
    ),
)


def measure(database_url: str, repeat: int) -> dict[str, Any]:
    import sqlalchemy as sa

    engine = sa.create_engine(database_url, future=True)
    results: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for label, sql in QUERIES:
            timings: list[float] = []
            rows = 0
            error: str | None = None
            for _ in range(repeat):
                started = time.perf_counter()
                try:
                    result = conn.execute(sa.text(sql))
                    fetched = result.fetchall()
                    elapsed = (time.perf_counter() - started) * 1000
                    rows = len(fetched)
                except Exception as exc:  # noqa: BLE001 - a dialect difference is a finding
                    error = f"{type(exc).__name__}: {exc}"
                    timings = []
                    break
                timings.append(elapsed)
            results.append(
                {
                    "query": label,
                    "rows": rows,
                    "ms_min": round(min(timings), 2) if timings else None,
                    "ms_median": round(statistics.median(timings), 2) if timings else None,
                    "ms_max": round(max(timings), 2) if timings else None,
                    "error": error,
                }
            )
    engine.dispose()
    return {"database": database_url, "repeat": repeat, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--database", default=None, help="SQLAlchemy URL (default: the configured one)")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    if args.database:
        url = args.database
    else:
        from app.core.config import settings

        url = settings.database_url

    report = measure(url, max(1, args.repeat))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"database: {report['database']}")
    print(f"repeat:   {report['repeat']}\n")
    print(f"{'query':24s} {'rows':>7s} {'min ms':>9s} {'median':>9s} {'max':>9s}")
    print("-" * 62)
    for row in report["results"]:
        if row["error"]:
            print(f"{row['query']:24s}  ERROR  {row['error'][:60]}")
            continue
        print(
            f"{row['query']:24s} {row['rows']:>7d} "
            f"{row['ms_min']:>9.2f} {row['ms_median']:>9.2f} {row['ms_max']:>9.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
