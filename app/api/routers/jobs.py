"""Job queue API: enqueue, inspect, cancel, retry, and a live progress stream."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import AdminUser, CurrentUser, DbSession, PipelineUser, ReadUser, request_meta
from app.api.schemas import Message
from app.core.errors import PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.jobs import queue
from app.models.app_users import AppAuditLog

log = get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", summary="List background jobs")
def list_jobs(
    session: DbSession,
    _user: ReadUser,
    status: Annotated[
        str | None, Query(description="queued | running | succeeded | failed | cancelled")
    ] = None,
    job_type: str | None = None,
    mine: Annotated[bool, Query(description="Only jobs I requested")] = False,
    user: CurrentUser = None,  # type: ignore[assignment]
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Job history, newest first.

    A non-admin can only see their own jobs; an admin sees everything.
    """
    from app.api.security import at_least

    requested_by = user.user_id if (mine or not at_least(user.role, "admin")) else None
    rows = queue.list_jobs(session, status=status, job_type=job_type, requested_by=requested_by, limit=limit)
    from app.services.realtime import broker

    return {
        "items": rows,
        "total": len(rows),
        "worker": {**queue.worker_status(), "realtime_subscribers": broker.subscriber_count},
    }


@router.get("/worker", summary="Background worker status")
def worker_status(_user: ReadUser) -> dict[str, Any]:
    from app.services.realtime import broker

    return {
        **queue.worker_status(),
        "subscribers": broker.subscriber_count,
        "topics": broker.topics(),
    }


@router.get("/types", summary="Registered job types and whether they can be cancelled")
def job_types(_user: ReadUser) -> dict[str, Any]:
    from app.jobs.handlers import REGISTRY

    return {
        "types": sorted(REGISTRY),
        "cancellable": sorted(queue.CANCELLABLE),
    }


@router.post(
    "/pipeline-run",
    response_model=Message,
    summary="Queue a pipeline run (returns immediately)",
)
def enqueue_pipeline_run(
    session: DbSession,
    request: Request,
    user: PipelineUser,
    sources: Annotated[str | None, Query(description="Comma-separated source codes")] = None,
    limit_per_source: Annotated[int | None, Query(ge=1, le=5_000)] = None,
    database: str = "postgres",
    skip_dq: bool = False,
    skip_catalog: bool = False,
    strict: bool = False,
) -> Message:
    """Enqueue a full pipeline run rather than blocking the request on it.

    `POST /pipeline/run/sync` remains available when a caller genuinely needs the
    result inline (the Airflow DAG does).
    """
    handle = queue.enqueue(
        session,
        "pipeline_run",
        {
            "sources": [code.strip() for code in (sources or "").split(",") if code.strip()],
            "database": database,
            "limit_per_source": limit_per_source,
            "skip_dq": skip_dq,
            "skip_catalog": skip_catalog,
            "strict": strict,
            "trigger": "api",
            "created_by": user.email,
        },
        requested_by=user.user_id,
        requested_by_email=user.email,
    )
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="job.enqueue",
            entity_type="app_job",
            entity_id=handle.job_key,
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"job_type": "pipeline_run", "database": database},
        )
    )
    return Message(
        message=f"Pipeline run queued as {handle.job_key}",
        detail={
            "job_id": handle.job_id,
            "job_key": handle.job_key,
            "status": handle.status,
            "href": f"/api/v1/jobs/{handle.job_key}",
        },
    )


@router.post("/backfill", response_model=Message, summary="Queue a historical backfill")
def enqueue_backfill(
    session: DbSession,
    request: Request,
    user: PipelineUser,
    start_date: str,
    end_date: str,
    sources: Annotated[str | None, Query()] = None,
    database: str = "postgres",
    limit_per_source: Annotated[int | None, Query(ge=1, le=5_000)] = None,
    skip_dq: bool = False,
    skip_catalog: bool = False,
    dry_run: bool = False,
) -> Message:
    import datetime as dt

    from app.services.backfill import MAX_BACKFILL_DAYS, plan_backfill

    plan = plan_backfill(
        start_date=dt.date.fromisoformat(start_date),
        end_date=dt.date.fromisoformat(end_date),
        sources=[code.strip() for code in (sources or "").split(",") if code.strip()] or None,
        database=database,
        limit_per_source=limit_per_source,
        skip_dq=skip_dq,
        skip_catalog=skip_catalog,
        dry_run=dry_run,
        created_by=user.email,
    )
    if len(plan.days) > MAX_BACKFILL_DAYS:
        raise ValidationError(f"a backfill may cover at most {MAX_BACKFILL_DAYS} days")

    handle = queue.enqueue(
        session,
        "backfill",
        {**plan.as_dict(), "created_by": user.email},
        requested_by=user.user_id,
        requested_by_email=user.email,
    )
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="job.enqueue",
            entity_type="app_job",
            entity_id=handle.job_key,
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"job_type": "backfill", "backfill_id": plan.backfill_id},
        )
    )
    return Message(
        message=f"Backfill of {len(plan.days)} day(s) queued as {handle.job_key}",
        detail={
            "job_id": handle.job_id,
            "job_key": handle.job_key,
            "backfill_id": plan.backfill_id,
            "href": f"/api/v1/jobs/{handle.job_key}",
        },
    )


@router.post("/export", response_model=Message, summary="Queue a dataset export")
def enqueue_export(
    session: DbSession,
    user: ReadUser,
    dataset: str = "products",
    format: str = "csv",
    row_limit: Annotated[int, Query(ge=1, le=50_000)] = 5_000,
) -> Message:
    if format not in {"csv", "json"}:
        raise ValidationError("format must be csv or json")
    handle = queue.enqueue(
        session,
        "export",
        {"dataset": dataset, "format": format, "row_limit": row_limit},
        requested_by=user.user_id,
        requested_by_email=user.email,
    )
    return Message(
        message=f"Export queued as {handle.job_key}",
        detail={"job_id": handle.job_id, "job_key": handle.job_key, "href": f"/api/v1/jobs/{handle.job_key}"},
    )


@router.get("/stream/jobs", summary="Server-Sent Events: live job progress")
async def stream_jobs(user: CurrentUser) -> StreamingResponse:
    """Live job progress. Auto-reconnecting, with a keep-alive every 25 seconds."""
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
        },
    )


async def _event_stream() -> AsyncIterator[str]:
    """All realtime frames: job progress plus run and notification events."""
    from app.services.realtime import TOPIC_JOB, subscribe_stream

    async for frame in subscribe_stream([TOPIC_JOB]):
        yield frame


__all__ = ["router"]


@router.get("/{reference}", summary="Job status, result and progress events")
def job_detail(reference: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    from app.api.security import at_least

    job = queue.get_job(session, reference)
    if not at_least(user.role, "admin") and job.requested_by not in (None, user.user_id):
        raise PermissionDeniedError("this job belongs to another user")
    return {
        **queue.job_to_dict(job),
        "events": queue.job_events(session, job.job_id),
    }


@router.get("/{reference}/events", summary="Progress events for one job")
def job_events(
    reference: str,
    session: DbSession,
    user: CurrentUser,
    after_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict[str, Any]:
    from app.api.security import at_least

    job = queue.get_job(session, reference)
    if not at_least(user.role, "admin") and job.requested_by not in (None, user.user_id):
        raise PermissionDeniedError("this job belongs to another user")
    return {
        "job_key": job.job_key,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "events": queue.job_events(session, job.job_id, after_id=after_id, limit=limit),
    }


@router.post("/{reference}/cancel", response_model=Message, summary="Cancel a job")
def cancel(reference: str, session: DbSession, request: Request, user: PipelineUser) -> Message:
    from app.api.security import at_least

    job = queue.get_job(session, reference)
    if not at_least(user.role, "admin") and job.requested_by not in (None, user.user_id):
        raise PermissionDeniedError("this job belongs to another user")
    result = queue.cancel_job(session, reference)
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="job.cancel",
            entity_type="app_job",
            entity_id=job.job_key,
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
    )
    return Message(message=f"Cancellation requested for {job.job_key}", detail=result)


@router.post("/{reference}/retry", response_model=Message, summary="Requeue a finished job")
def retry(reference: str, session: DbSession, user: PipelineUser) -> Message:
    from app.api.security import at_least

    job = queue.get_job(session, reference)
    if not at_least(user.role, "admin") and job.requested_by not in (None, user.user_id):
        raise PermissionDeniedError("this job belongs to another user")
    result = queue.retry_job(session, reference)
    return Message(message=f"{job.job_key} requeued", detail=result)


@router.post("/{reference}/run", summary="Run a queued job now (admin, synchronous)")
def run_now(reference: str, session: DbSession, _admin: AdminUser) -> Message:
    """Force the queue to make progress in this process.

    Useful when the worker thread is disabled (tests, a one-off container) or when
    an operator wants to unblock a stalled queue immediately.
    """
    handled = queue.drain()
    job = queue.get_job(session, reference)
    return Message(
        message=f"Drained {handled} job(s)",
        detail={**queue.job_to_dict(job)},
    )


@router.delete("/{reference}", response_model=Message, summary="Delete a finished job")
def delete(reference: str, session: DbSession, _admin: AdminUser) -> Message:
    job = queue.get_job(session, reference)
    if job.status == "running":
        raise ValidationError("cancel the job before deleting it")
    key = job.job_key
    job_id = job.job_id
    session.delete(job)
    session.flush()
    return Message(message=f"Job {key} deleted", detail={"job_id": job_id})
