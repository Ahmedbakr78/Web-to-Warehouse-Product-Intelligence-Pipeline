"""Durable background job queue.

Replaces FastAPI's ``BackgroundTasks`` for anything that can outlive a request.
A job is a row in ``app_job``, so it survives a process restart, is visible in the
dashboard, and can be cancelled or retried by an operator.

Design
------
* **Durable.** State lives in the database, never in memory.
* **Leased.** A worker claims a job by writing its own id and a lease expiry. A
  worker that dies loses the lease, and the job becomes claimable again rather
  than being stuck in ``running`` forever.
* **Heartbeated.** Long jobs extend their lease as they go, so a healthy job is
  never stolen.
* **Cooperative cancellation.** A cancellable job polls ``cancel_requested``
  between units of work.
* **Observable.** Every stage transition appends an ``AppJobEvent`` row, which the
  SSE endpoint streams to the browser.

The worker is a daemon thread started on application startup. Set
``JOB_WORKER_ENABLED=false`` to run without it (for example in tests).
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import session_scope
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.app_users import AppJob, AppJobEvent

log = get_logger(__name__)


def _publish(data: dict[str, Any], topics: tuple[str, ...] = ()) -> None:
    """Push a job event to connected clients. Never raises.

    `topics` lets a job also announce itself on a domain topic, so a client watching
    only `/stream/runs` still sees a pipeline run progress.
    """
    try:
        from app.services.realtime import TOPIC_JOB, TOPIC_RUN, publish

        publish(TOPIC_JOB, data)
        if data.get("job_type") == "pipeline_run" or not topics:
            publish(TOPIC_RUN, data)
        else:
            for topic in topics:
                publish(topic, data)
    except Exception as exc:  # noqa: BLE001 - realtime must never break a job
        log.debug("realtime publish failed: %s", exc)


#: How often a running worker extends its lease.
HEARTBEAT_SECONDS = 15
#: Idle poll interval for the worker loop.
POLL_SECONDS = 1.0


def lease_seconds() -> int:
    """Lease duration, configurable via ``JOB_LEASE_SECONDS``."""
    return max(10, int(settings.job_lease_seconds))


#: Jobs that can be cancelled cooperatively, checked between units of work.
CANCELLABLE = frozenset({"pipeline_run", "backfill", "export", "forecast"})


@dataclass(frozen=True)
class JobHandle:
    """What the caller gets back when it enqueues work."""

    job_id: int
    job_key: str
    status: str


def _publish_progress(
    job_id: int,
    message: str,
    *,
    level: str,
    stage: str | None,
    progress_pct: int | None,
) -> None:
    """Push a progress line over the broker only, with no database write."""
    _publish(
        {
            "kind": "job_progress",
            "job_id": job_id,
            "message": message,
            "level": level,
            "stage": stage,
            "progress_pct": progress_pct,
        },
    )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def jsonable(value: Any) -> Any:
    """Make a handler result safe to store in a JSON column.

    Pipeline and backfill results carry `datetime`, `date`, `Decimal` and `timedelta`
    objects, none of which SQLAlchemy's JSON type can serialise. Converting them here
    (rather than in each handler) keeps every handler free of serialisation concerns.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return str(value)


def new_job_key(prefix: str = "job") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def enqueue(
    session: Session,
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    requested_by: int | None = None,
    requested_by_email: str | None = None,
    max_attempts: int = 3,
) -> JobHandle:
    """Insert a queued job and return its handle. Does not start any work."""
    job = AppJob(
        job_key=new_job_key(job_type),
        job_type=job_type,
        status="queued",
        payload=payload or {},
        requested_by=requested_by,
        requested_by_email=requested_by_email,
        max_attempts=max_attempts,
        attempt=0,
        progress_pct=0,
    )
    session.add(job)
    session.flush()
    log.info("job %s queued (%s)", job.job_key, job_type)
    return JobHandle(job_id=job.job_id, job_key=job.job_key, status=job.status)


def log_event(
    session: Session,
    job_id: int,
    message: str,
    *,
    level: str = "info",
    stage: str | None = None,
    progress_pct: int | None = None,
) -> None:
    """Append a progress line and mirror it onto the job row."""
    session.add(
        AppJobEvent(
            job_id=job_id,
            level=level,
            stage=stage,
            message=message,
            progress_pct=progress_pct,
        )
    )
    job = session.get(AppJob, job_id)
    if job is not None:
        job.stage = stage or job.stage
        if progress_pct is not None:
            job.progress_pct = max(0, min(100, int(progress_pct)))
        key, status, job_type = job.job_key, job.status, job.job_type
    else:
        key, status, job_type = "", "", ""
    session.flush()
    _publish(
        {
            "kind": "job_progress",
            "job_id": job_id,
            "job_key": key,
            "job_type": job_type,
            "status": status,
            "level": level,
            "stage": stage,
            "message": message,
            "progress_pct": progress_pct,
        },
    )


def get_job(session: Session, reference: str) -> AppJob:
    """Look a job up by numeric id or by its opaque key."""
    job: AppJob | None = None
    if str(reference).isdigit():
        job = session.get(AppJob, int(reference))
    if job is None:
        job = session.execute(sa.select(AppJob).where(AppJob.job_key == str(reference))).scalars().first()
    if job is None:
        raise NotFoundError(f"job '{reference}' not found")
    return job


def job_events(session: Session, job_id: int, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            sa.select(AppJobEvent)
            .where(AppJobEvent.job_id == job_id, AppJobEvent.event_id > after_id)
            .order_by(AppJobEvent.event_id)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "event_id": row.event_id,
            "level": row.level,
            "stage": row.stage,
            "message": row.message,
            "progress_pct": row.progress_pct,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def job_to_dict(job: AppJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "job_key": job.job_key,
        "job_type": job.job_type,
        "status": job.status,
        "stage": job.stage,
        "progress_pct": job.progress_pct,
        "payload": job.payload or {},
        "result": job.result or {},
        "error": job.error,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "requested_by_email": job.requested_by_email,
        "queued_at": job.queued_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "cancel_requested": job.cancel_requested,
    }


def list_jobs(
    session: Session,
    *,
    status: str | None = None,
    job_type: str | None = None,
    requested_by: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = sa.select(AppJob)
    if status:
        stmt = stmt.where(AppJob.status == status)
    if job_type:
        stmt = stmt.where(AppJob.job_type == job_type)
    if requested_by is not None:
        stmt = stmt.where(AppJob.requested_by == requested_by)
    rows = session.execute(stmt.order_by(AppJob.queued_at.desc()).limit(limit)).scalars().all()
    return [job_to_dict(row) for row in rows]


def cancel_job(session: Session, reference: str) -> dict[str, Any]:
    """Request cancellation.

    A queued job stops immediately. A running cancellable job is flagged and stops
    at its next checkpoint; a running job that is not cancellable is reported as
    such rather than silently ignored.
    """
    job = get_job(session, reference)
    if job.status in {"succeeded", "failed", "cancelled"}:
        raise ConflictError(f"job {job.job_key} has already finished ({job.status})")
    job.cancel_requested = True
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = _utcnow()
        log.info("job %s cancelled before starting", job.job_key)
    elif job.job_type not in CANCELLABLE:
        log.warning("job %s (%s) cannot be cancelled mid-run", job.job_key, job.job_type)
    return job_to_dict(job)


def is_cancelled(session_factory: Callable[[], Any], job_id: int) -> bool:
    """Cheap cooperative-cancellation check used between units of work."""
    with session_factory() as session:
        job = session.get(AppJob, job_id)
        return bool(job and job.cancel_requested)


def retry_job(session: Session, reference: str) -> dict[str, Any]:
    job = get_job(session, reference)
    if job.status == "running":
        raise ConflictError(f"job {job.job_key} is still running")
    job.status = "queued"
    job.error = None
    job.finished_at = None
    job.cancel_requested = False
    job.progress_pct = 0
    job.stage = None
    job.attempt = 0
    log.info("job %s requeued", job.job_key)
    return job_to_dict(job)


# --------------------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------------------

#: A handler receives a "report" callable and returns the job result dict.
Handler = Callable[[int, Callable[..., None]], dict[str, Any]]


def _handlers() -> dict[str, Handler]:
    """Job type -> handler. Imported lazily so the module has no import cycle."""
    from app.jobs import handlers

    return handlers.REGISTRY


def claim_next(database: str | None, owner: str) -> AppJob | None:
    """Atomically claim one runnable job, or return None.

    Runnable means queued, or running with an expired lease. The claim is a single
    conditional UPDATE so two workers cannot take the same row.
    """
    now = _utcnow()
    with session_scope(database) as session:
        candidate = (
            session.execute(
                sa.select(AppJob)
                .where(
                    sa.or_(
                        AppJob.status == "queued",
                        sa.and_(AppJob.status == "running", AppJob.lease_expires_at < now),
                    )
                )
                .order_by(AppJob.queued_at)
                .limit(1)
            )
            .scalars()
            .first()
        )
        if candidate is None:
            return None
        job_id = candidate.job_id
        result = session.execute(
            sa.update(AppJob)  # type: ignore[arg-type]
            .where(AppJob.job_id == job_id, AppJob.status == candidate.status)
            .values(
                status="running",
                lease_owner=owner,
                lease_expires_at=now + dt.timedelta(seconds=lease_seconds()),
                heartbeat_at=now,
                started_at=candidate.started_at or now,
                attempt=AppJob.attempt + 1,
            )
        )
        if not result.rowcount:  # type: ignore[attr-defined]
            # Another worker won the race; try again on the next poll.
            return None
        job = session.get(AppJob, job_id)
        return job


def _execute(job_id: int, handler: Handler, database: str | None) -> None:
    """Run one handler, streaming progress live and persisting it in one batch.

    Progress is delivered immediately over the in-memory broker, but written to
    `app_job_event` only when the handler returns. Writing each line as it happens
    would open a second connection while the handler still holds its own transaction:
    SQLite refuses that outright ("database is locked"), and on PostgreSQL it costs a
    round trip per stage for data that is only ever read back as history.
    """
    pending: list[dict[str, Any]] = []

    def flush() -> None:
        if not pending:
            return
        batch, pending[:] = list(pending), []
        try:
            with session_scope(database) as session:
                job = session.get(AppJob, job_id)
                if job is None:
                    return
                for item in batch:
                    session.add(
                        AppJobEvent(
                            job_id=job_id,
                            level=item["level"],
                            stage=item["stage"],
                            message=item["message"],
                            progress_pct=item["progress_pct"],
                        )
                    )
                    job.stage = item["stage"] or job.stage
                    if item["progress_pct"] is not None:
                        job.progress_pct = max(0, min(100, int(item["progress_pct"])))
        except Exception as exc:  # noqa: BLE001 - an audit trail must never fail a job
            log.warning("could not persist progress events for job %s: %s", job_id, exc)

    def report(
        message: str, *, stage: str | None = None, progress_pct: int | None = None, level: str = "info"
    ) -> None:
        pending.append({"message": message, "stage": stage, "progress_pct": progress_pct, "level": level})
        _publish_progress(job_id, message, level=level, stage=stage, progress_pct=progress_pct)

    try:
        report("job started", stage="start", progress_pct=0)
        result = handler(job_id, report) or {}
        flush()

        with session_scope(database) as session:
            job = session.get(AppJob, job_id)
            if job is not None:
                job.result = jsonable(result)
                job.status = "succeeded"
                job.progress_pct = 100
                job.stage = "done"
                job.finished_at = _utcnow()
                job.lease_owner = None
                job.lease_expires_at = None
                session.add(
                    AppJobEvent(
                        job_id=job_id, level="info", stage="done", message="job finished", progress_pct=100
                    )
                )
        log.info("job %s succeeded", job_id)
    except Exception as exc:  # noqa: BLE001 - a worker must never die on one job
        flush()
        with session_scope(database) as session:
            job = session.get(AppJob, job_id)
            if job is not None:
                message = f"{type(exc).__name__}: {exc}"
                job.error = message[:2000]
                job.lease_owner = None
                job.lease_expires_at = None
                job.finished_at = _utcnow()
                if job.attempt < job.max_attempts:
                    # Requeue for another attempt rather than failing outright.
                    job.status = "queued"
                    job.finished_at = None
                    session.add(
                        AppJobEvent(
                            job_id=job_id,
                            level="warning",
                            stage="retry",
                            message=f"attempt {job.attempt}/{job.max_attempts} failed: {message}",
                        )
                    )
                else:
                    job.status = "failed"
                    session.add(
                        AppJobEvent(
                            job_id=job_id,
                            level="error",
                            stage="failed",
                            message=f"failed: {message}",
                        )
                    )
        log.warning("job %s failed or will retry: %s", job_id, exc)


def _heartbeat(job_id: int, database: str | None) -> None:
    """Extend the lease so a healthy long job is never reclaimed."""
    now = _utcnow()
    try:
        with session_scope(database) as session:
            session.execute(
                sa.update(AppJob)
                .where(AppJob.job_id == job_id, AppJob.status == "running")
                .values(heartbeat_at=now, lease_expires_at=now + dt.timedelta(seconds=lease_seconds()))
            )
    except Exception as exc:  # noqa: BLE001 - heartbeats are best-effort
        log.debug("heartbeat for job %s failed: %s", job_id, exc)


def drain(database: str | None = None, owner: str | None = None, limit: int = 100) -> int:
    """Run queued jobs in the calling thread. Returns how many completed.

    This is the synchronous entry point used by tests and by `pip serve --sync`.
    """
    worker_id = owner or f"drain-{uuid.uuid4().hex[:8]}"
    handled = 0
    for _ in range(limit):
        job = claim_next(database, worker_id)
        if job is None:
            break
        handler = _handlers().get(job.job_type)
        if handler is None:
            with session_scope(database) as session:
                row = session.get(AppJob, job.job_id)
                if row is not None:
                    row.status = "failed"
                    row.error = f"no handler registered for job type '{job.job_type}'"
                    row.finished_at = _utcnow()
                    row.lease_owner = None
                    row.lease_expires_at = None
                    log_event(session, row.job_id, row.error, level="error", stage="failed")
            continue
        _execute(job.job_id, handler, database)
        handled += 1
    return handled


class JobWorker:
    """Background daemon that polls for work and runs it."""

    def __init__(self, database: str | None = None, interval: float = POLL_SECONDS) -> None:
        self.database = database
        self.interval = interval
        self.owner = f"worker-{uuid.uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)
        self._thread.start()
        log.info("job worker %s started", self.owner)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        log.info("job worker %s stopped", self.owner)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run_with_heartbeat(self, job_id: int, handler: Handler) -> None:
        """Execute a handler while a companion thread keeps its lease fresh."""
        stop_beat = threading.Event()

        def beat() -> None:
            while not stop_beat.wait(HEARTBEAT_SECONDS):
                _heartbeat(job_id, self.database)

        beater = threading.Thread(target=beat, name=f"heartbeat-{job_id}", daemon=True)
        beater.start()
        try:
            _execute(job_id, handler, self.database)
        finally:
            stop_beat.set()
            beater.join(timeout=1.0)

    def _loop(self) -> None:
        handlers = _handlers()
        while not self._stop.is_set():
            try:
                job = claim_next(self.database, self.owner)
            except Exception as exc:  # noqa: BLE001 - the loop must survive a DB blip
                log.warning("job worker could not poll: %s", exc)
                self._stop.wait(self.interval * 5)
                continue
            if job is None:
                self._stop.wait(self.interval)
                continue
            handler = handlers.get(job.job_type)
            if handler is None:
                with session_scope(self.database) as session:
                    row = session.get(AppJob, job.job_id)
                    if row is not None:
                        row.status = "failed"
                        row.error = f"no handler registered for job type '{job.job_type}'"
                        row.finished_at = _utcnow()
                        row.lease_owner = None
                        row.lease_expires_at = None
                continue
            # Keep the lease alive for as long as the handler runs. The thread and
            # its stop flag are passed as arguments rather than captured from the loop.
            self._run_with_heartbeat(job.job_id, handler)


_WORKER: JobWorker | None = None


def get_worker(database: str | None = None) -> JobWorker:
    """The process-wide worker, created on first use."""
    global _WORKER
    if _WORKER is None:
        _WORKER = JobWorker(database)
    return _WORKER


def start_worker(database: str | None = None) -> JobWorker | None:
    if not settings.job_worker_enabled:
        log.info("job worker disabled by configuration (JOB_WORKER_ENABLED=false)")
        return None
    worker = get_worker(database)
    worker.start()
    return worker


def stop_worker() -> None:
    global _WORKER
    if _WORKER is not None:
        _WORKER.stop()
        _WORKER = None


def worker_status() -> dict[str, Any]:
    worker = _WORKER
    return {
        "enabled": settings.job_worker_enabled,
        "running": bool(worker and worker.running),
        "owner": worker.owner if worker else None,
        "cancellable_types": sorted(CANCELLABLE),
        "lease_seconds": lease_seconds(),
    }


__all__ = [
    "CANCELLABLE",
    "JobHandle",
    "JobWorker",
    "cancel_job",
    "drain",
    "enqueue",
    "get_job",
    "get_worker",
    "is_cancelled",
    "job_events",
    "job_to_dict",
    "jsonable",
    "list_jobs",
    "log_event",
    "retry_job",
    "start_worker",
    "stop_worker",
    "worker_status",
]
