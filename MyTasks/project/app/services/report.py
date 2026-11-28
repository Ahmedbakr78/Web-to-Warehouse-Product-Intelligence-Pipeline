"""Report templates.

A report is a declarative list of blocks (`tiles`, `table`, `bars`, `callout`, ...)
which the PDF renderer and the HTML preview both consume. Keeping the definition
separate from the rendering means a report can be shown in the browser and exported
to PDF from exactly the same description, and neither can drift from the other.

Five templates ship:

``executive_summary``
    The one a director reads: headline numbers, market pulse, data-quality posture.
``price_movements``
    The biggest price changes and what moved them, with a volatility view.
``data_quality``
    The 12 rules, their current verdicts, and the score trend.
``catalog_gaps``
    Where the retailer's own prices sit against the market, and what is missing.
``product``
    One product: history, forecast with its intervals, anomalies and price advice.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.analytics import forecast as forecast_engine
from app.analytics import service as analytics
from app.core.logging import get_logger

log = get_logger(__name__)

TEMPLATES: dict[str, dict[str, Any]] = {
    "executive_summary": {
        "title": "Executive summary",
        "subtitle": "Market position, data freshness and trustworthiness at a glance",
        "sections": ["headline", "changes", "availability", "sources", "quality"],
    },
    "price_movements": {
        "title": "Price movement report",
        "subtitle": "Largest movers, direction mix and per-category volatility",
        "sections": ["movers", "change_activity", "volatility", "notable_changes"],
    },
    "data_quality": {
        "title": "Data quality report",
        "subtitle": "Every rule, its current verdict and the score trend",
        "sections": ["quality_score", "rules", "failures", "source_coverage"],
    },
    "catalog_gaps": {
        "title": "Catalog reconciliation",
        "subtitle": "Our list prices against the market, and what we are missing",
        "sections": ["catalog_summary", "opportunities", "unmatched"],
    },
    "product": {
        "title": "Product report",
        "subtitle": "History, forecast, anomalies and pricing advice for one product",
        "sections": ["identity", "history", "forecast", "anomalies", "price_advice"],
        "requires_product": True,
    },
}

TEMPLATE_KEYS = tuple(TEMPLATES)


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "—"


def _num(value: Any, digits: int = 0) -> Any:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def template_list() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "title": spec["title"],
            "subtitle": spec["subtitle"],
            "sections": spec["sections"],
            "requires_product": spec.get("requires_product", False),
        }
        for key, spec in TEMPLATES.items()
    ]


# --------------------------------------------------------------------------------------
# Section builders. Each returns a list of blocks.
# --------------------------------------------------------------------------------------
def _headline(session: Session, days: int) -> list[dict[str, Any]]:
    kpi = analytics.kpi_summary(session, days=days)
    counts = kpi.get("counts", {})
    return [
        {
            "type": "tiles",
            "tiles": [
                {"label": "Products tracked", "value": counts.get("dim_product"), "hint": "deduplicated"},
                {
                    "label": "Price observations",
                    "value": counts.get("fact_price_snapshot"),
                    "hint": "one row per product per run",
                },
                {
                    "label": "Avg price",
                    "value": _num(kpi.get("avg_price"), 2),
                    "hint": "USD, latest",
                    "tone": "info",
                },
                {
                    "label": "Price changes",
                    "value": counts.get("chg_price_change"),
                    "hint": f"last {days} days",
                    "tone": "warning",
                },
                {
                    "label": "New products",
                    "value": counts.get("new_products"),
                    "hint": f"last {days} days",
                    "tone": "success",
                },
                {
                    "label": "Data quality",
                    "value": _num(kpi.get("dq_score"), 2),
                    "hint": "0-100, 12 rules",
                    "tone": "success" if (kpi.get("dq_score") or 0) >= 95 else "warning",
                },
            ],
        },
        {
            "type": "callout",
            "title": "What this report covers",
            "body": (
                f"{counts.get('dim_product', 0):,} products across "
                f"{counts.get('dim_category', 0):,} categories, from "
                f"{counts.get('dim_source', 0)} registered sources, with "
                f"{counts.get('chg_product_event', 0):,} lifecycle events recorded."
            ),
        },
    ]


def _changes(session: Session, days: int) -> list[dict[str, Any]]:
    summary = analytics.change_event_summary(session, days=days)
    return [
        {
            "type": "tiles",
            "tiles": [
                {"label": "New", "value": summary.get("new_products"), "tone": "success"},
                {"label": "Removed", "value": summary.get("removed_products"), "tone": "danger"},
                {"label": "Recategorised", "value": summary.get("category_changes"), "tone": "warning"},
                {"label": "Recurring", "value": summary.get("recurring")},
            ],
        },
        {
            "type": "table",
            "columns": [
                {"key": "full_date", "label": "Date"},
                {"key": "changes", "label": "Changes", "align": "right"},
                {"key": "increases", "label": "Up", "align": "right"},
                {"key": "decreases", "label": "Down", "align": "right"},
                {"key": "avg_abs_change_pct", "label": "Avg |change|", "align": "right"},
                {"key": "max_abs_change_pct", "label": "Max |change|", "align": "right"},
            ],
            "rows": analytics.price_change_timeline(session, days=days)[-21:],
        },
    ]


def _availability(session: Session) -> list[dict[str, Any]]:
    # `vw_availability_summary` is per category, not per availability state, so the
    # in-stock share is summed here rather than assuming a column that does not exist.
    rows = analytics.availability_summary(session)
    total = sum(int(row.get("observations") or 0) for row in rows)
    in_stock = sum(int(row.get("in_stock_count") or 0) for row in rows)
    out_of_stock = sum(int(row.get("out_of_stock_count") or 0) for row in rows)
    share = round(in_stock / total * 100, 2) if total else None

    tiles = [
        {"label": "Observations", "value": total},
        {
            "label": "In stock",
            "value": in_stock,
            "tone": "success",
            "hint": f"{share}% of all" if share else None,
        },
        {"label": "Out of stock", "value": out_of_stock, "tone": "warning"},
        {"label": "Categories", "value": len(rows)},
    ]
    blocks: list[dict[str, Any]] = [{"type": "tiles", "tiles": tiles}]

    if rows:
        blocks.append(
            {
                "type": "table",
                "columns": [
                    {"key": "category_name", "label": "Category"},
                    {"key": "observations", "label": "Obs", "align": "right"},
                    {"key": "in_stock_count", "label": "In stock", "align": "right"},
                    {"key": "out_of_stock_count", "label": "Out", "align": "right"},
                    {"key": "in_stock_pct", "label": "In stock %", "align": "right"},
                ],
                "rows": sorted(rows, key=lambda row: float(row.get("in_stock_pct") or 0), reverse=True)[:15],
            }
        )
    return blocks


def _sources(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "type": "table",
            "columns": [
                {"key": "source_code", "label": "Source"},
                {"key": "source_name", "label": "Name"},
                {"key": "kind", "label": "Kind"},
                {"key": "products_seen", "label": "Products", "align": "right"},
                {"key": "success_rate_pct", "label": "Success", "align": "right"},
                {
                    "key": "enabled",
                    "label": "State",
                    "badge": lambda value: "active" if value else "disabled",
                },
            ],
            "rows": analytics.source_health(session),
        }
    ]


def _quality_score(session: Session) -> list[dict[str, Any]]:
    from app.etl.dq import latest_report

    report = latest_report(session)
    summary = report.get("summary", {}) if report else {}
    tiles = [
        {"label": "Quality score", "value": _num(summary.get("score"), 2), "tone": "success"},
        {"label": "Rules passed", "value": summary.get("passed")},
        {"label": "Warnings", "value": summary.get("warned"), "tone": "warning"},
        {"label": "Failures", "value": summary.get("failed"), "tone": "danger"},
    ]
    trend = [
        {"label": str(row.get("full_date"))[5:], "value": _num(row.get("score"), 2)}
        for row in _quality_trend(session)
        if row.get("score") is not None
    ]
    return [{"type": "tiles", "tiles": tiles}, {"type": "bars", "items": trend[-30:]}]


def _quality_trend(session: Session, days: int = 90) -> list[dict[str, Any]]:
    """Average rule pass rate per day.

    `dq_rule_result` has no date column, so the day is cast from `evaluated_at`. The
    cast is spelled `CAST(x AS DATE)` because that is the one form all three
    supported dialects accept.
    """
    rows = session.execute(
        sa.text(
            """
            SELECT CAST(r.evaluated_at AS DATE) AS full_date,
                   ROUND(CAST(AVG(r.pass_rate_pct) AS DECIMAL(24,4)), 2) AS score
            FROM dq_rule_result r
            WHERE r.evaluated_at >= :since
            GROUP BY CAST(r.evaluated_at AS DATE)
            ORDER BY full_date
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    ).mappings()
    return [dict(row) for row in rows]


def _latest_rule_results(session: Session) -> list[dict[str, Any]]:
    """Rule results from the newest run.

    Read from `dq_rule_result` rather than `vw_quality_latest`: that view is a
    per-*run* rollup (score and rule counts), not the per-rule detail a catalogue
    report needs.
    """
    rows = session.execute(
        sa.text(
            """
            SELECT r.rule_code, r.rule_name, r.dimension, r.severity, r.status,
                   r.pass_rate_pct, r.records_checked, r.records_failed, r.message,
                   r.evaluated_at
            FROM dq_rule_result r
            JOIN etl_run e ON e.run_id = r.run_id
            WHERE r.run_id = (
                SELECT run_id FROM etl_run
                WHERE status IN ('success', 'partial')
                ORDER BY started_at DESC
                LIMIT 1
            )
            ORDER BY CASE r.severity WHEN 'critical' THEN 0 WHEN 'error' THEN 1
                                      WHEN 'warning' THEN 2 ELSE 3 END,
                     r.rule_code
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _rules(session: Session) -> list[dict[str, Any]]:
    rows = _latest_rule_results(session)
    return [
        {
            "type": "table",
            "columns": [
                {"key": "rule_code", "label": "Code"},
                {"key": "rule_name", "label": "Rule"},
                {"key": "dimension", "label": "Dimension"},
                {"key": "severity", "label": "Severity"},
                {
                    "key": "status",
                    "label": "Verdict",
                    "badge": lambda value: {
                        "pass": "pass",
                        "warn": "warning",
                        "fail": "fail",
                    }.get(str(value), str(value)),
                },
                {"key": "pass_rate_pct", "label": "Pass %", "align": "right"},
            ],
            "rows": rows,
        }
    ]


def _failures(session: Session) -> list[dict[str, Any]]:
    rows = [row for row in _latest_rule_results(session) if row.get("status") != "pass"]
    if not rows:
        return [
            {
                "type": "callout",
                "title": "No outstanding quality issues",
                "body": "All 12 rules passed on the most recent evaluation.",
            }
        ]
    return [
        {
            "type": "table",
            "columns": [
                {"key": "rule_code", "label": "Code"},
                {"key": "rule_name", "label": "Rule"},
                {"key": "severity", "label": "Severity"},
                {"key": "message", "label": "Finding"},
            ],
            "rows": rows,
        }
    ]


def _movers(session: Session, limit: int = 15) -> list[dict[str, Any]]:
    rows = analytics.top_movers(session, limit=limit)
    return [
        {
            "type": "table",
            "columns": [
                {"key": "canonical_name", "label": "Product"},
                {"key": "category_name", "label": "Category"},
                {"key": "previous_price", "label": "From", "align": "right"},
                {"key": "new_price", "label": "To", "align": "right"},
                {"key": "change_pct", "label": "Change", "align": "right"},
            ],
            "rows": rows,
        }
    ]


def _change_activity(session: Session, days: int) -> list[dict[str, Any]]:
    timeline = analytics.price_change_timeline(session, days=days)
    return [
        {
            "type": "bars",
            "items": [
                {"label": str(row.get("full_date"))[5:], "value": row.get("changes") or 0}
                for row in timeline[-30:]
            ],
        }
    ]


def _volatility(session: Session, days: int = 60) -> list[dict[str, Any]]:
    """Price dispersion per category.

    The standard deviation is computed in Python rather than with `STDDEV()`: SQLite
    has no such aggregate, and the other two dialects disagree on its return type.
    Pulling the values and calling `statistics.pstdev` keeps one implementation working
    on all three.
    """
    import statistics

    rows = session.execute(
        sa.text(
            """
            SELECT category_name, price_usd
            FROM vw_price_history
            WHERE full_date >= :since AND price_usd IS NOT NULL
            GROUP BY category_name, full_date, price_usd
            ORDER BY category_name
            """
        ),
        {"since": dt.date.today() - dt.timedelta(days=days)},
    )

    buckets: dict[str, list[float]] = {}
    for row in rows:
        buckets.setdefault(str(row[0] or "Uncategorised"), []).append(float(row[1]))

    summary: list[dict[str, Any]] = [
        {
            "category_name": category,
            "observations": len(values),
            "stddev": round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0,
            "spread": round(max(values) - min(values), 2),
        }
        for category, values in buckets.items()
        if len(values) >= 10
    ]
    summary.sort(key=lambda row: float(row["stddev"]), reverse=True)

    return [
        {
            "type": "bars",
            "items": [
                {"label": str(row["category_name"])[:30], "value": float(row["stddev"])}
                for row in summary[:12]
            ],
            "caption": "Population standard deviation of daily price, per category",
        },
        {
            "type": "table",
            "columns": [
                {"key": "category_name", "label": "Category"},
                {"key": "observations", "label": "Obs", "align": "right"},
                {"key": "stddev", "label": "Std dev", "align": "right"},
                {"key": "spread", "label": "Range", "align": "right"},
            ],
            "rows": summary,
        },
    ]


def _notable_changes(session: Session, days: int) -> list[dict[str, Any]]:
    return [
        {
            "type": "table",
            "columns": [
                {"key": "full_date", "label": "Date"},
                {"key": "canonical_name", "label": "Product"},
                {"key": "previous_price", "label": "From", "align": "right"},
                {"key": "new_price", "label": "To", "align": "right"},
                {"key": "change_pct", "label": "Change", "align": "right"},
                {"key": "direction", "label": "Direction"},
            ],
            "rows": analytics.price_change_report(session, days=days, limit=25),
        }
    ]


def _catalog_summary(session: Session) -> list[dict[str, Any]]:
    """Roll the reconciliation rows up into counts.

    `analytics.catalog_reconciliation` returns rows, not a summary object, so the
    aggregation happens here rather than pretending the service already did it.
    """
    rows = analytics.catalog_reconciliation(session, limit=5_000)
    matched = sum(1 for row in rows if row.get("match_status") == "matched")
    mismatches = sum(1 for row in rows if row.get("price_mismatch"))
    tiles = [
        {"label": "Catalog SKUs", "value": analytics.table_counts(session).get("catalog_product")},
        {"label": "Matched", "value": matched, "tone": "success"},
        {"label": "Unmatched", "value": len(rows) - matched, "tone": "warning"},
        {"label": "Price mismatches", "value": mismatches, "tone": "danger"},
    ]
    blocks: list[dict[str, Any]] = [{"type": "tiles", "tiles": tiles}]
    if rows:
        match_rates = [float(row["match_score"]) for row in rows if row.get("match_score") is not None]
        if match_rates:
            blocks.append(
                {
                    "type": "text",
                    "body": (
                        f"Mean match confidence {sum(match_rates) / len(match_rates):.1%} across "
                        f"{len(match_rates):,} matched SKU(s). A fuzzy match below the configured "
                        "threshold is reported as unmatched rather than forced."
                    ),
                }
            )
    return blocks


def _opportunities(session: Session, limit: int = 15) -> list[dict[str, Any]]:
    rows = analytics.catalog_reconciliation(session, limit=limit)
    priced = [row for row in rows if row.get("price_gap_pct") is not None]
    priced.sort(
        key=lambda row: abs(float(row["price_gap_pct"])),  # type: ignore[arg-type]
        reverse=True,
    )
    return [
        {
            # Bars take a number, not a formatted string: `_bars` divides by the peak,
            # so passing "-98.0%" would raise on float().
            "type": "bars",
            "items": [
                {
                    "label": str(row.get("canonical_name") or row.get("catalog_name"))[:38],
                    "value": round(float(row["price_gap_pct"]), 2),
                    "suffix": "%",
                }
                for row in priced[:12]
            ],
            "caption": "Largest gaps between our list price and the market, in percent",
        },
        {
            "type": "table",
            "columns": [
                {"key": "catalog_sku", "label": "SKU"},
                {"key": "catalog_name", "label": "Our product"},
                {"key": "scraped_name", "label": "Market product"},
                {"key": "catalog_price", "label": "Ours", "align": "right"},
                {"key": "scraped_price_usd", "label": "Market", "align": "right"},
                {"key": "price_gap_pct", "label": "Gap", "align": "right"},
            ],
            "rows": priced,
        },
    ]


def _unmatched(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = [
        row
        for row in analytics.catalog_reconciliation(session, limit=limit * 2)
        if row.get("match_status") != "matched"
    ]
    return [
        {
            "type": "table",
            "columns": [
                {"key": "catalog_sku", "label": "SKU"},
                {"key": "catalog_name", "label": "Our product"},
                {"key": "catalog_price", "label": "Price", "align": "right"},
                {"key": "match_status", "label": "Status"},
            ],
            "rows": rows[:limit],
        }
    ]


def _identity(session: Session, product_id: int) -> list[dict[str, Any]]:
    detail = analytics.product_detail(session, product_id)
    if not detail:
        return [{"type": "callout", "title": "Product not found", "body": f"No product {product_id}."}]
    return [
        {
            "type": "tiles",
            "tiles": [
                {"label": "Product", "value": (detail.get("product") or {}).get("canonical_name")},
                {"label": "Category", "value": (detail.get("product") or {}).get("category_name")},
                {"label": "Current price", "value": _num((detail.get("product") or {}).get("price_usd"), 2)},
                {"label": "Observations", "value": (detail.get("product") or {}).get("observation_count")},
            ],
        }
    ]


def _history(session: Session, product_id: int, limit: int = 60) -> list[dict[str, Any]]:
    rows = analytics.price_history(session, product_id, limit=limit)
    return [
        {
            "type": "bars",
            "items": [
                {"label": str(row.get("full_date"))[5:], "value": _num(row.get("price_usd"), 2)}
                for row in rows
            ],
        }
    ]


def _forecast_block(session: Session, product_id: int, horizon: int) -> list[dict[str, Any]]:
    result = forecast_engine.forecast_product(session, product_id, horizon=horizon)
    payload = result.as_dict()
    blocks: list[dict[str, Any]] = [
        {
            "type": "tiles",
            "tiles": [
                {"label": "Model", "value": payload["model"]},
                {"label": "Observations", "value": payload["observations"]},
                {
                    "label": "Backtest MAPE",
                    "value": _num(payload.get("mape_pct"), 2),
                    "hint": "holdout, not fit",
                    "tone": "success",
                },
                {"label": "Trend / yr", "value": _pct(payload.get("trend_pct_per_year"))},
            ],
        }
    ]
    if payload.get("reason"):
        blocks.append({"type": "callout", "title": "No forecast", "body": str(payload["reason"])})
    else:
        blocks.append({"type": "forecast", "points": payload["points"]})
    return blocks


def _anomaly_block(session: Session, product_id: int) -> list[dict[str, Any]]:
    found = forecast_engine.anomalies_for_product(session, product_id)
    if not found:
        return [
            {
                "type": "callout",
                "title": "No anomalies detected",
                "body": "Every observed price sits within 3.5 robust deviations of its local median.",
            }
        ]
    return [
        {
            "type": "table",
            "columns": [
                {"key": "when", "label": "Date"},
                {"key": "value", "label": "Observed", "align": "right"},
                {"key": "expected", "label": "Expected", "align": "right"},
                {"key": "score", "label": "Score", "align": "right"},
                {"key": "direction", "label": "Direction"},
                {"key": "severity", "label": "Severity"},
            ],
            "rows": [
                {
                    "when": item.when,
                    "value": round(item.value, 2),
                    "expected": round(item.expected, 2),
                    "score": round(item.score, 2),
                    "direction": item.direction,
                    "severity": item.severity,
                }
                for item in found
            ],
        }
    ]


def _price_advice(session: Session, product_id: int, horizon: int) -> list[dict[str, Any]]:
    points = forecast_engine.load_series(session, product_id)
    if len(points) < 3:
        return [
            {"type": "callout", "title": "Not enough history", "body": "At least 3 observations are needed."}
        ]
    values = [point.value for point in points]
    fitted = forecast_engine.damped_holt_winters(values, horizon)
    prediction = forecast_engine.predict_price(values, fitted.values)
    return [
        {
            "type": "tiles",
            "tiles": [
                {"label": "Current", "value": _num(prediction.current_price, 2)},
                {"label": "Recommended", "value": _num(prediction.recommended_price, 2), "tone": "info"},
                {"label": "Change", "value": _pct(prediction.change_pct)},
                {"label": "Confidence", "value": _num(prediction.confidence, 2)},
            ],
        },
        {"type": "callout", "title": "How this was derived", "body": " · ".join(prediction.notes)},
    ]


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------
#: Section key -> builder. Each builder returns a list of blocks.
_SectionBuilder = Callable[..., list[dict[str, Any]]]

_BUILDERS: dict[str, _SectionBuilder] = {
    "headline": _headline,
    "changes": _changes,
    "availability": _availability,
    "sources": _sources,
    "quality": _quality_score,
    "quality_score": _quality_score,
    "rules": _rules,
    "failures": _failures,
    "movers": _movers,
    "change_activity": _change_activity,
    "volatility": _volatility,
    "notable_changes": _notable_changes,
    "source_coverage": _sources,
    "catalog_summary": _catalog_summary,
    "opportunities": _opportunities,
    "unmatched": _unmatched,
}

#: Human-readable headings, so a report reads as a document rather than a data dump.
_SECTION_TITLES = {
    "headline": "Headline numbers",
    "changes": "Change summary",
    "availability": "Availability mix",
    "sources": "Source coverage",
    "source_coverage": "Source coverage",
    "quality": "Data quality score",
    "quality_score": "Data quality score",
    "rules": "Rule catalogue",
    "failures": "Outstanding issues",
    "movers": "Largest movers",
    "change_activity": "Change activity",
    "volatility": "Price volatility by category",
    "notable_changes": "Recent notable changes",
    "catalog_summary": "Reconciliation summary",
    "opportunities": "Pricing opportunities",
    "unmatched": "Unmatched catalog SKUs",
}

_PRODUCT_BUILDERS: dict[str, _SectionBuilder] = {
    "identity": _identity,
    "history": _history,
    "forecast": _forecast_block,
    "anomalies": _anomaly_block,
    "price_advice": _price_advice,
}

_PRODUCT_SECTION_TITLES = {
    "identity": "Product",
    "history": "Price history",
    "forecast": "Forecast",
    "anomalies": "Anomalies",
    "price_advice": "Pricing advice",
}


def build_report(
    session: Session,
    template: str = "executive_summary",
    *,
    days: int = 30,
    horizon: int = 14,
    product_id: int | None = None,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Build a report as `{title, subtitle, blocks, generated_at, template}`."""
    spec = TEMPLATES.get(template)
    if spec is None:
        raise ValueError(f"unknown template '{template}'; available: {', '.join(TEMPLATE_KEYS)}")

    requested = sections or list(spec["sections"])
    blocks: list[dict[str, Any]] = []
    titles = _SECTION_TITLES if not spec.get("requires_product") else _PRODUCT_SECTION_TITLES
    builders = _BUILDERS if not spec.get("requires_product") else _PRODUCT_BUILDERS

    for section in requested:
        builder = builders.get(section)
        if builder is None:
            log.warning("report section '%s' has no builder; skipping", section)
            continue
        try:
            if section in _PRODUCT_BUILDERS:
                if product_id is None:
                    continue
                # Only the forward-looking sections need the horizon.
                if section in {"forecast", "price_advice"}:
                    produced = builder(session, product_id, horizon)
                else:
                    produced = builder(session, product_id)
            elif section in {"changes", "change_activity", "notable_changes", "headline"}:
                produced = builder(session, days)
            else:
                produced = builder(session)
        except Exception as exc:  # noqa: BLE001 - one bad section must not lose the report
            log.warning("report section '%s' failed: %s", section, exc)
            blocks.append(
                {
                    "type": "callout",
                    "title": f"Section unavailable: {section}",
                    "body": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        blocks.append({"type": "heading", "title": titles.get(section, section.replace("_", " ").title())})
        blocks.extend(produced)

    product = None
    if spec.get("requires_product") and product_id is not None:
        row = (
            session.execute(
                sa.text("SELECT canonical_name FROM vw_product_current WHERE product_id = :pid"),
                {"pid": product_id},
            )
            .mappings()
            .first()
        )
        product = row["canonical_name"] if row else f"#{product_id}"

    title = spec["title"]
    if product:
        title = f"{product} - {spec['title']}"

    return {
        "template": template,
        "title": title,
        "subtitle": spec["subtitle"],
        "sections": requested,
        "blocks": blocks,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "days": days,
        "horizon": horizon,
        "product_id": product_id,
    }


def render_report(report: dict[str, Any]) -> str:
    """Render a report to a standalone HTML document."""
    from app.services.pdf import render_blocks

    scope = f"last {report.get('days', 30)} days"
    if report.get("product_id"):
        scope = f"product {report['product_id']}"
    footer = (
        f"Template '{report['template']}' · scope: {scope} · "
        "every figure is read live from the analytical views"
    )
    return render_blocks(report["title"], report["subtitle"], report["blocks"], footer=footer)


def render_report_pdf(report: dict[str, Any]) -> bytes:
    from app.services.pdf import to_pdf

    return to_pdf(render_report(report))


def render_report_csv(report: dict[str, Any]) -> str:
    """Flatten a built report to CSV.

    Two shapes share the file. Scalar facts (tiles, bars, callouts, prose,
    forecast points) form a `section, kind, label, value` frame at the top;
    every `table` block is then appended as a real CSV sub-table behind a `#`
    separator line carrying the section title. Readers that choke on the
    separators can drop every line starting with `#`.
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "kind", "label", "value"])
    tables: list[tuple[str, list[str], list[list[Any]]]] = []
    section = report.get("title", "")

    for block in report.get("blocks", []):
        kind = block.get("type")
        if kind == "heading":
            section = str(block.get("title") or section)
        elif kind == "tiles":
            for tile in block.get("tiles", []):
                writer.writerow([section, "metric", tile.get("label"), _csv_cell(tile.get("value"))])
        elif kind == "bars":
            for item in block.get("items", []):
                writer.writerow([section, "bar", item.get("label"), _csv_cell(item.get("value"))])
        elif kind == "callout":
            writer.writerow([section, "note", block.get("title"), block.get("body")])
        elif kind == "text":
            writer.writerow([section, "text", "", block.get("body")])
        elif kind == "forecast":
            for point in block.get("points", []):
                if isinstance(point, dict):
                    label = point.get("date") or point.get("period") or point.get("label") or ""
                    value = point.get("value", point.get("price", ""))
                else:
                    label, value = "", point
                writer.writerow([section, "forecast", label, _csv_cell(value)])
        elif kind == "table":
            columns = block.get("columns", [])
            labels = [str(column.get("label", column.get("key", ""))) for column in columns]
            keys = [str(column.get("key", "")) for column in columns]
            rows = [
                [_csv_cell(row.get(key) if isinstance(row, dict) else row) for key in keys]
                for row in block.get("rows", [])
            ]
            tables.append((section, labels, rows))

    for section_title, labels, rows in tables:
        output.write(f"# table: {section_title}\n")
        table_writer = csv.writer(output)
        if labels:
            table_writer.writerow(labels)
        table_writer.writerows(rows)
    return output.getvalue()


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return ""
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value


__all__ = [
    "TEMPLATE_KEYS",
    "TEMPLATES",
    "build_report",
    "render_report",
    "render_report_csv",
    "render_report_pdf",
    "template_list",
]
