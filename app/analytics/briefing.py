"""Morning briefing: turn warehouse signals into a prioritized action list.

The briefing is deliberately a *composition* layer rather than new SQL: every
number comes from an existing, individually tested analytical service. That
keeps the definitions in one place (a price drop on the dashboard is the same
price drop here) while giving the UI one lightweight endpoint to render.

Each insight is a small, serialisable dictionary with a severity, an icon hint,
a human sentence and a deep link back into the screen where the user can act.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from app.analytics import service as analytics

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "—"
    if abs(number) >= 1000:
        return f"${number:,.0f}"
    return f"${number:,.2f}"


def _pct(value: Any, digits: int = 1) -> str:
    number = _num(value)
    if number is None:
        return "—"
    return f"{number:+.{digits}f}%"


def _insight(
    *,
    key: str,
    kind: str,
    severity: str,
    title: str,
    detail: str,
    metric: str,
    icon: str,
    link: str,
    action: str,
    delta: float | None = None,
) -> dict[str, Any]:
    return {
        "id": key,
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        "metric": metric,
        "delta": delta,
        "icon": icon,
        "link": link,
        "action": action,
    }


def _drop_insights(movers: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in movers[:limit]:
        change = _num(row.get("change_pct"))
        if change is None:
            continue
        items.append(
            _insight(
                key=f"drop-{row.get('product_id')}",
                kind="opportunity",
                severity="high" if abs(change) >= 20 else "medium",
                title=str(row.get("canonical_name") or "Product"),
                detail=(
                    f"{row.get('category_name') or 'Uncategorised'} · "
                    f"{_money(row.get('previous_price'))} → {_money(row.get('new_price'))} "
                    f"on {row.get('source_code') or 'source'}"
                ),
                metric=_pct(change),
                delta=change,
                icon="trending-down",
                link=f"/products/{row.get('product_id')}",
                action="Review the new price",
            )
        )
    return items


def _rise_insights(movers: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in movers[:limit]:
        change = _num(row.get("change_pct"))
        if change is None:
            continue
        items.append(
            _insight(
                key=f"rise-{row.get('product_id')}",
                kind="risk",
                severity="high" if change >= 20 else "medium",
                title=str(row.get("canonical_name") or "Product"),
                detail=(
                    f"{row.get('category_name') or 'Uncategorised'} · "
                    f"{_money(row.get('previous_price'))} → {_money(row.get('new_price'))} "
                    f"on {row.get('source_code') or 'source'}"
                ),
                metric=_pct(change),
                delta=change,
                icon="trending-up",
                link=f"/products/{row.get('product_id')}",
                action="Check margin exposure",
            )
        )
    return items


def _category_signals(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows[:limit]:
        avg = _num(row.get("avg_abs_change_pct"))
        if avg is None:
            continue
        increases = int(row.get("increases") or 0)
        decreases = int(row.get("decreases") or 0)
        direction = "increases" if increases > decreases else "decreases"
        items.append(
            _insight(
                key=f"category-{row.get('category_name')}",
                kind="category",
                severity="medium" if avg >= 8 else "low",
                title=str(row.get("category_name") or "Uncategorised"),
                detail=(
                    f"{increases} increases · {decreases} decreases · "
                    f"{int(row.get('changes') or 0)} moves in the window"
                ),
                metric=f"{avg:.1f}% avg",
                delta=avg if direction == "increases" else -avg,
                icon="activity",
                link="/changes",
                action="Open category feed",
            )
        )
    return items


def _catalog_insights(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if row.get("match_status") != "matched":
            continue
        gap = _num(row.get("price_gap_pct"))
        if gap is None or abs(gap) < 5:
            continue
        gap_abs = _num(row.get("price_gap_abs"))
        gap_label = f"{gap:+.1f}%"
        if gap < 0:
            detail = (
                f"Market price {_money(row.get('scraped_price_usd'))} is below the internal "
                f"catalog at {_money(row.get('catalog_price'))} (gap {_money(gap_abs)})"
            )
            action = "Consider matching the market"
            severity = "medium"
            kind = "opportunity"
            icon = "tag"
        else:
            detail = (
                f"Market price {_money(row.get('scraped_price_usd'))} is above the internal "
                f"catalog at {_money(row.get('catalog_price'))} (gap {_money(gap_abs)})"
            )
            action = "Check competitor positioning"
            severity = "low"
            kind = "catalog"
            icon = "compare"
        items.append(
            _insight(
                key=f"catalog-{row.get('catalog_sku')}",
                kind=kind,
                severity=severity,
                title=str(row.get("catalog_name") or row.get("scraped_name") or "Catalog SKU"),
                detail=detail,
                metric=gap_label,
                delta=gap,
                icon=icon,
                link="/catalog",
                action=action,
            )
        )
        if len(items) >= limit:
            break
    return items


def _freshness_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    healthy = [row for row in rows if (_num(row.get("stale_pct")) or 0) < 25]
    stale = [row for row in rows if (_num(row.get("stale_pct")) or 0) >= 50]
    return {
        "sources": len(rows),
        "healthy_sources": len(healthy),
        "stale_sources": len(stale),
        "stale": [
            {
                "source_code": row.get("source_code"),
                "products": int(row.get("products") or 0),
                "stale_pct": _num(row.get("stale_pct")),
                "last_seen_at": row.get("last_seen_at"),
            }
            for row in stale[:6]
        ],
    }


def build_briefing(session: Session, days: int = 30, limit: int = 6) -> dict[str, Any]:
    """Assemble the executive briefing for the last ``days`` days."""
    limit = max(1, min(limit, 20))
    kpi = analytics.kpi_summary(session, days=days)
    latest = kpi.get("latest") or {}
    changes = kpi.get("changes") or {}
    events = kpi.get("events") or {}
    quality = kpi.get("quality") or {}
    counts = kpi.get("counts") or {}

    drops = analytics.top_movers(session, limit=limit, direction="decrease")
    rises = analytics.top_movers(session, limit=limit, direction="increase")
    category_rows = analytics.category_movers(session, days=days, limit=limit)
    risk_rows = analytics.inventory_risk(session, limit=limit)
    anomalies = analytics.price_anomalies(session, limit=limit)
    catalog_rows = analytics.catalog_reconciliation(session, limit=max(limit * 4, 24))
    freshness_rows = analytics.data_freshness(session, stale_days=7)
    best_value = analytics.best_value(session, limit=limit)
    discounts = analytics.discount_leaders(session, limit=limit)

    opportunities = _drop_insights(drops, limit)
    opportunities.extend(_catalog_insights(catalog_rows, max(2, limit // 2)))
    for row in discounts[: max(2, limit // 2)]:
        depth = _num(row.get("discount_pct"))
        if depth is None or depth < 10:
            continue
        opportunities.append(
            _insight(
                key=f"discount-{row.get('product_id')}",
                kind="opportunity",
                severity="medium" if depth >= 20 else "low",
                title=str(row.get("canonical_name") or "Product"),
                detail=f"{row.get('category_name') or 'Uncategorised'} · list price discount",
                metric=f"-{depth:.1f}%",
                delta=-depth,
                icon="tag",
                link=f"/products/{row.get('product_id')}",
                action="Review the promotion",
            )
        )

    risks = _rise_insights(rises, limit)
    for row in risk_rows[: max(2, limit // 2)]:
        stock_pct = _num(row.get("in_stock_pct"))
        if stock_pct is None or stock_pct >= 70:
            continue
        risks.append(
            _insight(
                key=f"stock-{row.get('category_name')}",
                kind="risk",
                severity="high" if stock_pct < 40 else "medium",
                title=str(row.get("category_name") or "Uncategorised"),
                detail=(
                    f"{int(row.get('out_of_stock_count') or 0)} out-of-stock observations · "
                    f"{int(row.get('price_increases') or 0)} recent increases"
                ),
                metric=f"{stock_pct:.0f}% in stock",
                delta=None,
                icon="package",
                link="/analytics",
                action="Inspect availability",
            )
        )
    for row in anomalies[: max(1, limit // 3)]:
        z = _num(row.get("z_score"))
        if z is None:
            continue
        risks.append(
            _insight(
                key=f"anomaly-{row.get('product_id')}",
                kind="risk",
                severity="medium" if abs(z) < 3 else "high",
                title=str(row.get("canonical_name") or "Product"),
                detail=(
                    f"{_money(row.get('price_usd'))} versus a category mean of "
                    f"{_money(row.get('category_mean_usd'))}"
                ),
                metric=f"{z:+.1f}σ",
                delta=z,
                icon="scan",
                link=f"/products/{row.get('product_id')}",
                action="Validate the listing",
            )
        )

    quality_score = _num(quality.get("dq_score"))
    if quality_score is not None and quality_score < 90:
        risks.append(
            _insight(
                key="dq-score",
                kind="quality",
                severity="high" if quality_score < 75 else "medium",
                title="Data-quality score below target",
                detail=(
                    f"{int(quality.get('rules_failed') or 0)} failed and "
                    f"{int(quality.get('rules_warned') or 0)} warning rules · target is 90"
                ),
                metric=f"{quality_score:.1f}",
                delta=quality_score - 90,
                icon="shield",
                link="/quality",
                action="Open the quality report",
            )
        )

    freshness = _freshness_summary(freshness_rows)
    if freshness["stale_sources"]:
        risks.append(
            _insight(
                key="freshness",
                kind="quality",
                severity="medium",
                title="Some sources are going stale",
                detail=(
                    f"{freshness['stale_sources']} of {freshness['sources']} sources have "
                    "more than half of their products unseen for a week"
                ),
                metric=f"{freshness['stale_sources']} sources",
                delta=None,
                icon="timer",
                link="/sources",
                action="Review source health",
            )
        )

    category_signals = _category_signals(category_rows, limit)

    actions = sorted(
        [*opportunities, *risks],
        key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), -abs(_num(item.get("delta")) or 0)),
    )[: limit * 2]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc),
        "window_days": days,
        "headline": {
            "observations": int(latest.get("products") or 0),
            "canonical_products": int(counts.get("dim_product") or 0),
            "sources_reporting": int(latest.get("sources") or 0),
            "avg_price_usd": _num(latest.get("avg_price")),
            "price_changes": int(changes.get("total_changes") or 0),
            "significant_changes": int(changes.get("significant") or 0),
            "new_products": int(events.get("new") or 0),
            "removed_products": int(events.get("removed") or 0),
            "quality_score": quality_score,
            "opportunities": len(opportunities),
            "risks": len(risks),
        },
        "opportunities": opportunities,
        "risks": risks,
        "category_signals": category_signals,
        "freshness": freshness,
        "best_value": [
            {
                "product_id": row.get("product_id"),
                "name": row.get("canonical_name"),
                "price_usd": _num(row.get("price_usd")),
                "rating": _num(row.get("rating")),
                "value_score": _num(row.get("value_score")),
                "source_code": row.get("source_code"),
            }
            for row in best_value
        ],
        "actions": actions,
    }


__all__ = ["build_briefing"]
