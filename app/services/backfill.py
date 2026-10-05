"""Historical backfill: replay the pipeline across a date range.

A backfill re-runs ingestion once per day in the range, tagging every run with
``trigger="backfill"`` and a shared ``backfill_id`` so the whole job can be traced,
queried and compared from the API.

Why it is a service and not a route: the job outlives the HTTP request, needs its own
progress tracking, and must keep working when it is driven from Airflow instead.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.models.base import utcnow

log = get_logger(__name__)

MAX_BACKFILL_DAYS = 31


@dataclass
class BackfillPlan:
    """A validated backfill request, expanded into one job per day."""

    backfill_id: str
    start_date: dt.date
    end_date: dt.date
    sources: list[str]
    database: str
    limit_per_source: int | None = None
    skip_dq: bool = False
    skip_catalog: bool = False
    dry_run: bool = False
    created_by: str | None = None
    days: list[dt.date] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "backfill_id": self.backfill_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "sources": list(self.sources),
            "database": self.database,
            "limit_per_source": self.limit_per_source,
            "skip_dq": self.skip_dq,
            "skip_catalog": self.skip_catalog,
            "dry_run": self.dry_run,
            "created_by": self.created_by,
            "days": [day.isoformat() for day in self.days],
            "total_days": len(self.days),
        }


def _as_date(value: Any, field_name: str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip()[:10])
        except ValueError as exc:
            raise ValidationError(
                f"{field_name} must be an ISO date (YYYY-MM-DD)", details={"value": value}
            ) from exc
    raise ValidationError(f"{field_name} is required", details={"value": str(value)})


def plan_backfill(
    *,
    start_date: Any,
    end_date: Any,
    sources: list[str] | None = None,
    database: str = "postgres",
    limit_per_source: int | None = None,
    skip_dq: bool = False,
    skip_catalog: bool = False,
    dry_run: bool = False,
    created_by: str | None = None,
) -> BackfillPlan:
    """Validate the request and expand it into a per-day plan.

    Raises ``ValidationError`` for reversed ranges, future dates or oversized jobs.
    """
    start = _as_date(start_date, "start_date")
    end = _as_date(end_date, "end_date")
    if end < start:
        raise ValidationError(
            "end_date must not be before start_date",
            details={"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
    span = (end - start).days + 1
    if span > MAX_BACKFILL_DAYS:
        raise ValidationError(
            f"backfill is limited to {MAX_BACKFILL_DAYS} days per job",
            details={"requested_days": span, "max_days": MAX_BACKFILL_DAYS},
        )
    today = utcnow().date()
    if end > today:
        raise ValidationError("end_date cannot be in the future", details={"today": today.isoformat()})

    days = [start + dt.timedelta(days=offset) for offset in range(span)]
    return BackfillPlan(
        backfill_id=f"bf_{uuid.uuid4().hex[:12]}",
        start_date=start,
        end_date=end,
        sources=list(sources or []),
        database=database,
        limit_per_source=limit_per_source,
        skip_dq=skip_dq,
        skip_catalog=skip_catalog,
        dry_run=dry_run,
        created_by=created_by,
        days=days,
    )


def execute_backfill(plan: BackfillPlan) -> dict[str, Any]:
    """Run the pipeline once per planned day and summarise the outcome.

    Each day is independent: a failure is recorded and the job continues, because a
    single bad day must not abandon the rest of the range.
    """
    from app.etl.pipeline import Pipeline, PipelineConfig

    runs: list[dict[str, Any]] = []
    started = utcnow()

    for day in plan.days:
        config = PipelineConfig(
            sources=list(plan.sources),
            database=plan.database,
            limit_per_source=plan.limit_per_source,
            skip_dq=plan.skip_dq,
            skip_catalog=plan.skip_catalog,
            trigger="backfill",
            created_by=plan.created_by or "backfill",
            run_key=f"{plan.backfill_id}:{day.isoformat()}",
            dry_run=plan.dry_run,
        )
        entry: dict[str, Any] = {"date": day.isoformat()}
        try:
            result = Pipeline(config).run()
            counters = result.counters or {}
            quality = result.quality or {}
            entry |= {
                "run_id": result.run_id,
                "status": result.status,
                # PipelineResult.counters uses its own names; map them to the API shape
                "records_extracted": counters.get("staged"),
                "records_valid": counters.get("snapshots_inserted"),
                "records_rejected": counters.get("rejected"),
                "new_products": counters.get("new_products"),
                "price_changes": counters.get("price_changes"),
                "removed_products": counters.get("removed_products"),
                "dq_score": quality.get("score"),
            }
        except Exception as exc:  # noqa: BLE001 - one bad day must not stop the job
            log.exception("backfill %s failed for %s", plan.backfill_id, day)
            entry |= {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        runs.append(entry)
        log.info("backfill %s day=%s status=%s", plan.backfill_id, day, entry.get("status"))

    finished = utcnow()
    succeeded = [run for run in runs if run.get("status") in {"success", "partial"}]
    failed = [run for run in runs if run.get("status") == "failed"]
    return {
        "backfill_id": plan.backfill_id,
        "status": "success" if not failed else ("partial" if succeeded else "failed"),
        "planned_days": len(plan.days),
        "succeeded_days": len(succeeded),
        "failed_days": len(failed),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "runs": runs,
    }


def backfill_runs(session: Session, backfill_id: str) -> list[dict[str, Any]]:
    """Every pipeline run belonging to a backfill job, oldest first."""
    rows = session.execute(
        sa.text(
            """
            SELECT run_id, status, trigger, started_at, finished_at, duration_ms,
                   records_extracted, records_valid, records_rejected, new_products,
                   price_changes, removed_products, dq_score, run_key, error_message
            FROM etl_run
            WHERE run_key LIKE :prefix
            ORDER BY started_at
            """
        ),
        {"prefix": f"{backfill_id}:%"},
    ).mappings()
    return [dict(row) for row in rows]


def backfill_progress(session: Session, backfill_id: str) -> dict[str, Any]:
    """Aggregate progress for a backfill, derived from its runs."""
    runs = backfill_runs(session, backfill_id)
    if not runs:
        return {"backfill_id": backfill_id, "found": False, "runs": []}

    statuses = [run.get("status") for run in runs]
    failed = sum(1 for status in statuses if status == "failed")
    succeeded = sum(1 for status in statuses if status in {"success", "partial"})
    scores = [run["dq_score"] for run in runs if run.get("dq_score") is not None]
    return {
        "backfill_id": backfill_id,
        "found": True,
        "status": "success" if not failed else ("partial" if succeeded else "failed"),
        "total_runs": len(runs),
        "succeeded_runs": succeeded,
        "failed_runs": failed,
        "records_extracted": sum(run.get("records_extracted") or 0 for run in runs),
        "records_valid": sum(run.get("records_valid") or 0 for run in runs),
        "new_products": sum(run.get("new_products") or 0 for run in runs),
        "price_changes": sum(run.get("price_changes") or 0 for run in runs),
        "removed_products": sum(run.get("removed_products") or 0 for run in runs),
        "average_dq_score": round(sum(scores) / len(scores), 4) if scores else None,
        "runs": runs,
    }


def list_backfills(session: Session, limit: int = 25) -> list[dict[str, Any]]:
    """Recent backfill jobs with rolled-up counts, newest first.

    Runs are tagged ``<backfill_id>:<date>``, so the roll-up is done in Python: string
    slicing on ``run_key`` behaves the same on PostgreSQL, MySQL and SQLite, whereas the
    equivalent SQL substring functions do not.
    """
    rows = session.execute(
        sa.text(
            """
            SELECT run_key,
                   status,
                   COALESCE(records_extracted, 0) AS records_extracted,
                   started_at,
                   finished_at
            FROM etl_run
            WHERE run_key LIKE 'bf\\_%'
            ORDER BY started_at DESC
            """
        )
    ).mappings()

    jobs: dict[str, dict[str, Any]] = {}
    for row in rows:
        job_id = str(row["run_key"]).split(":", 1)[0]
        job = jobs.get(job_id)
        if job is None:
            job = jobs[job_id] = {
                "backfill_id": job_id,
                "total_runs": 0,
                "failed_runs": 0,
                "records_extracted": 0,
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
            }
        job["total_runs"] += 1
        job["records_extracted"] += row["records_extracted"] or 0
        if row["status"] == "failed":
            job["failed_runs"] += 1
        if job["started_at"] is None or (
            row["started_at"] is not None and row["started_at"] < job["started_at"]
        ):
            job["started_at"] = row["started_at"]
        if job["finished_at"] is None or (
            row["finished_at"] is not None and row["finished_at"] > job["finished_at"]
        ):
            job["finished_at"] = row["finished_at"]

    for job in jobs.values():
        failed = job["failed_runs"]
        total = job["total_runs"]
        job["status"] = "success" if not failed else ("partial" if total > failed else "failed")

    return sorted(jobs.values(), key=lambda job: job["started_at"] or dt.datetime.min, reverse=True)[:limit]


__all__ = [
    "MAX_BACKFILL_DAYS",
    "BackfillPlan",
    "backfill_progress",
    "backfill_runs",
    "execute_backfill",
    "list_backfills",
    "plan_backfill",
]
