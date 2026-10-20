"""Alert-rule evaluation across every supported metric and delivery channel."""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa

from app.models.app_users import AppAlertRule, AppNotification
from app.models.dimensions import DimDate, DimProduct
from app.models.facts import ChgPriceChange, ChgProductEvent
from app.models.operations import DqRuleResult, EtlRun
from app.services.alerts import evaluate_all

NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture(autouse=True)
def _rollback_alert_rows(session):
    yield
    session.rollback()


def _seed_metric_rows(session) -> DimProduct:
    date_id = session.execute(sa.select(DimDate.date_id).limit(1)).scalar() or 20260101
    product = DimProduct(
        canonical_name="Alert test product",
        normalized_name="alert test product",
        display_name="Alert test product",
        source_code="local_demo",
        currency="USD",
        current_price=10,
        current_rating=1.0,
        availability="out_of_stock",
        fingerprint="alert-test-product",
        is_active=True,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(product)
    session.flush()
    session.add(
        EtlRun(
            run_id="alert-test-run",
            pipeline="product_intelligence",
            target_database="sqlite",
            status="success",
            started_at=NOW,
            finished_at=NOW,
        )
    )
    session.flush()
    session.add(
        DqRuleResult(
            run_id="alert-test-run",
            rule_code="DQ-ALERT",
            rule_name="Alert test rule",
            dimension="completeness",
            severity="error",
            status="fail",
            evaluated_at=NOW,
        )
    )
    session.add(
        ChgPriceChange(
            product_id=product.product_id,
            source_code="local_demo",
            run_id="alert-test-run",
            date_id=date_id,
            previous_price=20,
            new_price=10,
            change_abs=-10,
            change_pct=-50,
            direction="decrease",
            is_significant=True,
            detected_at=NOW,
        )
    )
    session.add(
        ChgProductEvent(
            product_id=product.product_id,
            source_code="local_demo",
            run_id="alert-test-run",
            date_id=date_id,
            event_type="new",
            detected_at=NOW,
        )
    )
    session.flush()
    return product


def _rule(session, **overrides) -> AppAlertRule:
    values = {
        "user_id": 1,
        "name": "test rule",
        "metric": "rating",
        "operator": "lt",
        "threshold": 5.0,
        "channel": "in_app",
        "is_active": True,
    }
    values.update(overrides)
    rule = AppAlertRule(**values)
    session.add(rule)
    session.flush()
    return rule


def test_alert_evaluation_covers_all_metrics(session):
    _seed_metric_rows(session)
    rules = [
        _rule(session, name="price", metric="price_change_pct", operator="lt", threshold=-10),
        _rule(session, name="rating", metric="rating", operator="lt", threshold=2.5),
        _rule(session, name="new", metric="new_product", operator="gt", threshold=0),
        _rule(session, name="dq", metric="dq_failure", operator="gt", threshold=0),
        _rule(session, name="stock", metric="stock_out", operator="gt", threshold=0),
    ]

    summary = evaluate_all(session, user_id=1, publish=False)

    by_id = {item["alert_id"]: item for item in summary["rules"]}
    for rule in rules:
        assert by_id[rule.alert_id]["fires"] is True
        assert by_id[rule.alert_id]["value"] >= 1


def test_publish_creates_in_app_notifications_and_updates_counters(session):
    _seed_metric_rows(session)
    rule = _rule(session, name="rating publisher", metric="rating", operator="lt", threshold=2.5)

    summary = evaluate_all(session, user_id=1, publish=True)

    assert summary["notifications_created"] >= 1
    session.refresh(rule)
    assert rule.trigger_count >= 1
    assert rule.last_triggered_at is not None
    notification = (
        session.execute(sa.select(AppNotification).where(AppNotification.alert_id == rule.alert_id))
        .scalars()
        .first()
    )
    assert notification is not None
    assert notification.entity_type == "alert_rule"
    assert notification.action_url == "/alerts"


def test_webhook_alert_uses_the_rule_owner(session, monkeypatch):
    _seed_metric_rows(session)
    calls: list[dict] = []

    def fake_emit(session_, event, payload, *, user_id=None):
        calls.append({"event": event, "payload": payload, "user_id": user_id})
        return []

    monkeypatch.setattr("app.services.webhooks.emit", fake_emit)
    rule = _rule(
        session,
        name="webhook publisher",
        metric="rating",
        operator="lt",
        threshold=2.5,
        channel="webhook",
    )

    evaluate_all(session, user_id=1, publish=True)

    matching = [call for call in calls if call["event"] == "alert.triggered"]
    assert matching
    assert matching[0]["user_id"] == rule.user_id
    assert matching[0]["payload"]["alert_id"] == rule.alert_id
    in_app = (
        session.execute(sa.select(AppNotification).where(AppNotification.alert_id == rule.alert_id))
        .scalars()
        .first()
    )
    assert in_app is None
    session.refresh(rule)
    assert rule.trigger_count >= 1
