"""Data-quality endpoints: latest report, rule catalogue, history."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.api.deps import DbSession, PaginationDep, ReadUser
from app.api.schemas import Page
from app.etl.dq import latest_report, rules_catalog

router = APIRouter(prefix="/quality", tags=["data-quality"])


@router.get("/latest", summary="Most recent DQ report with the quality score")
def latest(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    return latest_report(session)


@router.get("/runs/{run_id}", summary="DQ report for a specific run")
def for_run(run_id: str, session: DbSession, _user: ReadUser) -> dict[str, Any]:
    return latest_report(session, run_id=run_id)


@router.get("/rules", summary="Catalogue of every data-quality rule")
def rules(_user: ReadUser) -> list[dict[str, Any]]:
    return rules_catalog()


@router.get("/results", response_model=Page[dict[str, Any]], summary="Historical DQ results")
def results(session: DbSession, pagination: PaginationDep, _user: ReadUser, status: str | None = None,
            dimension: str | None = None) -> Page[dict[str, Any]]:
    where = ["1 = 1"]
    params: dict[str, Any] = {}
    if status:
        where.append("q.status = :status")
        params["status"] = status
    if dimension:
        where.append("q.dimension = :dimension")
        params["dimension"] = dimension
    clause = "WHERE " + " AND ".join(where)
    total = session.execute(sa.text(f"SELECT COUNT(*) FROM dq_rule_result q {clause}"), params).scalar() or 0
    rows = session.execute(
        sa.text(
            f"""
            SELECT q.result_id, q.run_id, q.rule_code, q.rule_name, q.dimension, q.severity, q.status,
                   q.observed_value, q.expected_value, q.records_checked, q.records_failed,
                   q.pass_rate_pct, q.message, q.evaluated_at
            FROM dq_rule_result q {clause}
            ORDER BY q.evaluated_at DESC, q.rule_code
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": pagination.page_size, "offset": pagination.offset},
    ).mappings().all()
    return Page.build([dict(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/trend", summary="Quality score trend per run")
def trend(session: DbSession, _user: ReadUser, days: Annotated[int, Query(ge=1, le=3650)] = 90) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.text(
            """
            SELECT r.run_id, r.started_at, r.dq_score, r.status,
                   SUM(CASE WHEN q.status = 'pass' THEN 1 ELSE 0 END) AS passed,
                   SUM(CASE WHEN q.status = 'warn' THEN 1 ELSE 0 END) AS warned,
                   SUM(CASE WHEN q.status = 'fail' THEN 1 ELSE 0 END) AS failed
            FROM etl_run r JOIN dq_rule_result q ON q.run_id = r.run_id
            WHERE r.started_at >= :since
            GROUP BY r.run_id, r.started_at, r.dq_score, r.status
            ORDER BY r.started_at
            """
        ),
        {"since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)},
    ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/summary", summary="Aggregate quality posture")
def summary(session: DbSession, _user: ReadUser) -> dict[str, Any]:
    by_dimension = session.execute(
        sa.text(
            """
            SELECT dimension, status, COUNT(*) AS count
            FROM dq_rule_result GROUP BY dimension, status
            """
        )
    ).mappings().all()
    by_status = session.execute(
        sa.text("SELECT status, COUNT(*) AS count FROM dq_rule_result GROUP BY status")
    ).mappings().all()
    worst = session.execute(
        sa.text(
            """
            SELECT rule_code, rule_name, dimension, severity, status, message, observed_value, expected_value, run_id
            FROM dq_rule_result WHERE status IN ('fail','warn')
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'error' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END,
                     evaluated_at DESC LIMIT 10
            """
        )
    ).mappings().all()
    return {
        "by_dimension": [dict(row) for row in by_dimension],
        "by_status": [dict(row) for row in by_status],
        "problem_rules": [dict(row) for row in worst],
    }
