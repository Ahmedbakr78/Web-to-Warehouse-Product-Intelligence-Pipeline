"""Outbound webhook delivery: signed, retried and fully audited.

Design:
    * Every payload is signed with HMAC-SHA256 using a per-subscription secret, so the
      receiver can verify authenticity (``X-Webhook-Signature: sha256=<hex>``).
    * Deliveries retry with exponential backoff and are recorded row by row, giving a
      complete delivery log per subscription.
    * Targets are validated before any request is made: only ``http``/``https`` URLs
      pointing at a public host are allowed, which blocks SSRF against loopback,
      link-local and RFC1918 addresses.
    * Subscriptions auto-disable after repeated consecutive failures so a dead endpoint
      cannot slow the pipeline down forever.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import PipelineError
from app.core.logging import get_logger
from app.models.app_users import AppWebhook, AppWebhookDelivery
from app.models.base import utcnow

log = get_logger(__name__)

WEBHOOK_EVENTS: tuple[str, ...] = (
    "run.completed",
    "run.failed",
    "run.started",
    "dq.failed",
    "price.spike",
    "product.new",
    "product.removed",
    "catalog.mismatch",
    "alert.triggered",
    "backfill.completed",
)
MAX_FAILURES_BEFORE_DISABLE = 10
MAX_EVENT_NAME = 64
RETRY_BACKOFF_SECONDS = (30, 300, 1800)  # 30s, 5m, 30m
USER_AGENT = "product-intelligence-webhooks/1.0"
SIGNATURE_HEADER = "X-Webhook-Signature"
EVENT_HEADER = "X-Webhook-Event"
DELIVERY_HEADER = "X-Webhook-Delivery"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"


@dataclass
class DeliveryOutcome:
    """Result of one delivery attempt.

    ``delivery`` is the persisted row when the attempt was recorded (``record=True``);
    retries reuse an existing row, so the status fields are reported separately.
    """

    status: str
    status_code: int | None = None
    error: str | None = None
    duration_ms: int | None = None
    delivery: AppWebhookDelivery | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success"


class WebhookError(PipelineError):
    """Configuration or delivery problem that the caller should surface."""

    status_code = 400
    code = "webhook_error"


def generate_secret() -> str:
    """Per-subscription signing secret (shown once, like an API key)."""
    return "whsec_" + secrets.token_urlsafe(32)


def sign_payload(secret: str, body: bytes, timestamp: int) -> str:
    """HMAC-SHA256 over ``timestamp.body`` so replays are detectable."""
    signed = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, timestamp: str | int, signature: str) -> bool:
    """Helper for receivers (and our tests) verifying an incoming signature."""
    try:
        expected = sign_payload(secret, body, int(timestamp))
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, signature or "")


# --------------------------------------------------------------------------------------
# Target validation (SSRF guard)
# --------------------------------------------------------------------------------------
def _is_blocked_address(host: str) -> bool:
    """True when the host resolves to a private, loopback or reserved address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return True
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def validate_target_url(url: str) -> str:
    """Validate a webhook target and return it normalised.

    Raises ``WebhookError`` for anything that is not a public http(s) endpoint.
    """
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise WebhookError("target_url must use http or https")
    if not parsed.hostname:
        raise WebhookError("target_url must include a host")
    if parsed.username or parsed.password:
        raise WebhookError("target_url must not embed credentials")
    if _is_blocked_address(parsed.hostname):
        raise WebhookError(
            "target_url must resolve to a public address",
            details={"host": parsed.hostname},
        )
    return parsed.geturl()


# --------------------------------------------------------------------------------------
# Subscription helpers
# --------------------------------------------------------------------------------------
def normalise_events(events: list[str] | None) -> list[str]:
    """Validate and de-duplicate a subscription's event list."""
    if not events:
        return list(WEBHOOK_EVENTS)
    cleaned: list[str] = []
    for raw in events:
        name = str(raw).strip()
        if not name or len(name) > MAX_EVENT_NAME:
            raise WebhookError(f"invalid event name: {raw!r}")
        if name != "*" and name not in WEBHOOK_EVENTS:
            raise WebhookError(f"unknown event '{name}'", details={"supported": list(WEBHOOK_EVENTS)})
        if name not in cleaned:
            cleaned.append(name)
    return cleaned


def subscriptions_for_event(session: Session, event: str) -> list[AppWebhook]:
    """Active subscriptions listening to ``event`` (or to everything)."""
    hooks = (
        session.execute(
            sa.select(AppWebhook).where(
                AppWebhook.is_active.is_(True),
                AppWebhook.consecutive_failures < MAX_FAILURES_BEFORE_DISABLE,
            )
        )
        .scalars()
        .all()
    )
    return [hook for hook in hooks if (hook.events or []).count("*") or event in (hook.events or [])]


# --------------------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------------------
def _post(url: str, body: bytes, headers: dict[str, str], timeout: int) -> tuple[int, str]:
    """POST ``body`` and return ``(status_code, response_excerpt)``."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            excerpt = response.read(512).decode("utf-8", "replace")
            return int(response.status), excerpt
    except urllib.error.HTTPError as exc:  # 4xx/5xx still tell us something
        excerpt = exc.read(512).decode("utf-8", "replace") if exc.fp else ""
        return int(exc.code), excerpt


def deliver(
    session: Session,
    hook: AppWebhook,
    event: str,
    payload: dict[str, Any],
    *,
    record: bool = True,
) -> DeliveryOutcome:
    """Attempt one delivery, record the outcome and schedule a retry if it failed."""
    row: AppWebhookDelivery | None = None
    if record:
        row = AppWebhookDelivery(webhook_id=hook.webhook_id, event=event, payload=payload, status="pending")
        session.add(row)
        session.flush()

    body = json.dumps(
        {
            "event": event,
            "sent_at": utcnow().isoformat(),
            "subscription": {"id": hook.webhook_id, "name": hook.name},
            "data": payload,
        },
        default=str,
    ).encode()
    timestamp = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        EVENT_HEADER: event,
        TIMESTAMP_HEADER: str(timestamp),
        SIGNATURE_HEADER: sign_payload(hook.secret, body, timestamp),
        **(hook.headers or {}),
    }
    if row is not None:
        headers[DELIVERY_HEADER] = str(row.delivery_id)

    started = time.perf_counter()
    status_code: int | None = None
    excerpt = ""
    error: str | None = None
    try:
        status_code, excerpt = _post(hook.target_url, body, headers, hook.timeout_seconds or 10)
        if status_code >= 400:
            error = f"HTTP {status_code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    duration_ms = int((time.perf_counter() - started) * 1000)
    success = status_code is not None and status_code < 400

    hook.last_triggered_at = utcnow()
    hook.last_status_code = status_code
    if success:
        hook.success_count = (hook.success_count or 0) + 1
        hook.consecutive_failures = 0
        hook.last_error = None
        hook.disabled_reason = None
    else:
        hook.failure_count = (hook.failure_count or 0) + 1
        hook.consecutive_failures = (hook.consecutive_failures or 0) + 1
        hook.last_error = error
        if hook.consecutive_failures >= MAX_FAILURES_BEFORE_DISABLE:
            hook.is_active = False
            hook.disabled_reason = "auto-disabled after repeated failures"
            log.warning("webhook %s auto-disabled: %s", hook.webhook_id, hook.disabled_reason)

    if row is not None:
        row.status = "success" if success else "failed"
        row.attempts = 1
        row.status_code = status_code
        row.response_excerpt = excerpt[:512] or None
        row.error = error
        row.duration_ms = duration_ms
        if success:
            row.delivered_at = utcnow()
        else:
            row.next_retry_at = utcnow() + dt.timedelta(seconds=RETRY_BACKOFF_SECONDS[0])
    return DeliveryOutcome(
        status="success" if success else "failed",
        status_code=status_code,
        error=error,
        duration_ms=duration_ms,
        delivery=row,
    )


def emit(session: Session, event: str, payload: dict[str, Any]) -> list[AppWebhookDelivery]:
    """Fan an event out to every matching subscription.

    Failures are swallowed on purpose: a broken webhook must never fail a pipeline run.
    """
    deliveries: list[AppWebhookDelivery] = []
    for hook in subscriptions_for_event(session, event):
        try:
            outcome = deliver(session, hook, event, payload)
            if outcome.delivery is not None:
                deliveries.append(outcome.delivery)
        except Exception:  # noqa: BLE001 - integrations must not break the pipeline
            log.exception("webhook delivery failed for subscription %s", hook.webhook_id)
        session.flush()
    return deliveries


def retry_due(session: Session, limit: int = 50) -> int:
    """Re-attempt failed deliveries whose backoff has elapsed. Returns attempts made."""
    now = utcnow()
    pending = (
        session.execute(
            sa.select(AppWebhookDelivery)
            .where(
                AppWebhookDelivery.status == "failed",
                AppWebhookDelivery.next_retry_at.is_not(None),
                AppWebhookDelivery.next_retry_at <= now,
            )
            .order_by(AppWebhookDelivery.next_retry_at)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    attempted = 0
    for delivery in pending:
        hook = session.get(AppWebhook, delivery.webhook_id)
        if hook is None or not hook.is_active:
            continue
        outcome = deliver(session, hook, delivery.event, delivery.payload or {}, record=False)
        delivery.attempts = (delivery.attempts or 0) + 1
        delivery.next_retry_at = None
        delivery.duration_ms = outcome.duration_ms
        if outcome.ok:
            delivery.status = "success"
            delivery.delivered_at = utcnow()
            delivery.status_code = outcome.status_code
            delivery.response_excerpt = None
            delivery.error = None
        elif delivery.attempts >= (hook.max_attempts or 3):
            delivery.status = "failed"
        else:
            backoff = RETRY_BACKOFF_SECONDS[min(delivery.attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
            delivery.next_retry_at = now + dt.timedelta(seconds=backoff)
        attempted += 1
        session.flush()
    return attempted


__all__ = [
    "EVENT_HEADER",
    "DeliveryOutcome",
    "MAX_FAILURES_BEFORE_DISABLE",
    "RETRY_BACKOFF_SECONDS",
    "SIGNATURE_HEADER",
    "WEBHOOK_EVENTS",
    "WebhookError",
    "deliver",
    "emit",
    "generate_secret",
    "normalise_events",
    "retry_due",
    "sign_payload",
    "subscriptions_for_event",
    "validate_target_url",
    "verify_signature",
]
