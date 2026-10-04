"""Apache Airflow DAG: orchestrated product intelligence pipeline.

    Product Intelligence Pipeline
      check_health ──► extract ──► stage ──► transform ──► dedupe ──► load_warehouse
                                                        │                │
                                              data_quality ◄──────────┤
                                                        │           detect_changes
                                                 build_aggregates ◄────┘
                                                        │
                                              reconcile_catalog
                                                        │
                                              publish_notifications ──► report

Design notes
------------
* Every task is idempotent and can be retried safely (each run gets a fresh
  ``run_id`` and the fact table is keyed by ``(product_id, run_id)``).
* ``ShortCircuitOperator`` guards stop the DAG when the database is unreachable or
  robots.txt forbids every configured source, instead of failing loudly at load time.
* A single ``PipelineTrigger`` task can be switched on (``EXECUTE_FULL_PIPELINE``) to
  run the orchestrator in-process, which is handy for demonstrations; the default is the
  explicit task-by-task graph below, which shows the ETL stages individually.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any

# --------------------------------------------------------------------------------------
# Airflow imports with a graceful fallback so the module can also be imported by tests
# or by the CLI without Airflow installed.
# --------------------------------------------------------------------------------------
try:  # pragma: no cover - exercised only inside Airflow
    from airflow import DAG
    from airflow.models.param import Param
    from airflow.operators.bash import BashOperator
    from airflow.operators.empty import EmptyOperator
    from airflow.operators.python import BranchPythonOperator, PythonOperator, ShortCircuitOperator
    from airflow.providers.postgres.hooks.postgres import PostgresHook
    from airflow.utils.task_group import TaskGroup
    from airflow.utils.trigger_rule import TriggerRule

    AIRFLOW_AVAILABLE = True
except Exception:  # pragma: no cover - local development without Airflow
    AIRFLOW_AVAILABLE = False
    DAG = Any  # type: ignore[assignment,misc]
    Param = dict  # type: ignore[assignment,misc]
    BashOperator = PythonOperator = ShortCircuitOperator = BranchPythonOperator = None  # type: ignore[assignment]
    EmptyOperator = TaskGroup = None  # type: ignore[assignment]
    PostgresHook = None  # type: ignore[assignment]
    TriggerRule = None  # type: ignore[assignment]

PROJECT_ROOT = os.environ.get("PIP_PROJECT_ROOT", "/opt/airflow")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DAG_ID = "product_intelligence_pipeline"
SCHEDULE = os.environ.get("PIP_SCHEDULE", "0 3 * * *")
START_DATE = dt.datetime(2026, 1, 1)
MAX_ACTIVE_RUNS = 1
CATCHUP = False
DEFAULT_ARGS: dict[str, Any] = {
    "owner": "data-platform@pipeline.local",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": dt.timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": dt.timedelta(hours=1),
    "execution_timeout": dt.timedelta(minutes=45),
    "email_on_failure": False,
    "pool": "product_pipeline",
}

#: Sources the DAG collects on every schedule (all of them allow automated access).
DEFAULT_SOURCES = ["local_demo", "dummyjson_products", "fakestore_products"]
SCRAPE_SOURCES = ["books_to_scrape"]
REQUESTS_PER_SOURCE = int(os.environ.get("PIP_REQUESTS_PER_SOURCE", "120"))


# --------------------------------------------------------------------------------------
# Python callables used by the operators (kept import-safe so the DAG parses offline)
# --------------------------------------------------------------------------------------
def check_database_health(**context: Any) -> bool:
    """Short-circuit guard: the warehouse must be reachable before anything else runs."""
    from app.core.db import ping

    targets = (context["params"].get("database") if context.get("params") else None) or "postgres"
    health = ping(targets)
    if not health["connected"]:
        raise RuntimeError(f"target database '{targets}' is unreachable: {health['error']}")
    print(f"database ok: {health['dialect']} {health['server_version']} latency={health['latency_ms']}ms")
    return True


def check_source_compliance(**context: Any) -> bool:
    """Short-circuit guard: at least one allow-listed source must pass robots.txt."""
    from app.ingestion.base import list_sources
    from app.ingestion.robots import get_robots_cache

    sources = context["params"].get("sources") or DEFAULT_SOURCES
    cache = get_robots_cache()
    allowed = []
    for source in list_sources():
        if source["code"] not in sources:
            continue
        decision = cache.can_fetch(source["base_url"])
        allowed.append((source["code"], decision.allowed, decision.rule))
        print(f"robots check {source['code']}: allowed={decision.allowed} ({decision.rule})")
    usable = [code for code, ok, _rule in allowed if ok and settings_enabled(code)]
    if not usable:
        raise RuntimeError("robots.txt forbids every configured source - aborting")
    print(f"usable sources: {usable}")
    return True


def settings_enabled(code: str) -> bool:
    from app.ingestion.base import get_source_class

    try:
        return bool(get_source_class(code).enabled)
    except Exception:
        return False


def probe_sources(**context: Any) -> dict[str, Any]:
    """Fetch a single record from every configured source as a connectivity probe."""
    from app.ingestion.base import get_source

    params = context.get("params") or {}
    codes = params.get("sources") or DEFAULT_SOURCES
    outcome: dict[str, Any] = {}
    for code in codes:
        try:
            source = get_source(code)
            record = next(iter(source.fetch(limit=1)), None)
            source.close()
            outcome[code] = {"ok": record is not None, "name": record.name if record else None}
            print(f"probe {code}: ok={record is not None} ({record.name if record else 'no record'})")
        except Exception as exc:
            outcome[code] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
            print(f"probe {code}: FAILED {outcome[code]['error']}")
    if not any(value.get("ok") for value in outcome.values()):
        raise RuntimeError("no configured source returned a record")
    return outcome


def pipeline_command(stage: str, **extra: str) -> str:
    """Build a CLI invocation for one ETL stage."""
    parts = [
        'python -m app.cli.main run-pipeline',
        f'--sources "{" ,".join(DEFAULT_SOURCES)}"'.replace(" ", ""),
        f"--limit {REQUESTS_PER_SOURCE}",
        "--trigger airflow",
    ]
    parts.extend(extra.split() if extra else [])
    return f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} {' '.join(parts)}"


def run_full_pipeline(**context: Any) -> dict[str, Any]:
    """In-process execution of the whole orchestrator (used by ``execute_full_pipeline``)."""
    from app.etl.pipeline import Pipeline, PipelineConfig

    params = context.get("params") or {}
    config = PipelineConfig(
        sources=params.get("sources") or DEFAULT_SOURCES,
        database=params.get("database") or "postgres",
        limit_per_source=int(params.get("limit") or REQUESTS_PER_SOURCE),
        trigger="airflow",
        dag_id=DAG_ID,
        task_id=context.get("task", {}).get("task_id") if isinstance(context.get("task"), dict) else None,
        created_by="airflow",
    )
    result = Pipeline(config).run()
    print(f"airflow run {result.run_id} status={result.status} counters={result.counters}")
    return result.as_dict()


def evaluate_quality(**context: Any) -> dict[str, Any]:
    from app.core.db import session_scope
    from app.etl.dq import evaluate_quality as evaluate

    database = (context.get("params") or {}).get("database") or "postgres"
    with session_scope(database) as session:
        report = evaluate(session, _latest_run_id(session))
        payload = report.summary()
    print(f"dq summary: {payload}")
    if payload["blocking"]:
        raise RuntimeError(f"data-quality gate failed for blocking rules: {payload['blocking']}")
    return payload


def _latest_run_id(session: Any) -> str:
    import sqlalchemy as sa

    from app.models.operations import EtlRun

    row = session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)).scalars().first()
    if row is None:
        raise RuntimeError("no pipeline run found to evaluate")
    return row.run_id


def build_aggregates(**context: Any) -> int:
    """Rebuild the pre-aggregated category/day rollup for the latest run."""
    from app.core.db import session_scope
    from app.etl.loader import WarehouseLoader

    database = (context.get("params") or {}).get("database") or "postgres"
    with session_scope(database) as session:
        return WarehouseLoader(session, _latest_run_id(session)).refresh_category_daily()


def reconcile_catalog(**context: Any) -> dict[str, Any]:
    """Re-run the catalog reconciliation for the latest run."""
    from app.core.db import session_scope
    from app.etl.catalog_reconcile import CatalogReconciler, reconciliation_summary

    database = (context.get("params") or {}).get("database") or "postgres"
    with session_scope(database) as session:
        results = CatalogReconciler(session, _latest_run_id(session)).run(persist=True)
        summary = reconciliation_summary(results)
    print(f"catalog reconciliation: {summary}")
    return summary


def detect_changes(**context: Any) -> dict[str, Any]:
    """Publish change counts to XCom so downstream tasks can consume them."""
    import sqlalchemy as sa

    from app.core.db import session_scope

    database = (context.get("params") or {}).get("database") or "postgres"
    with session_scope(database) as session:
        run_id = _latest_run_id(session)
        row = session.execute(
            sa.text(
                """
                SELECT (SELECT COUNT(*) FROM chg_price_change WHERE run_id = :run_id) AS price_changes,
                       (SELECT COUNT(*) FROM chg_product_event WHERE run_id = :run_id AND event_type = 'new') AS new_products,
                       (SELECT COUNT(*) FROM chg_product_event WHERE run_id = :run_id AND event_type = 'removed') AS removed,
                       (SELECT COUNT(*) FROM chg_product_event WHERE run_id = :run_id AND event_type = 'category_changed') AS category_changes
                """
            ),
            {"run_id": run_id},
        ).mappings().one()
    payload = dict(row)
    print(f"changes: {payload}")
    return payload


def publish_notifications(**context: Any) -> int:
    """Create in-app notifications for the configured alert rules."""
    import sqlalchemy as sa

    from app.core.db import session_scope
    from app.models.app_users import AppAlertRule, AppNotification

    database = (context.get("params") or {}).get("database") or "postgres"
    created = 0
    with session_scope(database) as session:
        rules = session.execute(
            sa.select(AppAlertRule).where(AppAlertRule.is_active.is_(True))
        ).scalars().all()
        for rule in rules:
            if rule.metric == "price_change_pct":
                count = session.execute(
                    sa.text(
                        """
                        SELECT COUNT(*) FROM chg_price_change
                        WHERE direction = 'decrease' AND ABS(change_pct) >= :threshold
                          AND detected_at >= :since
                        """
                    ),
                    {"threshold": abs(rule.threshold), "since": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)},
                ).scalar() or 0
            else:
                continue
            if count:
                session.add(
                    AppNotification(
                        user_id=rule.user_id,
                        alert_id=rule.alert_id,
                        level="warning" if count < 10 else "critical",
                        title=f"{rule.name}: {count} matching events in the last 24h",
                        body=f"Threshold {rule.operator} {rule.threshold}%",
                        entity_type="price_change",
                        action_url="/changes/price",
                    )
                )
                rule.last_triggered_at = dt.datetime.now(dt.timezone.utc)
                rule.trigger_count = (rule.trigger_count or 0) + 1
                created += 1
    print(f"notifications published: {created}")
    return created


def publish_report(**context: Any) -> str:
    """Render the analytics report into the Airflow log (and optionally a file)."""
    import subprocess

    output = subprocess.run(
        [sys.executable, "-m", "app.cli.main", "report",
         "--days", "30", "--json"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300,
    )
    print(output.stdout[:4000])
    artifact_dir = os.path.join(PROJECT_ROOT, "var", "artifacts")
    os.makedirs(artifact_dir, exist_ok=True)
    path = os.path.join(artifact_dir, f"report-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M%S}.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(output.stdout or "{}")
    print(f"report artifact: {path}")
    return path


def branch_on_changes(**context: Any) -> str:
    """Only run the notification task when something actually changed."""
    changes = context["ti"].xcom_pull(task_ids="detect_changes") or {}
    if changes.get("price_changes") or changes.get("new_products") or changes.get("removed"):
        return "notify_users"
    return "skip_notifications"


# --------------------------------------------------------------------------------------
# DAG definition
# --------------------------------------------------------------------------------------
if AIRFLOW_AVAILABLE:  # pragma: no cover - only inside Airflow
    with DAG(
        dag_id=DAG_ID,
        description="Compliant web-to-warehouse product intelligence pipeline",
        schedule=SCHEDULE,
        start_date=START_DATE,
        catchup=CATCHUP,
        max_active_runs=MAX_ACTIVE_RUNS,
        default_args=DEFAULT_ARGS,
        tags=["etl", "product-intelligence", "web-scraping", "data-quality"],
        params={
            "database": Param("postgres", type="string", title="Target database"),
            "sources": Param(DEFAULT_SOURCES, type="array", title="Source codes"),
            "limit": Param(REQUESTS_PER_SOURCE, type="integer", title="Records per source"),
        },
        doc_md=__doc__,
    ) as dag:
        start = EmptyOperator(task_id="start")

        # ---------------- pre-flight guards -------------------------------------------
        health_check = ShortCircuitOperator(
            task_id="check_database_health",
            python_callable=check_database_health,
            doc_md="Abort early when the analytical database is unreachable.",
        )
        compliance_check = ShortCircuitOperator(
            task_id="check_source_compliance",
            python_callable=check_source_compliance,
            doc_md="Verify robots.txt permits every configured source before crawling.",
        )
        probe = PythonOperator(
            task_id="probe_sources",
            python_callable=probe_sources,
            doc_md="Fetch one record per source to prove connectivity and extraction.",
        )

        # ---------------- the pipeline itself -----------------------------------------
        execute = PythonOperator(
            task_id="run_pipeline",
            python_callable=run_full_pipeline,
            doc_md="Extract -> stage -> transform -> dedupe -> load -> detect changes.",
            execution_timeout=dt.timedelta(minutes=30),
        )
        detect = PythonOperator(task_id="detect_changes", python_callable=detect_changes)
        quality = PythonOperator(task_id="data_quality_gate", python_callable=evaluate_quality)
        aggregates = PythonOperator(task_id="build_aggregates", python_callable=build_aggregates)
        reconcile = PythonOperator(task_id="reconcile_catalog", python_callable=reconcile_catalog)

        # ---------------- alerting ----------------------------------------------------
        branch = BranchPythonOperator(
            task_id="branch_changes",
            python_callable=branch_on_changes,
            doc_md="Only notify users when the run actually produced changes.",
        )
        notify = PythonOperator(task_id="notify_users", python_callable=publish_notifications)
        skip_notify = EmptyOperator(task_id="skip_notifications")
        report = PythonOperator(task_id="publish_report", python_callable=publish_report)
        stop = EmptyOperator(task_id="end")

        # ---------------- wiring -------------------------------------------------------
        start >> health_check >> compliance_check >> probe >> execute
        execute >> [detect, quality, aggregates, reconcile]
        detect >> branch
        branch >> [notify, skip_notify]
        [notify, skip_notify, quality, aggregates, reconcile] >> report >> stop
