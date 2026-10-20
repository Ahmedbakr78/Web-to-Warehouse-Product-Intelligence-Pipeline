"""Alert-rule evaluation and notification publishing.

Rules are evaluated against the warehouse. Price and rating thresholds are compared
against the metric itself; the count metrics (new products, DQ failures, out-of-stock)
are compared against the number of matching rows. A matching in-app rule writes an
:class:`AppNotification`; a matching webhook rule emits ``alert.triggered`` to that
user's active subscriptions.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.app_users import AppAlertRule, AppNotification
from app.models.base import utcnow
from app.models.dimensions import DimCategory, DimProduct
from app.models.facts import ChgPriceChange, ChgProductEvent
from app.models.operations import DqRuleResult, EtlRun

log = get_logger(__name__)

_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "lt": lambda value, threshold: value < threshold,
    "lte": lambda value, threshold: value <= threshold,
    "gt": lambda value, threshold: value > threshold,
    "gte": lambda value, threshold: value >= threshold,
    "eq": lambda value, threshold: value == threshold,
}

_SQL_COMPARISONS: dict[str, Callable[[Any, float], Any]] = {
    "lt": lambda column, threshold: column < threshold,
    "lte": lambda column, threshold: column <= threshold,
    "gt": lambda column, threshold: column > threshold,
    "gte": lambda column, threshold: column >= threshold,
    "eq": lambda column, threshold: column == threshold,
}

COUNT_METRICS = {"new_product", "dq_failure", "stock_out"}


def _comparison(operator: str) -> Callable[[float, float], bool]:
    return _COMPARISONS.get(operator, _COMPARISONS["lt"])


def _sql_comparison(operator: str, column: Any, threshold: float) -> Any:
    return _SQL_COMPARISONS.get(operator, _SQL_COMPARISONS["lt"])(column, threshold)


def _product_filters(rule: AppAlertRule) -> tuple[list[Any], list[Any]]:
    conditions: list[Any] = []
    joins: list[tuple[Any, Any]] = []
    if rule.category:
        joins.append((DimCategory, DimProduct.category_id == DimCategory.category_id))
        conditions.append(DimCategory.name == rule.category)
    if rule.source_code:
        conditions.append(DimProduct.source_code == rule.source_code)
    return conditions, joins


def _count(
    session: Session,
    select_from: Any,
    conditions: list[Any],
    joins: list[tuple[Any, Any]],
) -> int:
    statement = sa.select(sa.func.count()).select_from(select_from)
    for target, onclause in joins:
        statement = statement.join(target, onclause)
    if conditions:
        statement = statement.where(*conditions)
    return int(session.execute(statement).scalar() or 0)


def evaluate_rule(session: Session, rule: AppAlertRule, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Return how many rows a rule matches and whether it fires right now."""
    moment = now or utcnow()
    operator = rule.operator if rule.operator in _COMPARISONS else "lt"
    product_conditions, joins = _product_filters(rule)

    if rule.metric == "price_change_pct":
        since = moment - dt.timedelta(days=1)
        conditions = [
            ChgPriceChange.detected_at >= since,
            _sql_comparison(operator, ChgPriceChange.change_pct, float(rule.threshold)),
            *product_conditions,
        ]
        value = _count(
            session,
            ChgPriceChange,
            conditions,
            [(DimProduct, ChgPriceChange.product_id == DimProduct.product_id), *joins],
        )
        fires = value > 0
    elif rule.metric == "rating":
        conditions = [
            DimProduct.current_rating.is_not(None),
            DimProduct.is_active.is_(True),
            _sql_comparison(operator, DimProduct.current_rating, float(rule.threshold)),
            *product_conditions,
        ]
        value = _count(session, DimProduct, conditions, joins)
        fires = value > 0
    elif rule.metric == "new_product":
        since = moment - dt.timedelta(days=7)
        conditions = [
            ChgProductEvent.event_type == "new",
            ChgProductEvent.detected_at >= since,
            *product_conditions,
        ]
        value = _count(
            session,
            ChgProductEvent,
            conditions,
            [(DimProduct, ChgProductEvent.product_id == DimProduct.product_id), *joins],
        )
        fires = _comparison(operator)(float(value), float(rule.threshold))
    elif rule.metric == "dq_failure":
        # The verdict must come from the most recent run that actually carries a
        # data-quality score. A run that has not been scored yet (still running,
        # or aborted before the DQ stage) must not mask the previous verdict.
        latest_run = session.execute(
            sa.select(EtlRun.run_id)
            .join(DqRuleResult, DqRuleResult.run_id == EtlRun.run_id)
            .order_by(EtlRun.started_at.desc())
            .limit(1)
        ).scalar()
        conditions = [DqRuleResult.run_id == latest_run, DqRuleResult.status == "fail"]
        value = _count(session, DqRuleResult, conditions, [])
        fires = _comparison(operator)(float(value), float(rule.threshold))
    else:
        conditions = [
            DimProduct.availability == "out_of_stock",
            DimProduct.is_active.is_(True),
            *product_conditions,
        ]
        value = _count(session, DimProduct, conditions, joins)
        fires = _comparison(operator)(float(value), float(rule.threshold))

    return {
        "alert_id": rule.alert_id,
        "name": rule.name,
        "metric": rule.metric,
        "operator": rule.operator,
        "threshold": float(rule.threshold),
        "channel": rule.channel,
        "value": value,
        "fires": fires,
        "matches_now": value if fires else 0,
    }


def _notify(session: Session, rule: AppAlertRule, evaluation: dict[str, Any]) -> int:
    created = 0
    moment = utcnow()
    if rule.channel == "webhook":
        from app.services.webhooks import emit

        payload = {
            "alert_id": rule.alert_id,
            "name": rule.name,
            "metric": rule.metric,
            "operator": rule.operator,
            "threshold": float(rule.threshold),
            "value": evaluation["value"],
            "user_id": rule.user_id,
        }
        try:
            emit(session, "alert.triggered", payload, user_id=rule.user_id)
        except Exception:  # noqa: BLE001 - a webhook must never break alert publication
            log.exception("alert webhook emission failed for rule %s", rule.alert_id)
    else:
        level = "critical" if evaluation["value"] >= 10 else "warning"
        session.add(
            AppNotification(
                user_id=rule.user_id,
                alert_id=rule.alert_id,
                level=level,
                title=f"{rule.name}: {evaluation['value']} matching rows",
                body=(
                    f"{rule.metric} {rule.operator} {rule.threshold:g}; "
                    f"{evaluation['value']} matching rows in the warehouse"
                ),
                entity_type="alert_rule",
                action_url="/alerts",
            )
        )
        created = 1
    rule.last_triggered_at = moment
    rule.trigger_count = (rule.trigger_count or 0) + 1
    return created


def evaluate_all(
    session: Session,
    *,
    user_id: int | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    """Evaluate active rules, optionally publishing notifications and webhooks."""
    statement = sa.select(AppAlertRule).where(AppAlertRule.is_active.is_(True))
    if user_id is not None:
        statement = statement.where(AppAlertRule.user_id == user_id)
    rules = session.execute(statement.order_by(AppAlertRule.alert_id)).scalars().all()
    now = utcnow()
    results: list[dict[str, Any]] = []
    notifications = 0
    for rule in rules:
        evaluation = evaluate_rule(session, rule, now=now)
        results.append(evaluation)
        if publish and evaluation["fires"]:
            notifications += _notify(session, rule, evaluation)
    session.flush()
    return {
        "evaluated": len(results),
        "notifications_created": notifications,
        "fired": sum(1 for item in results if item["fires"]),
        "rules": results,
    }


__all__ = ["COUNT_METRICS", "evaluate_all", "evaluate_rule"]
