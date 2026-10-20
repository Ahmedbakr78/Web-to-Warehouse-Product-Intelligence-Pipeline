"""Pipeline lifecycle events published to subscribed webhooks."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services.webhooks import emit

log = get_logger(__name__)


def emit_pipeline_started(session: Session, result: Any) -> None:
    """Publish ``run.started`` before the first stage runs."""
    emit(
        session,
        "run.started",
        {
            "run_id": getattr(result, "run_id", None),
            "status": "running",
            "database": getattr(result, "database", None),
            "started_at": getattr(result, "started_at", None),
        },
    )


def emit_pipeline_result(session: Session, result: Any) -> int:
    """Publish run, quality, product, price and catalogue events for one run.

    Returns the number of events emitted. Webhook delivery failures are already
    swallowed by :func:`app.services.webhooks.emit`, so a dead subscriber can never
    fail a pipeline run.
    """
    counters = dict(getattr(result, "counters", None) or {})
    payload = {
        "run_id": getattr(result, "run_id", None),
        "status": getattr(result, "status", None),
        "database": getattr(result, "database", None),
        "started_at": getattr(result, "started_at", None),
        "finished_at": getattr(result, "finished_at", None),
        "duration_ms": getattr(result, "duration_ms", None),
        **counters,
    }
    emitted = 0
    status = str(getattr(result, "status", "") or "")
    run_event = "run.failed" if status == "failed" else "run.completed"
    emit(session, run_event, payload)
    emitted += 1

    quality = getattr(result, "quality", None) or {}
    if int(quality.get("fail") or 0) > 0:
        emit(
            session,
            "dq.failed",
            {**payload, "dq_failed": quality.get("fail"), "dq_score": quality.get("score")},
        )
        emitted += 1
    if int(counters.get("new_products") or 0) > 0:
        emit(session, "product.new", {**payload, "new_products": counters["new_products"]})
        emitted += 1
    if int(counters.get("removed_products") or 0) > 0:
        emit(session, "product.removed", {**payload, "removed_products": counters["removed_products"]})
        emitted += 1
    if int(counters.get("price_changes") or 0) > 0:
        emit(session, "price.spike", {**payload, "price_changes": counters["price_changes"]})
        emitted += 1
    reconciliation = getattr(result, "reconciliation", None) or {}
    if int(reconciliation.get("price_mismatches") or 0) > 0:
        emit(
            session,
            "catalog.mismatch",
            {**payload, "price_mismatches": reconciliation["price_mismatches"]},
        )
        emitted += 1
    return emitted


__all__ = ["emit_pipeline_result", "emit_pipeline_started"]
