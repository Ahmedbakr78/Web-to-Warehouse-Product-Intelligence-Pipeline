"""Pipeline endpoints: list runs, inspect a run, trigger a new run, stage timings."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Query, Request

from app.analytics import service as analytics
from app.api.deps import DbSession, OptionalUser, PaginationDep, PipelineUser, ReadUser, request_meta
from app.api.schemas import (
    BackfillRequest,
    BackfillResult,
    Message,
    Page,
    PipelineRunRead,
    PipelineTriggerRequest,
)
from app.core.errors import NotFoundError, PipelineError
from app.core.logging import get_logger
from app.models.app_users import AppAuditLog, AppNotification
from app.models.operations import DqRuleResult, EtlRun

log = get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/runs", response_model=Page[PipelineRunRead], summary="List pipeline runs")
def runs(
    session: DbSession, pagination: PaginationDep, _user: ReadUser, status: str | None = None
) -> Page[PipelineRunRead]:
    where = "WHERE 1 = 1"
    params: dict[str, Any] = {}
    if status:
        where += " AND status = :status"
        params["status"] = status
    total = session.execute(sa.text(f"SELECT COUNT(*) FROM etl_run {where}"), params).scalar() or 0
    rows = (
        session.execute(
            sa.text(
                f"""
            SELECT run_id, status, run_trigger, target_database, started_at, finished_at, duration_ms,
                   records_extracted, records_valid, records_rejected, records_inserted,
                   records_updated, duplicates_merged, new_products, price_changes, removed_products,
                   catalog_matched, dq_score, yield_pct, dag_id, task_id, error_message
            FROM vw_pipeline_health {where}
            ORDER BY started_at DESC
            LIMIT :limit OFFSET :offset
            """
            ),
            {**params, "limit": pagination.page_size, "offset": pagination.offset},
        )
        .mappings()
        .all()
    )
    items = [dict(row) | {"trigger": row["run_trigger"]} for row in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/runs/latest", summary="Most recent run (full detail)")
def latest_run(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    row = session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)).scalars().first()
    if row is None:
        return {}
    return analytics.run_detail(session, row.run_id)


@router.get(
    "/runs/compare",
    summary="Compare two runs (metric deltas, DQ regressions, catalogue and price movement)",
)
def compare_runs(
    session: DbSession,
    _user: ReadUser,
    base: str = Query(..., description="Reference (earlier) run id"),
    target: str = Query(..., description="Run being judged (usually the newer one)"),
    sample_limit: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    # NOTE: this static route must stay above "/runs/{run_id}": Starlette matches
    # routes in definition order, so otherwise "compare" is captured as a run_id
    # and the UI receives {} (which crashes on diff.target.records_valid).
    diff = analytics.compare_runs(session, base, target, sample_limit=sample_limit)
    if not diff:
        raise NotFoundError("one or both runs were not found", details={"base": base, "target": target})
    return diff


@router.get("/runs/{run_id}", summary="Run detail with DQ, HTTP audit and reconciliation")
def run_detail(run_id: str, session: DbSession, _user: ReadUser) -> dict[str, Any]:
    detail = analytics.run_detail(session, run_id)
    if not detail:
        return {}
    return detail


@router.get("/runs/{run_id}/dq", summary="DQ rule results for one run")
def run_dq(run_id: str, session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            sa.select(DqRuleResult).where(DqRuleResult.run_id == run_id).order_by(DqRuleResult.rule_code)
        )
        .scalars()
        .all()
    )
    return [
        {
            "rule_code": row.rule_code,
            "rule_name": row.rule_name,
            "dimension": row.dimension,
            "severity": row.severity,
            "status": row.status,
            "observed_value": row.observed_value,
            "expected_value": row.expected_value,
            "records_checked": row.records_checked,
            "records_failed": row.records_failed,
            "pass_rate_pct": row.pass_rate_pct,
            "message": row.message,
            "evaluated_at": row.evaluated_at,
        }
        for row in rows
    ]


@router.get("/runs/{run_id}/http", summary="HTTP compliance log for one run")
def run_http(run_id: str, session: DbSession, _user: ReadUser, limit: int = 200) -> list[dict[str, Any]]:
    return analytics.http_log(session, limit=limit, run_id=run_id)


@router.post("/run", summary="Trigger a pipeline run (background)")
def trigger(
    payload: PipelineTriggerRequest,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    user: PipelineUser,
) -> dict[str, Any]:
    from app.etl.pipeline import PipelineConfig

    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="pipeline.run",
            entity_type="etl_run",
            status="accepted",
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={
                "sources": payload.sources,
                "database": payload.database,
                "trigger": payload.trigger,
                "dag_id": payload.dag_id,
                "task_id": payload.task_id,
            },
        )
    )
    session.add(
        AppNotification(
            user_id=user.user_id,
            level="info",
            title="Pipeline run queued",
            body=f"Sources: {', '.join(payload.sources) if payload.sources else 'all enabled'}",
            entity_type="pipeline",
            action_url="/pipeline",
        )
    )

    config = PipelineConfig(
        sources=payload.sources or [],
        database=payload.database,
        limit_per_source=payload.limit_per_source,
        strict=payload.strict,
        skip_dq=payload.skip_dq,
        skip_catalog=payload.skip_catalog,
        trigger=payload.trigger or "api",
        created_by=user.email,
    )
    background.add_task(_execute_run, config)
    return {
        "status": "queued",
        "message": "Pipeline execution scheduled in the background",
        "config": config.as_dict(),
    }


def _execute_run(config: Any) -> None:
    """Background task body (runs after the HTTP response has been sent)."""
    from app.etl.pipeline import Pipeline

    try:
        result = Pipeline(config).run()
        log.info("api triggered pipeline finished run=%s status=%s", result.run_id, result.status)
    except PipelineError as exc:  # pragma: no cover - defensive
        log.error("api triggered pipeline failed: %s", exc)
    except Exception as exc:  # pragma: no cover
        log.exception("api triggered pipeline crashed: %s", exc)


@router.post("/run/sync", summary="Trigger a pipeline run and wait for the result")
def trigger_sync(
    payload: PipelineTriggerRequest,
    request: Request,
    session: DbSession,
    user: PipelineUser,
) -> dict[str, Any]:
    from app.etl.pipeline import Pipeline, PipelineConfig

    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="pipeline.run_sync",
            entity_type="etl_run",
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details={"sources": payload.sources, "database": payload.database},
        )
    )
    result = Pipeline(
        PipelineConfig(
            sources=payload.sources or [],
            database=payload.database,
            limit_per_source=payload.limit_per_source,
            strict=payload.strict,
            skip_dq=payload.skip_dq,
            skip_catalog=payload.skip_catalog,
            trigger=payload.trigger or "api",
            dag_id=payload.dag_id,
            task_id=payload.task_id,
            created_by=user.email,
        )
    ).run()
    return result.as_dict()


@router.get("/backfills", response_model=list[dict[str, Any]], summary="Recent backfill jobs")
def backfills(session: DbSession, _user: ReadUser, limit: int = 25) -> list[dict[str, Any]]:
    from app.services.backfill import list_backfills

    return list_backfills(session, limit=limit)


@router.post(
    "/backfill",
    response_model=BackfillResult,
    summary="Replay the pipeline across a date range (one run per day)",
)
def backfill(
    payload: BackfillRequest,
    request: Request,
    session: DbSession,
    user: PipelineUser,
) -> dict[str, Any]:
    """Queue a backfill. Days run independently so one failure cannot abort the job."""
    from app.services.backfill import execute_backfill, plan_backfill

    plan = plan_backfill(
        start_date=payload.start_date,
        end_date=payload.end_date,
        sources=payload.sources,
        database=payload.database,
        limit_per_source=payload.limit_per_source,
        skip_dq=payload.skip_dq,
        skip_catalog=payload.skip_catalog,
        dry_run=payload.dry_run,
        created_by=user.email,
    )
    meta = request_meta(request)
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="pipeline.backfill",
            entity_type="backfill",
            entity_id=plan.backfill_id,
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
            details=plan.as_dict(),
        )
    )
    summary = execute_backfill(plan)
    log.info("backfill %s finished status=%s", plan.backfill_id, summary["status"])
    try:
        from app.services.webhooks import emit

        emit(session, "backfill.completed", {"backfill_id": plan.backfill_id, **summary})
    except Exception:  # noqa: BLE001 - webhook problems must never fail a backfill
        log.warning("backfill webhook emission failed for %s", plan.backfill_id)
    return summary


@router.get("/backfill/{backfill_id}", summary="Progress and per-day results of a backfill")
def backfill_detail(backfill_id: str, session: DbSession, _user: ReadUser) -> dict[str, Any]:
    from app.services.backfill import backfill_progress

    progress = backfill_progress(session, backfill_id)
    if not progress.get("found"):
        raise NotFoundError(f"backfill '{backfill_id}' not found")
    return progress


@router.get("/sources/status", summary="Source health with sync state")
def sources_status(session: DbSession, _user: OptionalUser) -> list[dict[str, Any]]:
    from app.ingestion.base import list_sources

    registered = {source["code"]: source for source in list_sources()}
    rows = (
        session.execute(
            sa.text(
                """
            SELECT s.source_code, s.name, s.kind, s.enabled, s.rate_limit_per_minute, s.min_delay_seconds,
                   s.terms_allowed, s.robots_checked_at, s.last_run_at, s.last_run_id, s.total_records,
                   s.total_runs, s.success_rate_pct, s.avg_duration_seconds, s.base_url, s.terms_url,
                   COALESCE(y.consecutive_failures, 0) AS consecutive_failures,
                   COALESCE(y.status, 'unknown') AS sync_status,
                   y.message AS sync_message,
                   (SELECT COUNT(DISTINCT product_id) FROM fact_price_snapshot f WHERE f.source_code = s.source_code) AS products_seen
            FROM dim_source s
            LEFT JOIN sync_state y ON y.source_code = s.source_code
            ORDER BY s.source_code
            """
            )
        )
        .mappings()
        .all()
    )

    payload: list[dict[str, Any]] = []
    known = {row["source_code"] for row in rows}
    for row in rows:
        item = dict(row)
        item["registered"] = row["source_code"] in registered
        item["managed"] = "code" if row["source_code"] in registered else "database"
        item["description"] = registered.get(row["source_code"], {}).get("description", "")
        item["robots_respected"] = registered.get(row["source_code"], {}).get("robots_respected", True)
        # Present on every row so the two branches of this payload share one
        # shape and a consumer never has to guess which keys exist.
        item["supports_paging"] = registered.get(row["source_code"], {}).get("supports_paging", False)
        # A source that has never run has no sync_state row, so the COALESCE
        # above yields 'unknown'. 'idle' is the honest label: registered and
        # ready, simply not exercised yet.
        if (item.get("total_runs") or 0) == 0 and item.get("sync_status") == "unknown":
            item["sync_status"] = "idle"
        payload.append(item)

    # Registered sources that have never run have no `dim_source` row at all.
    # They still need the full row shape: the dashboard reads terms, rate
    # limits and delays from this payload, and omitting them made every
    # never-run source render as "terms restricted · 0 req/min · 0s delay",
    # contradicting the compliance header built from the registry.
    for code, source in registered.items():
        if code in known:
            continue
        payload.append(
            {
                "source_code": code,
                "name": source["name"],
                "kind": source["kind"],
                "enabled": source["enabled"],
                "registered": True,
                "managed": "code",
                "base_url": source.get("base_url"),
                "terms_url": source.get("terms_url"),
                "terms_allowed": source.get("terms_allowed", True),
                "description": source.get("description", ""),
                "robots_respected": source.get("robots_respected", True),
                "supports_paging": source.get("supports_paging", False),
                "rate_limit_per_minute": source.get("rate_limit_per_minute", 0),
                "min_delay_seconds": source.get("min_delay_seconds", 0),
                "robots_checked_at": None,
                "last_run_at": None,
                "last_run_id": None,
                "total_runs": 0,
                "total_records": 0,
                "success_rate_pct": None,
                "avg_duration_seconds": 0,
                "products_seen": 0,
                "consecutive_failures": 0,
                "sync_status": "idle",
                "sync_message": None,
            }
        )
    payload.sort(key=lambda item: item["source_code"])
    return payload


@router.post(
    "/rebuild-aggregates",
    summary="Rebuild the category/day rollup for the latest run",
)
def rebuild_aggregates(session: DbSession, user: PipelineUser) -> dict[str, Any]:
    """Recompute `agg_category_daily` from the latest run's snapshots.

    Exposed so the Airflow DAG can rebuild the rollup over REST when it cannot
    import the pipeline package in-process (the Airflow container pins
    SQLAlchemy 1.4). `GET /stages` is deliberately not used for this: it is a
    read-only catalogue and does not refresh anything.
    """
    from app.etl.loader import WarehouseLoader

    run = session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)).scalars().first()
    if run is None:
        raise NotFoundError("no pipeline run found; run the pipeline before rebuilding aggregates")
    written = WarehouseLoader(session, run.run_id).refresh_category_daily()
    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="pipeline.rebuild_aggregates",
            entity_type="etl_run",
            entity_id=run.run_id,
            details={"rows": written},
        )
    )
    log.info("aggregates rebuilt for run %s: %s rows", run.run_id, written)
    return {"status": "refreshed", "run_id": run.run_id, "rows": written}


@router.get("/stages", summary="Stage catalogue and average durations")
def stages(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    from app.etl.pipeline import STAGE_NAMES

    rows = (
        session.execute(
            sa.text(
                """
            SELECT status, COUNT(*) AS runs, ROUND(CAST(AVG(duration_ms) AS DECIMAL(24,2)), 0) AS avg_duration_ms,
                   MAX(duration_ms) AS max_duration_ms,
                   SUM(records_extracted) AS records_extracted, SUM(records_valid) AS records_valid
            FROM etl_run GROUP BY status
            """
            )
        )
        .mappings()
        .all()
    )
    return {
        "stages": list(STAGE_NAMES),
        "by_status": [dict(row) for row in rows],
        "totals": analytics.table_counts(session),
    }


@router.post(
    "/clear-history",
    response_model=Message,
    summary="Delete run history (admin)",
)
def clear_history(
    session: DbSession,
    user: PipelineUser,
    confirm: Annotated[bool, Query()] = False,
    include_facts: Annotated[
        bool,
        Query(
            description="Also delete the price snapshots and change events of the deleted runs. "
            "Without this flag, only operational history is removed and any run that still "
            "has warehouse facts is kept."
        ),
    ] = False,
) -> Message:
    """Purge run history.

    Operational tables (`dq_rule_result`, `fact_catalog_snapshot`,
    `ingestion_http_log`) are always cleared. The `etl_run` rows are only removed
    when nothing else references them: `fact_price_snapshot`, `chg_price_change`
    and `chg_product_event` all carry a `run_id`, so deleting those runs
    unconditionally raised a foreign-key violation.

    Pass `include_facts=true` to delete the warehouse facts too. That is
    destructive and irreversible, so the response reports exactly what went.
    """
    from app.api.security import at_least

    if not at_least(user.role, "admin") or not confirm:
        return Message(
            message="Refused: requires an admin role and confirm=true", detail={"required": "admin + confirm"}
        )

    session.add(
        AppAuditLog(
            user_id=user.user_id,
            user_email=user.email,
            action="pipeline.clear_history",
            entity_type="etl_run",
            entity_id="*",
            details={"include_facts": include_facts},
        )
    )

    deleted: dict[str, int] = {}
    for table in ("dq_rule_result", "fact_catalog_snapshot", "ingestion_http_log"):
        result = session.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 - fixed table list
        deleted[table] = int(result.rowcount or 0)  # type: ignore[attr-defined]

    if include_facts:
        for table in ("fact_price_snapshot", "chg_price_change", "chg_product_event"):
            result = session.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 - fixed table list
            deleted[table] = int(result.rowcount or 0)  # type: ignore[attr-defined]
        result = session.execute(sa.text("DELETE FROM etl_run"))
        deleted["etl_run"] = int(result.rowcount or 0)  # type: ignore[attr-defined]
        return Message(message="Run history and warehouse facts deleted", detail=deleted)

    # Keep any run that still has facts pointing at it.
    result = session.execute(
        sa.text(
            """
            DELETE FROM etl_run
            WHERE NOT EXISTS (SELECT 1 FROM fact_price_snapshot s WHERE s.run_id = etl_run.run_id)
              AND NOT EXISTS (SELECT 1 FROM chg_price_change c  WHERE c.run_id = etl_run.run_id)
              AND NOT EXISTS (SELECT 1 FROM chg_product_event e  WHERE e.run_id = etl_run.run_id)
            """
        )
    )
    deleted["etl_run"] = int(result.rowcount or 0)  # type: ignore[attr-defined]
    remaining = session.execute(sa.select(sa.func.count()).select_from(EtlRun)).scalar() or 0
    deleted["runs_kept_because_facts_exist"] = int(remaining)
    return Message(message="Operational run history cleared", detail=deleted)


@router.get("/schedule", summary="Configured schedule and orchestration status")
def schedule(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    from app.models.app_users import AppSetting

    row = session.get(AppSetting, "pipeline.schedule_cron")
    last = session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)).scalars().first()
    return {
        "cron": row.value if row else "0 3 * * *",
        "dag_id": "product_intelligence_pipeline",
        "orchestrator": "Apache Airflow (LocalExecutor) - optional local scheduler fallback",
        "last_run_at": last.started_at if last else None,
        "next_expected": (last.started_at + dt.timedelta(days=1)) if last else None,
        "trigger_mix": [
            dict(item)
            for item in session.execute(
                sa.text("SELECT trigger, COUNT(*) AS count FROM etl_run GROUP BY trigger")
            ).mappings()
        ],
    }
