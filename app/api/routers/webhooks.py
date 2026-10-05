"""Webhook subscription management: CRUD, test delivery and delivery history."""

from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentUser, DbSession, Page, PaginationDep, request_meta
from app.api.schemas import Message
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models.app_users import AppAuditLog, AppWebhook, AppWebhookDelivery
from app.models.base import utcnow
from app.services import webhooks

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _serialise(hook: AppWebhook, include_secret: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "webhook_id": hook.webhook_id,
        "user_id": hook.user_id,
        "name": hook.name,
        "target_url": hook.target_url,
        "description": hook.description,
        "events": hook.events or [],
        "is_active": hook.is_active,
        "headers": hook.headers or {},
        "timeout_seconds": hook.timeout_seconds,
        "max_attempts": hook.max_attempts,
        "success_count": hook.success_count,
        "failure_count": hook.failure_count,
        "consecutive_failures": hook.consecutive_failures,
        "last_status_code": hook.last_status_code,
        "last_error": hook.last_error,
        "last_triggered_at": hook.last_triggered_at,
        "disabled_reason": hook.disabled_reason,
        "created_at": hook.created_at,
    }
    if include_secret:
        data["secret"] = hook.secret
    return data


def _owned(session: DbSession, webhook_id: int, user: Any, *, admin: bool = False) -> AppWebhook:
    hook = session.get(AppWebhook, webhook_id)
    if hook is None:
        raise NotFoundError(f"webhook {webhook_id} not found")
    if not admin and hook.user_id != user.user_id:
        raise PermissionDeniedError("this webhook belongs to another user")
    return hook


@router.get("/events", summary="Events a webhook can subscribe to")
def events(_user: CurrentUser) -> dict[str, Any]:
    return {
        "events": list(webhooks.WEBHOOK_EVENTS),
        "wildcard": "*",
        "signature_header": webhooks.SIGNATURE_HEADER,
        "event_header": webhooks.EVENT_HEADER,
        "timestamp_header": webhooks.TIMESTAMP_HEADER,
        "retry_backoff_seconds": list(webhooks.RETRY_BACKOFF_SECONDS),
        "max_failures_before_disable": webhooks.MAX_FAILURES_BEFORE_DISABLE,
    }


@router.get("", summary="List my webhook subscriptions")
def list_webhooks(session: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    hooks = (
        session.execute(
            sa.select(AppWebhook)
            .where(AppWebhook.user_id == user.user_id)
            .order_by(AppWebhook.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_serialise(hook) for hook in hooks]


@router.post("", status_code=201, summary="Create a webhook subscription")
def create_webhook(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    payload: dict[str, Any],
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ConflictError("name is required")
    target_url = webhooks.validate_target_url(str(payload.get("target_url") or ""))

    hook = AppWebhook(
        user_id=user.user_id,
        name=name,
        target_url=target_url,
        secret=webhooks.generate_secret(),
        events=webhooks.normalise_events(payload.get("events")),
        description=payload.get("description"),
        headers=payload.get("headers") or {},
        timeout_seconds=int(payload.get("timeout_seconds") or 10),
        max_attempts=int(payload.get("max_attempts") or 3),
        is_active=bool(payload.get("is_active", True)),
    )
    session.add(hook)
    session.flush()

    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="webhook.create",
            entity_type="app_webhook",
            entity_id=str(hook.webhook_id),
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"name": hook.name, "target_url": hook.target_url, "events": hook.events},
        )
    )
    # The secret is returned exactly once, like an API key.
    return _serialise(hook, include_secret=True)


@router.get("/{webhook_id}", summary="Webhook detail")
def get_webhook(session: DbSession, user: CurrentUser, webhook_id: int) -> dict[str, Any]:
    return _serialise(_owned(session, webhook_id, user))


@router.patch("/{webhook_id}", summary="Update a webhook subscription")
def update_webhook(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    webhook_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    hook = _owned(session, webhook_id, user)
    if "target_url" in payload:
        hook.target_url = webhooks.validate_target_url(str(payload["target_url"]))
    if "events" in payload:
        hook.events = webhooks.normalise_events(payload["events"])
    for field in ("name", "description", "headers", "is_active"):
        if field in payload:
            setattr(hook, field, payload[field])
    for field in ("timeout_seconds", "max_attempts"):
        if field in payload:
            setattr(hook, field, int(payload[field]))
    if payload.get("is_active"):
        hook.consecutive_failures = 0
        hook.disabled_reason = None
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="webhook.update",
            entity_type="app_webhook",
            entity_id=str(hook.webhook_id),
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"fields": sorted(payload)},
        )
    )
    return _serialise(hook)


@router.delete("/{webhook_id}", response_model=Message, summary="Delete a webhook subscription")
def delete_webhook(session: DbSession, user: CurrentUser, webhook_id: int) -> Message:
    hook = _owned(session, webhook_id, user)
    session.delete(hook)
    return Message(message=f"webhook {webhook_id} deleted")


@router.post("/{webhook_id}/test", summary="Send a test event to this webhook")
def test_webhook(
    session: DbSession,
    user: CurrentUser,
    webhook_id: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hook = _owned(session, webhook_id, user)
    event = str((payload or {}).get("event") or "run.completed")
    if event not in webhooks.WEBHOOK_EVENTS:
        raise ConflictError(f"unknown event '{event}'", details={"supported": list(webhooks.WEBHOOK_EVENTS)})
    body = (payload or {}).get("data") or {
        "message": "Test delivery from the Product Intelligence dashboard",
        "webhook_id": hook.webhook_id,
    }
    delivery = webhooks.deliver(session, hook, event, body)
    session.flush()
    result: dict[str, Any] = {"event": event, "delivered": bool(delivery and delivery.status == "success")}
    if delivery is not None:
        result |= {
            "delivery_id": delivery.delivery_id,
            "status": delivery.status,
            "status_code": delivery.status_code,
            "duration_ms": delivery.duration_ms,
            "error": delivery.error,
            "response_excerpt": delivery.response_excerpt,
        }
    return result


@router.get(
    "/{webhook_id}/deliveries",
    summary="Delivery history for a webhook",
)
def deliveries(
    session: DbSession,
    user: CurrentUser,
    webhook_id: int,
    pagination: PaginationDep,
    status: Annotated[str | None, Query()] = None,
) -> Page[dict[str, Any]]:
    hook = _owned(session, webhook_id, user)
    conditions = [AppWebhookDelivery.webhook_id == hook.webhook_id]
    if status:
        conditions.append(AppWebhookDelivery.status == status)
    total = (
        session.execute(
            sa.select(sa.func.count()).select_from(AppWebhookDelivery).where(*conditions)
        ).scalar()
        or 0
    )
    rows = (
        session.execute(
            sa.select(AppWebhookDelivery)
            .where(*conditions)
            .order_by(AppWebhookDelivery.created_at.desc())
            .limit(pagination.page_size)
            .offset(pagination.offset)
        )
        .scalars()
        .all()
    )
    items = [
        {
            "delivery_id": row.delivery_id,
            "event": row.event,
            "status": row.status,
            "attempts": row.attempts,
            "status_code": row.status_code,
            "response_excerpt": row.response_excerpt,
            "error": row.error,
            "duration_ms": row.duration_ms,
            "next_retry_at": row.next_retry_at,
            "delivered_at": row.delivered_at,
            "created_at": row.created_at,
            "payload": row.payload,
        }
        for row in rows
    ]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.post("/retry-due", summary="Retry failed deliveries whose backoff has elapsed")
def retry_due(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    attempted = webhooks.retry_due(session)
    return {"attempted": attempted, "checked_at": utcnow().isoformat()}


@router.post("/{webhook_id}/rotate-secret", summary="Rotate the signing secret")
def rotate_secret(session: DbSession, user: CurrentUser, webhook_id: int) -> dict[str, Any]:
    hook = _owned(session, webhook_id, user)
    hook.secret = webhooks.generate_secret()
    hook.consecutive_failures = 0
    return _serialise(hook, include_secret=True)


__all__ = ["router"]
