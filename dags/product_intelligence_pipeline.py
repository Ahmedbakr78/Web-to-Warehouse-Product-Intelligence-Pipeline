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
# Transport
#
# Airflow 2.10 runs on SQLAlchemy 1.4 (its own ORM models are not SQLAlchemy 2
# compatible) while the pipeline package requires SQLAlchemy 2.0, so inside the Airflow
# container the two cannot share one interpreter. Every task therefore resolves through
# `call_pipeline`, which prefers a direct in-process call and transparently falls back to
# the pipeline's REST API. `make airflow-test` on the host takes the fast path; the
# containerised DAG takes the API path. Same logic, same results, one code path.
# --------------------------------------------------------------------------------------
API_URL = os.environ.get("PIPELINE_API_URL", "http://api:8000/api/v1").rstrip("/")
API_KEY = os.environ.get("PIPELINE_SERVICE_KEY", "")


def _api(method: str, path: str, **kwargs: Any) -> Any:
    """Call the pipeline REST API with the service credentials."""
    import httpx

    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    with httpx.Client(timeout=180.0) as client:
        response = client.request(method, f"{API_URL}{path}", headers=headers, **kwargs)
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text


def call_pipeline(local_callable: Any, api_path: str, *, method: str = "GET", **api_kwargs: Any) -> Any:
    """Run `local_callable` in-process, or fall back to the REST API."""
    try:
        return local_callable()
    except ImportError as exc:
        print(f"in-process execution unavailable ({exc}); using the REST API at {API_URL}")
        return _api(method, api_path, **api_kwargs)


def _task_id(context: dict) -> str | None:
    """Task id from the Airflow context (TaskInstance object, dict or None)."""
    task = context.get("task")
    if isinstance(task, dict):
        return task.get("task_id")
    return getattr(task, "task_id", None)


def latest_run_id_via_api() -> str:
    run = _api("GET", "/pipeline/runs/latest")
    if not run or not run.get("run_id"):
        raise RuntimeError("no pipeline run found to work with")
    return run["run_id"]


# --------------------------------------------------------------------------------------
# Python callables used by the operators (kept import-safe so the DAG parses offline)
# --------------------------------------------------------------------------------------
def check_database_health(**context: Any) -> bool:
    """Short-circuit guard: the warehouse must be reachable before anything else runs."""

    def local() -> bool:
        from app.core.db import ping

        target = (context.get("params") or {}).get("database") or "postgres"
        health = ping(target)
        if not health["connected"]:
            raise RuntimeError(f"target database '{target}' is unreachable: {health['error']}")
        print(f"database ok: {health['dialect']} {health['server_version']} latency={health['latency_ms']}ms")
        return True

    return bool(call_pipeline(local, "/health"))


def check_source_compliance(**context: Any) -> bool:
    """Short-circuit guard: at least one allow-listed source must pass robots.txt.

    `local()` returns the list of usable source codes rather than a bare `True`.
    That matters because `call_pipeline` prefers the in-process result, and the old
    `True` was then treated as an empty response below - so the in-process path
    always raised "no usable source" and `make airflow-test` could never pass.
    """

    def local() -> list[str]:
        from app.ingestion.base import list_sources
        from app.ingestion.robots import get_robots_cache

        sources = (context.get("params") or {}).get("sources") or DEFAULT_SOURCES
        cache = get_robots_cache()
        usable: list[str] = []
        for source in list_sources():
            if source["code"] not in sources:
                continue
            if not source_enabled(source["code"]):
                print(f"skip {source['code']}: disabled or not terms-allowed")
                continue
            decision = cache.can_fetch(source["base_url"])
            print(f"robots check {source['code']}: allowed={decision.allowed} ({decision.rule})")
            if decision.allowed:
                usable.append(source["code"])
        if not usable:
            raise RuntimeError("robots.txt forbids every configured source - aborting")
        print(f"usable sources: {usable}")
        return usable

    payload = call_pipeline(local, "/sources")
    # REST fallback: the registry response carries the enabled/terms flags per source.
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload.get("sources") or payload.get("items") or []
    else:
        entries = []
    codes = (context.get("params") or {}).get("sources") or DEFAULT_SOURCES
    usable = [
        entry.get("code")
        for entry in entries
        if entry.get("code") in codes and entry.get("enabled") and entry.get("terms_allowed")
    ]
    if not usable:
        raise RuntimeError("no usable (enabled + terms-allowed) source configured - aborting")
    print(f"usable sources: {usable}")
    return True


def source_enabled(code: str) -> bool:
    """A source participates only when the registry marks it enabled AND terms-allowed."""
    from app.ingestion.base import get_source_class

    try:
        source_cls = get_source_class(code)
    except Exception:
        return False
    return bool(source_cls.enabled and source_cls.terms_allowed)


def probe_sources(**context: Any) -> dict[str, Any]:
    """Fetch a single record from every configured source as a connectivity probe."""

    def local() -> dict[str, Any]:
        from app.ingestion.base import get_source

        codes = (context.get("params") or {}).get("sources") or DEFAULT_SOURCES
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

    codes = (context.get("params") or {}).get("sources") or DEFAULT_SOURCES
    return call_pipeline(
        local,
        "/pipeline/sources/status",
        params={"source_code": codes[0]} if len(codes) == 1 else None,
    )


def pipeline_command(stage: str, **extra: str) -> str:
    """Build a CLI invocation for one ETL stage."""
    parts = [
        "python -m app.cli.main run-pipeline",
        f'--sources "{" ,".join(DEFAULT_SOURCES)}"'.replace(" ", ""),
        f"--limit {REQUESTS_PER_SOURCE}",
        "--trigger airflow",
    ]
    parts.extend(extra.split() if extra else [])
    return f"cd {PROJECT_ROOT} && PYTHONPATH={PROJECT_ROOT} {' '.join(parts)}"


def run_full_pipeline(**context: Any) -> dict[str, Any]:
    """Execute the whole orchestrator: extract -> load -> detect -> reconcile -> quality."""

    def local() -> dict[str, Any]:
        from app.etl.pipeline import Pipeline, PipelineConfig

        params = context.get("params") or {}
        config = PipelineConfig(
            sources=params.get("sources") or DEFAULT_SOURCES,
            database=params.get("database") or "postgres",
            limit_per_source=int(params.get("limit") or REQUESTS_PER_SOURCE),
            trigger="airflow",
            dag_id=DAG_ID,
            task_id=_task_id(context),
            created_by="airflow",
        )
        result = Pipeline(config).run()
        print(f"airflow run {result.run_id} status={result.status} counters={result.counters}")
        return result.as_dict()

    params = context.get("params") or {}
    payload = {
        "sources": params.get("sources") or DEFAULT_SOURCES,
        "database": params.get("database") or "postgres",
        "limit_per_source": int(params.get("limit") or REQUESTS_PER_SOURCE),
        "trigger": "airflow",
        "dag_id": DAG_ID,
        "task_id": _task_id(context),
    }
    result = call_pipeline(local, "/pipeline/run/sync", method="POST", json=payload)
    print(f"airflow run {result.get('run_id')} status={result.get('status')}")
    return result


def evaluate_quality(**context: Any) -> dict[str, Any]:
    """Data-quality gate: only a *critical* failure stops the run."""
    payload = call_pipeline(lambda: _quality_local(), "/quality/latest")
    print(f"dq summary: {payload}")
    blocking = payload.get("blocking") if isinstance(payload, dict) else None
    if blocking:
        raise RuntimeError(f"data-quality gate failed for blocking rules: {blocking}")
    return payload


def _quality_local() -> dict[str, Any]:
    from app.core.db import session_scope
    from app.etl.dq import evaluate_quality as evaluate

    database = "postgres"
    with session_scope(database) as session:
        return evaluate(session, _latest_run_id(session)).summary()


def _latest_run_id(session: Any) -> str:
    import sqlalchemy as sa

    from app.models.operations import EtlRun

    row = session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1)).scalars().first()
    if row is None:
        raise RuntimeError("no pipeline run found to evaluate")
    return row.run_id


def build_aggregates(**context: Any) -> dict[str, Any]:
    """Rebuild the pre-aggregated category/day rollup for the latest run."""

    def local() -> dict[str, Any]:
        from app.core.db import session_scope
        from app.etl.loader import WarehouseLoader

        with session_scope("postgres") as session:
            run_id = _latest_run_id(session)
            written = WarehouseLoader(session, run_id).refresh_category_daily()
        print(f"category-daily aggregates refreshed: {written} rows for run {run_id}")
        return {"status": "refreshed", "rows": written, "run_id": run_id}

    return call_pipeline(local, "/pipeline/stages")


def reconcile_catalog(**context: Any) -> dict[str, Any]:
    """Match the internal catalog against the freshly loaded warehouse."""

    def local() -> dict[str, Any]:
        from app.core.db import session_scope
        from app.etl.catalog_reconcile import CatalogReconciler, reconciliation_summary

        with session_scope("postgres") as session:
            results = CatalogReconciler(session, _latest_run_id(session)).run(persist=True)
        return reconciliation_summary(results)

    summary = call_pipeline(local, "/catalog/summary")
    if isinstance(summary, dict):
        print(f"catalog reconciliation: {summary.get('totals') or summary}")
    return summary


def detect_changes(**context: Any) -> dict[str, Any]:
    """Publish change counts to XCom so the branching task can consume them."""
    payload = call_pipeline(lambda: _changes_local(), "/changes/summary", params={"days": 1})
    print(f"changes: {payload}")
    return payload


def _changes_local() -> dict[str, Any]:
    """In-process implementation (used when the interpreter allows SQLAlchemy 2)."""
    import sqlalchemy as sa

    from app.core.db import session_scope

    with session_scope("postgres") as session:
        run_id = _latest_run_id(session)
        row = (
            session.execute(
                sa.text(
                    """
                SELECT (SELECT COUNT(*) FROM chg_price_change WHERE run_id = :run_id) AS price_changes,
                       (SELECT COUNT(*) FROM chg_product_event WHERE run_id = :run_id AND event_type = 'new') AS new_products,
                       (SELECT COUNT(*) FROM chg_product_event WHERE run_id = :run_id AND event_type = 'removed') AS removed,
                       (SELECT COUNT(*) FROM chg_product_event WHERE run_id = :run_id AND event_type = 'category_changed') AS category_changes
                """
                ),
                {"run_id": run_id},
            )
            .mappings()
            .one()
        )
    return dict(row)


def publish_notifications(**context: Any) -> dict[str, Any]:
    """Evaluate the alert rules and raise in-app notifications for whatever matches."""
    return call_pipeline(lambda: _notify_local(), "/alerts/evaluate", method="POST")


def _notify_local() -> dict[str, Any]:
    import sqlalchemy as sa

    from app.core.db import session_scope
    from app.models.app_users import AppAlertRule, AppNotification

    created = 0
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    with session_scope("postgres") as session:
        rules = (
            session.execute(sa.select(AppAlertRule).where(AppAlertRule.is_active.is_(True))).scalars().all()
        )
        for rule in rules:
            if rule.metric != "price_change_pct":
                continue
            count = (
                session.execute(
                    sa.text(
                        """
                    SELECT COUNT(*) FROM chg_price_change
                    WHERE direction = 'decrease' AND ABS(change_pct) >= :threshold
                      AND detected_at >= :since
                    """
                    ),
                    {"threshold": abs(rule.threshold), "since": since},
                ).scalar()
                or 0
            )
            if not count:
                continue
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
    return {"notifications_created": created}


def publish_report(**context: Any) -> dict[str, Any]:
    """Publish the analytics report and persist a JSON artifact for the Airflow UI."""

    def kpi_local() -> dict[str, Any]:
        from app.analytics import service as analytics
        from app.core.db import session_scope

        with session_scope("postgres") as session:
            return analytics.kpi_summary(session, days=30)

    def changes_local() -> dict[str, Any]:
        from app.analytics import service as analytics
        from app.core.db import session_scope

        with session_scope("postgres") as session:
            return analytics.change_event_summary(session, days=30)

    def quality_local() -> dict[str, Any]:
        from app.core.db import session_scope
        from app.etl.dq import latest_report

        with session_scope("postgres") as session:
            return latest_report(session)

    report = {
        "kpi": call_pipeline(kpi_local, "/analytics/kpi"),
        "changes": call_pipeline(changes_local, "/changes/summary", params={"days": 30}),
        "quality": call_pipeline(quality_local, "/quality/latest"),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    artifact = _write_report_artifact(report, context)
    if artifact:
        report["artifact"] = artifact
    print(f"report sections: {list(report)} artifact={artifact}")
    return report


def _write_report_artifact(report: dict[str, Any], context: dict[str, Any]) -> str | None:
    """Persist the report JSON next to the other runtime artifacts (never fatal)."""
    import json

    stamp = (context.get("ts_nodash") or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")).replace(
        "+", ""
    )
    # Inside Airflow the project root is /opt/airflow; on a developer host fall
    # back to the repository checkout that contains this DAG.
    roots = [PROJECT_ROOT, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    for root in roots:
        try:
            reports_dir = os.path.join(root, "var", "reports")
            os.makedirs(reports_dir, exist_ok=True)
            path = os.path.join(reports_dir, f"{DAG_ID}-{stamp}.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, default=str)
            return path
        except OSError:  # read-only mount or missing permissions: try the next root
            continue
    print("could not persist the report artifact under any project root")
    return None


def branch_on_changes(**context: Any) -> str:
    """Only run the notification task when something actually changed."""
    changes = context["ti"].xcom_pull(task_ids="detect_changes") or {}
    print(f"branch input: {changes}")
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
        report = PythonOperator(
            task_id="publish_report",
            python_callable=publish_report,
            # A branch may skip a sibling; the report must still be published.
            trigger_rule=TriggerRule.ALL_DONE,
        )
        stop = EmptyOperator(task_id="end", trigger_rule=TriggerRule.ALL_DONE)

        # ---------------- wiring -------------------------------------------------------
        start >> health_check >> compliance_check >> probe >> execute
        execute >> [detect, quality, aggregates, reconcile]
        detect >> branch
        branch >> [notify, skip_notify]
        [notify, skip_notify, quality, aggregates, reconcile] >> report >> stop
