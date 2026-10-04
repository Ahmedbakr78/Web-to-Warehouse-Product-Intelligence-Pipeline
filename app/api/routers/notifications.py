"""Notifications and user alert rules."""

from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, PaginationDep
from app.api.schemas import AlertRuleCreate, AlertRuleRead, Message, NotificationRead, Page
from app.core.errors import ProductNotFoundError

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=Page[NotificationRead], summary="My notifications")
def notifications(
    session: DbSession,
    user: CurrentUser,
    pagination: PaginationDep,
    unread_only: Annotated[bool, Query()] = False,
) -> Page[NotificationRead]:
    from app.models.app_users import AppNotification

    conditions = [AppNotification.user_id == user.user_id]
    if unread_only:
        conditions.append(AppNotification.is_read.is_(False))
    total = (
        session.execute(sa.select(sa.func.count()).select_from(AppNotification).where(*conditions)).scalar()
        or 0
    )
    rows = (
        session.execute(
            sa.select(AppNotification)
            .where(*conditions)
            .order_by(AppNotification.created_at.desc())
            .limit(pagination.page_size)
            .offset(pagination.offset)
        )
        .scalars()
        .all()
    )
    return Page.build(
        [NotificationRead.model_validate(row) for row in rows], total, pagination.page, pagination.page_size
    )


@router.post("/notifications/{notification_id}/read", response_model=Message, summary="Mark as read")
def mark_read(notification_id: int, session: DbSession, user: CurrentUser) -> Message:
    from app.models.app_users import AppNotification

    row = session.get(AppNotification, notification_id)
    if row is None:
        raise ProductNotFoundError(f"notification {notification_id} not found")
    if row.user_id not in (None, user.user_id):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("this notification belongs to another user")
    row.is_read = True
    return Message(message="Marked as read")


@router.post("/notifications/read-all", response_model=Message, summary="Mark all as read")
def mark_all_read(session: DbSession, user: CurrentUser) -> Message:
    from app.models.app_users import AppNotification

    count = (
        session.execute(
            sa.update(AppNotification)
            .where(AppNotification.user_id == user.user_id, AppNotification.is_read.is_(False))
            .values(is_read=True)
        ).rowcount  # type: ignore[attr-defined]
        or 0
    )
    return Message(message=f"{count} notifications marked as read", detail={"updated": count})


@router.get("/alerts", response_model=list[AlertRuleRead], summary="My alert rules")
def alerts(session: DbSession, user: CurrentUser) -> list[AlertRuleRead]:
    from app.models.app_users import AppAlertRule

    rows = (
        session.execute(
            sa.select(AppAlertRule)
            .where(AppAlertRule.user_id == user.user_id)
            .order_by(AppAlertRule.alert_id)
        )
        .scalars()
        .all()
    )
    return [AlertRuleRead.model_validate(row) for row in rows]


@router.post("/alerts", response_model=AlertRuleRead, status_code=201, summary="Create an alert rule")
def create_alert(payload: AlertRuleCreate, session: DbSession, user: CurrentUser) -> AlertRuleRead:
    from app.models.app_users import AppAlertRule

    rule = AppAlertRule(
        user_id=user.user_id,
        name=payload.name,
        metric=payload.metric,
        operator=payload.operator,
        threshold=payload.threshold,
        category=payload.category,
        source_code=payload.source_code,
        channel=payload.channel,
        is_active=payload.is_active,
    )
    session.add(rule)
    session.flush()
    return AlertRuleRead.model_validate(rule)


@router.patch("/alerts/{alert_id}", response_model=AlertRuleRead, summary="Update an alert rule")
def update_alert(
    alert_id: int, session: DbSession, user: CurrentUser, payload: AlertRuleCreate
) -> AlertRuleRead:
    from app.models.app_users import AppAlertRule

    rule = session.get(AppAlertRule, alert_id)
    if rule is None or rule.user_id != user.user_id:
        raise ProductNotFoundError(f"alert {alert_id} not found")
    for field_name, value in payload.model_dump().items():
        setattr(rule, field_name, value)
    return AlertRuleRead.model_validate(rule)


@router.delete("/alerts/{alert_id}", response_model=Message, summary="Delete an alert rule")
def delete_alert(alert_id: int, session: DbSession, user: CurrentUser) -> Message:
    from app.models.app_users import AppAlertRule

    rule = session.get(AppAlertRule, alert_id)
    if rule is None or rule.user_id != user.user_id:
        raise ProductNotFoundError(f"alert {alert_id} not found")
    session.delete(rule)
    return Message(message=f"Alert '{rule.name}' deleted")


@router.post("/alerts/evaluate", summary="Evaluate my alert rules against the latest data")
def evaluate_alerts(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Real evaluation query: how many rows would fire each rule right now."""
    from app.models.app_users import AppAlertRule

    rules = (
        session.execute(
            sa.select(AppAlertRule).where(
                AppAlertRule.user_id == user.user_id, AppAlertRule.is_active.is_(True)
            )
        )
        .scalars()
        .all()
    )
    results: list[dict[str, Any]] = []
    for rule in rules:
        if rule.metric == "price_change_pct":
            clause = "WHERE is_significant AND ABS(change_pct) >= :threshold"
            params = {"threshold": abs(rule.threshold)}
            rows = (
                session.execute(sa.text(f"SELECT COUNT(*) FROM vw_price_changes {clause}"), params).scalar()
                or 0
            )
        elif rule.metric == "rating":
            rows = (
                session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM vw_product_current WHERE rating IS NOT NULL AND rating < :threshold"
                    ),
                    {"threshold": rule.threshold},
                ).scalar()
                or 0
            )
        elif rule.metric == "new_product":
            rows = (
                session.execute(
                    sa.text("SELECT COUNT(*) FROM vw_new_products WHERE first_seen_at >= :since"),
                    {
                        "since": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                        - __import__("datetime").timedelta(days=7)
                    },
                ).scalar()
                or 0
            )
        elif rule.metric == "dq_failure":
            rows = (
                session.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM dq_rule_result WHERE status = 'fail' AND run_id = (SELECT MAX(run_id) FROM etl_run)"
                    )
                ).scalar()
                or 0
            )
        else:
            rows = (
                session.execute(
                    sa.text("SELECT COUNT(*) FROM vw_product_current WHERE availability = 'out_of_stock'")
                ).scalar()
                or 0
            )
        results.append(
            {
                "alert_id": rule.alert_id,
                "name": rule.name,
                "metric": rule.metric,
                "threshold": rule.threshold,
                "matches_now": int(rows),
            }
        )
    return {"evaluated": len(results), "rules": results}
