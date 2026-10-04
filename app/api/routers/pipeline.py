"""Pipeline endpoints: list runs, inspect a run, trigger a new run, stage timings."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Query, Request
from sqlalchemy.orm import Session

from app.analytics import service as analytics
from app.api.deps import DbSession, OptionalUser, PaginationDep, PipelineUser, ReadUser, request_meta
from app.api.schemas import Message, Page, PipelineRunRead, PipelineTriggerRequest
from app.core.errors import PipelineError
from app.core.logging import get_logger
from app.models.app_users import AppAuditLog, AppNotification
from app.models.operations import DqRuleResult, EtlRun

log = get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/runs", response_model=Page[PipelineRunRead], summary="List pipeline runs")
def runs(session: DbSession, pagination: PaginationDep, _user: ReadUser, status: str | None = None) -> Page[PipelineRunRead]:
    where = "WHERE 1 = 1"
    params: dict[str, Any] = {}
    if status:
        where += " AND status = :status"
        params["status"] = status
    total = session.execute(sa.text(f"SELECT COUNT(*) FROM etl_run {where}"), params).scalar() or 0
    rows = session.execute(
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
    ).mappings().all()
    items = [dict(row) | {"trigger": row["run_trigger"]} for row in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/runs/latest", summary="Most recent run (full detail)")
def latest_run(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    row = session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)).scalars().first()
    if row is None:
        return {}
    return analytics.run_detail(session, row.run_id)


@router.get("/runs/{run_id}", summary="Run detail with DQ, HTTP audit and reconciliation")
def run_detail(run_id: str, session: DbSession, _user: ReadUser) -> dict[str, Any]:
    detail = analytics.run_detail(session, run_id)
    if not detail:
        return {}
    return detail


@router.get("/runs/{run_id}/dq", summary="DQ rule results for one run")
def run_dq(run_id: str, session: DbSession, _user: ReadUser) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(DqRuleResult).where(DqRuleResult.run_id == run_id).order_by(DqRuleResult.rule_code)
    ).scalars().all()
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
    return analytics.http_log(session, limit=limit)


@router.post("/run", summary="Trigger a pipeline run (background)")
def trigger(
    payload: PipelineTriggerRequest,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    user: PipelineUser,
) -> dict[str, Any]:
    from app.etl.pipeline import Pipeline, PipelineConfig

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
            details={"sources": payload.sources, "database": payload.database, "trigger": payload.trigger},
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
            created_by=user.email,
        )
    ).run()
    return result.as_dict()


@router.get("/sources/status", summary="Source health with sync state")
def sources_status(session: DbSession, _user: OptionalUser) -> list[dict[str, Any]]:
    from app.ingestion.base import list_sources

    registered = {source["code"]: source for source in list_sources()}
    rows = session.execute(
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
    ).mappings().all()

    payload: list[dict[str, Any]] = []
    known = {row["source_code"] for row in rows}
    for row in rows:
        item = dict(row)
        item["registered"] = row["source_code"] in registered
        item["description"] = registered.get(row["source_code"], {}).get("description", "")
        item["robots_respected"] = registered.get(row["source_code"], {}).get("robots_respected", True)
        payload.append(item)
    for code, source in registered.items():
        if code not in known:
            payload.append({"source_code": code, "name": source["name"], "registered": True,
                            "enabled": source["enabled"], "kind": source["kind"], "products_seen": 0})
    return payload


@router.get("/stages", summary="Stage catalogue and average durations")
def stages(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    from app.etl.pipeline import STAGE_NAMES

    rows = session.execute(
        sa.text(
            """
            SELECT status, COUNT(*) AS runs, ROUND(CAST(AVG(duration_ms) AS DECIMAL(24,2)), 0) AS avg_duration_ms,
                   MAX(duration_ms) AS max_duration_ms,
                   SUM(records_extracted) AS records_extracted, SUM(records_valid) AS records_valid
            FROM etl_run GROUP BY status
            """
        )
    ).mappings().all()
    return {
        "stages": list(STAGE_NAMES),
        "by_status": [dict(row) for row in rows],
        "totals": analytics.table_counts(session),
    }


@router.post("/clear-history", response_model=Message, summary="Delete run history (admin)")
def clear_history(session: DbSession, user: PipelineUser, confirm: Annotated[bool, Query()] = False) -> Message:
    from app.api.security import at_least

    if not at_least(user.role, "admin") or not confirm:
        return Message(message="Refused: requires an admin role and confirm=true", detail={"required": "admin + confirm"})
    deleted = {
        "etl_run": session.execute(sa.text("DELETE FROM dq_rule_result")).rowcount,
        "dq_rule_result": 0,
    }
    session.execute(sa.text("DELETE FROM fact_catalog_snapshot"))
    session.execute(sa.text("DELETE FROM ingestion_http_log"))
    session.execute(sa.text("DELETE FROM dq_rule_result"))
    session.execute(sa.text("DELETE FROM etl_run"))
    return Message(message="Run history cleared", detail=deleted)


@router.get("/schedule", summary="Configured schedule and orchestration status")
def schedule(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    from app.models.app_users import AppSetting

    row = session.get(AppSetting, "pipeline.schedule_cron")
    last = session.execute(
        sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)
    ).scalars().first()
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