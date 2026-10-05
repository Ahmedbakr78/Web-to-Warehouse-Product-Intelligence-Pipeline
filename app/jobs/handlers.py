"""Job handlers, one per `app_job.job_type`.

Each handler has the signature ``(job_id, report) -> result dict`` and is
responsible for calling ``report(...)`` as it makes progress. The queue owns
retries, leases and persistence; a handler only does the work and raises on
failure.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from app.core.db import session_scope
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.jobs import queue
from app.models.app_users import AppJob

log = get_logger(__name__)

Report = Callable[..., None]

#: job_type -> handler
REGISTRY: dict[str, Callable[[int, Report], dict[str, Any]]] = {}

#: The pipeline stages, used to translate a stage callback into a percentage.
STAGES = (
    "extract",
    "stage",
    "transform",
    "resolve",
    "load",
    "detect",
    "reconcile",
    "quality",
    "aggregate",
)


def job_type(
    name: str,
) -> Callable[[Callable[[int, Report], dict[str, Any]]], Callable[[int, Report], dict[str, Any]]]:
    """Register a handler for a job type."""

    def decorate(func: Callable[[int, Report], dict[str, Any]]) -> Callable[[int, Report], dict[str, Any]]:
        REGISTRY[name] = func
        return func

    return decorate


def _payload(job_id: int) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(AppJob, job_id)
        return dict(job.payload or {}) if job is not None else {}


def _should_stop(job_id: int) -> bool:
    return queue.is_cancelled(session_scope, job_id)


@job_type("pipeline_run")
def run_pipeline(job_id: int, report: Report) -> dict[str, Any]:
    """Execute one full pipeline run, reporting each stage."""
    from app.etl.pipeline import Pipeline, PipelineConfig

    payload = _payload(job_id)
    config = PipelineConfig(
        sources=payload.get("sources") or [],
        database=payload.get("database") or "postgres",
        limit_per_source=payload.get("limit_per_source"),
        skip_dq=payload.get("skip_dq", False),
        skip_catalog=payload.get("skip_catalog", False),
        strict=payload.get("strict", False),
        skip_removed=payload.get("skip_removed", False),
        stale_after_days=payload.get("stale_after_days", 7),
        trigger=payload.get("trigger", "job"),
        created_by=payload.get("created_by"),
    )
    if not config.sources:
        from app.ingestion.base import list_sources

        config.sources = [source["code"] for source in list_sources() if source["enabled"]]

    # Stage timings are written by the pipeline; poll the run row so progress is real.
    seen_stages: list[str] = []

    def on_stage(stage: str, detail: str = "") -> None:
        seen_stages.append(stage)
        index = STAGES.index(stage) if stage in STAGES else len(seen_stages)
        report(
            f"{stage}: {detail or 'running'}",
            stage=stage,
            progress_pct=round((index + 1) / len(STAGES) * 100),
        )

    report("pipeline starting", stage="start", progress_pct=0)
    pipeline = Pipeline(config, on_stage=on_stage)
    result = pipeline.run()
    report("pipeline finished", stage="done", progress_pct=100)
    return result.as_dict()


@job_type("backfill")
def run_backfill(job_id: int, report: Report) -> dict[str, Any]:
    """Replay a date range, one run per day, stopping early if cancelled."""
    from app.services.backfill import BackfillPlan, execute_backfill

    payload = _payload(job_id)
    days = [dt.date.fromisoformat(value) for value in payload.get("days", [])]
    if not days:
        raise ValueError("backfill job has no days to replay")
    plan = BackfillPlan(
        backfill_id=payload.get("backfill_id") or queue.new_job_key("backfill"),
        start_date=min(days),
        end_date=max(days),
        sources=payload.get("sources") or [],
        database=payload.get("database") or "postgres",
        limit_per_source=payload.get("limit_per_source"),
        skip_dq=payload.get("skip_dq", False),
        skip_catalog=payload.get("skip_catalog", False),
        dry_run=payload.get("dry_run", False),
        created_by=payload.get("created_by"),
        days=days,
    )
    total = len(days)
    report(f"replaying {total} day(s)", stage="start", progress_pct=0)

    done = 0

    def on_day(day: dt.date, entry: dict[str, Any]) -> None:
        nonlocal done
        done += 1
        level = "warning" if entry.get("status") == "failed" else "info"
        report(
            f"day {done}/{total} ({day.isoformat()}): {entry.get('status')}",
            level=level,
            stage="replay",
            progress_pct=round(done / total * 100) if total else 100,
        )

    def guard(day: dt.date) -> None:
        """Stop at a day boundary when an operator cancels the job."""
        if _should_stop(job_id):
            raise ValidationError(f"backfill cancelled before {day.isoformat()}")

    summary = execute_backfill(plan, on_day=on_day, before_day=guard)
    report("backfill finished", stage="done", progress_pct=100)
    return summary


@job_type("export")
def run_export(job_id: int, report: Report) -> dict[str, Any]:
    """Write a dataset export to disk and record where it landed."""
    from app.services.exporter import fetch_rows, filename_for, to_csv, to_json

    payload = _payload(job_id)
    fmt = payload.get("format", "csv")
    if fmt not in {"csv", "json"}:
        raise ValueError(f"unsupported export format '{fmt}'")

    report("querying dataset", stage="query", progress_pct=10)
    with session_scope() as session:
        dataset, rows = fetch_rows(
            session,
            payload.get("dataset", "products"),
            payload.get("filters") or {},
            int(payload.get("row_limit", 5_000)),
        )

    report(f"serialising {len(rows)} row(s) to {fmt.upper()}", stage="serialise", progress_pct=60)
    body = (
        to_csv(rows, dataset.columns)
        if fmt == "csv"
        else to_json(rows, dataset, int(payload.get("row_limit", 5_000)))
    )

    from app.core.config import settings

    target_dir = settings.artifacts_dir / "exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename_for(dataset, fmt)
    path.write_text(body, encoding="utf-8")

    report("export written", stage="done", progress_pct=100)
    return {
        "dataset": dataset.key,
        "format": fmt,
        "rows": len(rows),
        "bytes": path.stat().st_size,
        "path": str(path),
        "filename": path.name,
    }


@job_type("forecast")
def run_forecast(job_id: int, report: Report) -> dict[str, Any]:
    """Recompute price forecasts and write them to var/artifacts as JSON.

    The result is a file rather than a warehouse table on purpose: a forecast is a
    derived artefact that is fully reproducible from the snapshots already stored, and
    a table would add a migration and a staleness problem for no analytical gain.
    """
    import json

    from app.analytics.forecast import forecast_all
    from app.core.config import settings

    payload = _payload(job_id)
    horizon = int(payload.get("horizon", 14))
    product_id = payload.get("product_id")

    report("forecasting price series", stage="forecast", progress_pct=20)
    with session_scope() as session:
        if product_id:
            from app.analytics.forecast import forecast_product

            forecasts = [forecast_product(session, int(product_id), horizon=horizon)]
        else:
            forecasts = forecast_all(session, horizon=horizon)

    report(f"{len(forecasts)} forecast(s) computed", stage="serialise", progress_pct=80)
    target = settings.artifacts_dir / "forecasts"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"forecasts-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}.json"
    path.write_text(
        json.dumps(
            {
                "horizon": horizon,
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "forecasts": [item.as_dict() for item in forecasts],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    report("forecasts written", stage="done", progress_pct=100)
    return {"computed": len(forecasts), "horizon": horizon, "path": str(path)}


@job_type("rebuild_aggregates")
def run_rebuild_aggregates(job_id: int, report: Report) -> dict[str, Any]:
    """Refresh the category/day rollup for the latest run."""
    import sqlalchemy as sa

    from app.etl.loader import WarehouseLoader
    from app.models.operations import EtlRun

    payload = _payload(job_id)
    with session_scope(payload.get("database")) as session:
        run = session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)).scalars().first()
        if run is None:
            raise NotFoundError("no pipeline run found")
        report(f"rebuilding aggregates for {run.run_id}", stage="aggregate", progress_pct=50)
        written = WarehouseLoader(session, run.run_id).refresh_category_daily()
    report("aggregates rebuilt", stage="done", progress_pct=100)
    return {"run_id": run.run_id, "rows": written}


__all__ = ["REGISTRY", "STAGES", "job_type"]
