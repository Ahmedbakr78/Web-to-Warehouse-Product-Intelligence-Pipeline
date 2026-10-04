"""Rich-powered CLI for the whole pipeline.

Commands
--------
``init-db``      create tables + views + reference data
``bootstrap``    init-db + users + demo catalog and history
``seed-demo``    seed users / catalog / N days of history
``run-pipeline`` execute one full pipeline run
``sources``      list the registered ingestion sources
``report``       print the SQL analytics report
``verify``       compare PostgreSQL and MySQL targets
``serve``        run the FastAPI development server
``token``        issue an API token for a demo account
``user``         manage dashboard accounts
``quality``      re-evaluate the data-quality rules
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from app.core.config import describe_target, reload_settings, settings
from app.core.logging import configure_logging, get_logger, setup_file_logging

log = get_logger("app.cli")
console = Console(
    theme=Theme(
        {
            "ok": "bold green",
            "warn": "bold yellow",
            "err": "bold red",
            "info": "bold cyan",
            "key": "bold white",
        }
    )
)

app = typer.Typer(
    name="pip",
    help="Web-to-Warehouse Product Intelligence Pipeline - command line interface",
    add_completion=False,
    no_args_is_help=True,
)
sources_app = typer.Typer(help="Inspect ingestion sources", no_args_is_help=True)
users_app = typer.Typer(help="Manage dashboard accounts", no_args_is_help=True)
app.add_typer(sources_app, name="sources")
app.add_typer(users_app, name="user")

DB_OPTION = typer.Option(None, "--database", "-d", help="postgres | mysql | sqlite")


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def _print_json(payload: Any) -> None:
    console.print_json(json.dumps(payload, default=str))


def _kv_table(title: str, data: dict[str, Any]) -> None:
    table = Table(title=title, show_header=False, box=None, pad_edge=False)
    table.add_column("key", style="key", no_wrap=True)
    table.add_column("value")
    for key, value in data.items():
        table.add_row(str(key), str(value))
    console.print(Panel(table, border_style="info"))


def _status_line(text: str, ok: bool = True) -> None:
    console.print(f"[{'ok' if ok else 'err'}]{'✔' if ok else '✘'}[/] {text}")


# --------------------------------------------------------------------------------------
# database commands
# --------------------------------------------------------------------------------------
@app.command("init-db")
def init_db(
    database: str = DB_OPTION,
    drop: bool = typer.Option(False, "--drop", help="Drop every table first (destructive)"),
) -> None:
    """Create the schema, reference data and analytical views."""
    from app.etl.bootstrap import bootstrap

    console.rule(f"[bold]Initialising {describe_target(database)}")
    result = bootstrap(database, drop=drop)
    _kv_table(
        "Database ready",
        {
            "target": result["database"],
            "dialect": result["dialect"],
            "tables": result["table_count"],
            "views applied": len(result["views_applied"]),
            "date rows added": result["dim_date_rows_added"],
            "currency rows added": result["dim_currency_rows_added"],
            "duration": f"{result['duration_ms']} ms",
        },
    )
    _status_line("Schema, reference data and views are ready")


@app.command("bootstrap")
def bootstrap_cmd(
    database: str = DB_OPTION,
    drop: bool = typer.Option(False, "--drop"),
    days: int = typer.Option(120, "--days", min=7, max=1095, help="Days of demo history to generate"),
    no_demo: bool = typer.Option(False, "--no-demo", help="Schema only, skip demo data"),
) -> None:
    """One-shot setup: schema + reference data + users + demo dataset."""
    from app.etl.bootstrap import bootstrap as bootstrap_db
    from app.etl.seed import run_full_seed

    console.rule(f"[bold]Bootstrapping {describe_target(database)}")
    result = bootstrap_db(database, drop=drop)
    _status_line(
        f"{result['table_count']} tables, {len(result['views_applied'])} views on {result['dialect']}"
    )
    if not no_demo:
        seeded = run_full_seed(database, days=days)
        _kv_table(
            "Demo dataset",
            {
                "users": seeded["users"],
                "catalog SKUs": seeded["catalog"],
                "saved views + alerts": seeded["saved"],
                "products": seeded["history"].get("products", 0),
                "price snapshots": seeded["history"].get("snapshots", 0),
                "price changes": seeded["history"].get("price_changes", 0),
                "lifecycle events": seeded["history"].get("events", 0),
                "days of history": days,
            },
        )
    _status_line("Bootstrap complete - start the API with [bold]make serve[/]")


@app.command("seed-demo")
def seed_demo(
    database: str = DB_OPTION,
    days: int = typer.Option(120, "--days", min=7, max=1095),
    users_only: bool = typer.Option(False, "--users-only"),
    catalog_only: bool = typer.Option(False, "--catalog-only"),
) -> None:
    """Seed users, the internal catalog and historical snapshots."""
    from app.core.db import session_scope
    from app.etl.seed import build_seed_products, seed_catalog, seed_users

    with session_scope(database) as session:
        users = seed_users(session)
        catalog = 0 if users_only else seed_catalog(session, build_seed_products())
    history: dict[str, Any] = {}
    if not (users_only or catalog_only):
        with session_scope(database) as session:
            from app.etl.seed import seed_history

            history = seed_history(session, days=days)
    _kv_table(
        "Seeded",
        {
            "users": users,
            "catalog SKUs": catalog,
            "snapshots": history.get("snapshots", 0),
            "price changes": history.get("price_changes", 0),
            "events": history.get("events", 0),
        },
    )


@app.command("verify")
def verify(
    databases: str = typer.Option("postgres,mysql", "--databases", help="Comma separated targets"),
) -> None:
    """Compare row counts and data-quality posture across database targets."""
    from app.core.db import ping, session_scope
    from app.etl.bootstrap import table_report
    from app.etl.dq import latest_report

    targets = [item.strip().lower() for item in databases.split(",") if item.strip()]
    #: Structural tables must match exactly; fact tables depend on how many runs each
    #: target has executed, so they are reported but never treated as a failure.
    structural = ("dim_category", "dim_source", "dim_currency", "catalog_product", "app_user", "dim_date")
    reports: dict[str, Any] = {}
    for target in targets:
        health = ping(target)
        if not health["connected"]:
            reports[target] = {"error": health["error"]}
            continue
        counts = {row["table"]: row["rows"] for row in table_report(target)}
        with session_scope(target) as session:
            quality = latest_report(session)
        reports[target] = {
            "dialect": health["dialect"],
            "latency_ms": health["latency_ms"],
            "tables": len(counts),
            "products": counts.get("dim_product", 0),
            "categories": counts.get("dim_category", 0),
            "catalog": counts.get("catalog_product", 0),
            "snapshots": counts.get("fact_price_snapshot", 0),
            "price_changes": counts.get("chg_price_change", 0),
            "dq_score": quality.get("score"),
            "dq_pass": quality.get("pass"),
            "dq_fail": quality.get("fail"),
            "counts": counts,
        }

    table = Table(title="Cross-database verification", header_style="bold cyan")
    table.add_column("target")
    table.add_column("dialect")
    table.add_column("latency", justify="right")
    table.add_column("tables", justify="right")
    table.add_column("products", justify="right")
    table.add_column("categories", justify="right")
    table.add_column("catalog", justify="right")
    table.add_column("snapshots", justify="right")
    table.add_column("changes", justify="right")
    table.add_column("DQ", justify="right")
    for target, payload in reports.items():
        if "error" in payload:
            table.add_row(target, "[err]unreachable[/]", "-", "-", "-", "-", "-", "-", "-")
        else:
            table.add_row(
                target,
                str(payload["dialect"]),
                f"{payload['latency_ms']} ms",
                str(payload["tables"]),
                str(payload["products"]),
                str(payload["categories"]),
                str(payload["catalog"]),
                str(payload["snapshots"]),
                str(payload["price_changes"]),
                str(payload["dq_score"]),
            )
    console.print(table)

    reachable = {name: payload for name, payload in reports.items() if "error" not in payload}
    if len(reachable) > 1:
        drift = []
        for name in structural:
            values = {target: payload["counts"].get(name) for target, payload in reachable.items()}
            if len(set(values.values())) > 1:
                drift.append(f"{name}: {values}")
        if drift:
            console.print("[err]structural drift detected[/]")
            for item in drift:
                console.print(f"    - {item}")
        else:
            _status_line("Structural tables are identical on every target - the warehouse model is portable")
        scores = {payload["dq_score"] for payload in reachable.values()}
        if len(scores) == 1:
            _status_line(f"Identical data-quality score across targets ({scores.pop()})")
        else:
            _status_line(f"Data-quality scores differ between targets: {scores}", ok=False)


# --------------------------------------------------------------------------------------
# pipeline commands
# --------------------------------------------------------------------------------------
@app.command("run-pipeline")
def run_pipeline(
    sources: str = typer.Option(None, "--sources", "-s", help="Comma separated source codes"),
    database: str = DB_OPTION,
    limit: int = typer.Option(None, "--limit", "-n", min=1, max=5000, help="Records per source"),
    all_sources: bool = typer.Option(False, "--all-sources", help="Force every registered source"),
    strict: bool = typer.Option(False, "--strict", help="Reject records with a missing price"),
    skip_dq: bool = typer.Option(False, "--skip-dq"),
    skip_catalog: bool = typer.Option(False, "--skip-catalog"),
    trigger: str = typer.Option("cli", "--trigger"),
    quiet: bool = typer.Option(False, "--quiet", help="Only print the summary"),
) -> None:
    """Execute one full ingestion -> load -> analysis run."""
    from app.etl.pipeline import Pipeline, PipelineConfig

    selected = [item.strip() for item in sources.split(",")] if sources else []
    console.rule(f"[bold]Pipeline run on {describe_target(database)}")
    result = Pipeline(
        PipelineConfig(
            sources=selected,
            database=database,
            limit_per_source=limit,
            strict=strict,
            skip_dq=skip_dq,
            skip_catalog=skip_catalog,
            trigger=trigger,
            created_by="cli",
        )
    ).run()

    table = Table(title=f"Run {result.run_id}", header_style="bold cyan")
    table.add_column("metric")
    table.add_column("value", justify="right")
    counters = result.counters or {}
    for key in (
        "staged",
        "rejected",
        "products_created",
        "products_updated",
        "duplicates_merged",
        "snapshots_inserted",
        "price_changes",
        "new_products",
        "removed_products",
        "category_changes",
        "categories_created",
        "http_log_rows",
    ):
        if key in counters:
            table.add_row(key.replace("_", " "), str(counters[key]))
    table.add_row("duration", f"{result.duration_ms or 0} ms")
    if result.quality:
        table.add_row(
            "dq score",
            f"{result.quality.get('score')} ({result.quality.get('pass')} pass / "
            f"{result.quality.get('warn')} warn / {result.quality.get('fail')} fail)",
        )
    if result.reconciliation:
        table.add_row(
            "catalog matched",
            f"{result.reconciliation.get('matched')}/{result.reconciliation.get('total')} "
            f"({result.reconciliation.get('match_rate_pct')}%)",
        )
    console.print(table)

    if not quiet:
        timing = Table(title="Stage timings", header_style="bold cyan")
        timing.add_column("stage")
        timing.add_column("rows", justify="right")
        timing.add_column("ms", justify="right")
        timing.add_column("detail")
        for item in result.timings:
            timing.add_row(item.name, str(item.rows), f"{item.duration_ms}", item.detail or "")
        console.print(timing)

    for warning in result.warnings[:8]:
        console.print(f"[warn]![/] {warning}")
    colour = "ok" if result.status == "success" else ("warn" if result.status == "partial" else "err")
    _status_line(f"status: {result.status}", ok=result.status == "success")
    if result.status == "failed":
        raise typer.Exit(code=1)


@app.command("report")
def report(
    database: str = DB_OPTION,
    days: int = typer.Option(30, "--days", min=1, max=3650),
    limit: int = typer.Option(15, "--limit", min=1, max=100),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Print the SQL analytics report (price changes, drift, movers, quality)."""
    from app.analytics import service as analytics
    from app.core.db import session_scope

    with session_scope(database) as session:
        kpi = analytics.kpi_summary(session, days=days)
        movers = analytics.top_movers(session, limit=limit)
        changes = analytics.price_change_report(session, days=days, limit=limit)
        drift = analytics.category_drift_report(session, days=days)[:limit]
        from app.etl.dq import latest_report

        quality = latest_report(session)
        compliance = analytics.compliance_report(session, days=30)

    if json_output:
        _print_json(
            {
                "kpi": kpi,
                "top_movers": movers,
                "changes": changes,
                "category_drift": drift,
                "quality": quality,
                "compliance": compliance,
            }
        )
        return

    console.rule(f"[bold]Analytics report - last {days} days ({describe_target(database)})")
    _kv_table(
        "Summary",
        {
            "products observed": kpi["latest"].get("products"),
            "sources": kpi["latest"].get("sources"),
            "average price (USD)": kpi["latest"].get("avg_price"),
            "average rating": kpi["latest"].get("avg_rating"),
            "price changes": kpi["changes"].get("total_changes"),
            "significant changes": kpi["changes"].get("significant"),
            "new products": kpi["events"].get("new"),
            "removed products": kpi["events"].get("removed"),
            "category changes": kpi["events"].get("category_changed"),
            "dq score": quality.get("score"),
            "dq pass / warn / fail": f"{quality.get('pass')} / {quality.get('warn')} / {quality.get('fail')}",
            "http requests (30d)": compliance.get("requests"),
            "robots.txt blocks": compliance.get("blocked_requests"),
        },
    )

    if movers:
        table = Table(title=f"Top {len(movers)} price movers", header_style="bold cyan")
        table.add_column("product", overflow="ellipsis", max_width=44)
        table.add_column("category")
        table.add_column("from", justify="right")
        table.add_column("to", justify="right")
        table.add_column("change %", justify="right")
        for row in movers:
            colour = "green" if (row.get("change_pct") or 0) < 0 else "red"
            table.add_row(
                str(row.get("canonical_name"))[:44],
                str(row.get("category_name"))[:18],
                str(row.get("previous_price")),
                str(row.get("new_price")),
                f"[{colour}]{row.get('change_pct')}[/]",
            )
        console.print(table)

    if drift:
        table = Table(title="Category drift", header_style="bold cyan")
        table.add_column("category")
        table.add_column("added", justify="right")
        table.add_column("removed", justify="right")
        table.add_column("recategorised", justify="right")
        table.add_column("net", justify="right")
        for row in drift:
            table.add_row(
                str(row.get("category_name")),
                str(row.get("products_added")),
                str(row.get("products_removed")),
                str(row.get("products_recategorised")),
                str(row.get("net_change")),
            )
        console.print(table)

    if quality.get("rules"):
        table = Table(title="Data quality", header_style="bold cyan")
        table.add_column("rule")
        table.add_column("dimension")
        table.add_column("severity")
        table.add_column("status")
        table.add_column("observed")
        table.add_column("message", overflow="ellipsis", max_width=52)
        for rule in quality["rules"]:
            colour = {"pass": "green", "warn": "yellow", "fail": "red"}.get(rule["status"], "white")
            table.add_row(
                rule["code"],
                rule["dimension"],
                rule["severity"],
                f"[{colour}]{rule['status']}[/]",
                str(rule.get("observed_value")),
                (rule.get("message") or "")[:52],
            )
        console.print(table)


@app.command("quality")
def quality_cmd(
    database: str = DB_OPTION,
    run_id: str = typer.Option(None, "--run-id", help="Re-evaluate one specific run"),
) -> None:
    """Re-run the data-quality framework and print the report."""
    import sqlalchemy as sa

    from app.core.db import session_scope
    from app.etl.dq import evaluate_quality, latest_report
    from app.models.operations import EtlRun

    with session_scope(database) as session:
        target_run = run_id
        if target_run is None:
            row = (
                session.execute(sa.select(EtlRun).order_by(EtlRun.started_at.desc()).limit(1))
                .scalars()
                .first()
            )
            target_run = row.run_id if row else None
        if target_run is None:
            console.print("[warn]No runs found - run the pipeline first.[/]")
            raise typer.Exit(code=1)
        report_result = evaluate_quality(session, target_run)
        payload = report_result.summary()
        stored = latest_report(session, target_run)

    _kv_table(
        "Quality report",
        {
            "run": payload["run_id"],
            "rules": payload["total"],
            "pass": payload["pass"],
            "warn": payload["warn"],
            "fail": payload["fail"],
            "score": payload["score"],
            "blocking": ", ".join(payload["blocking"]) or "none",
        },
    )
    for rule in stored.get("rules", []):
        colour = {"pass": "green", "warn": "yellow", "fail": "red"}.get(rule["status"], "white")
        console.print(
            f"  [{colour}]{rule['status']:>4}[/] {rule['code']}  {rule['name']}  ({rule.get('observed_value')})"
        )


# --------------------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------------------
@sources_app.command("list")
def sources_list() -> None:
    """List every registered ingestion source."""
    from app.ingestion.base import list_sources

    table = Table(title="Registered ingestion sources", header_style="bold cyan")
    table.add_column("code")
    table.add_column("name", overflow="ellipsis", max_width=38)
    table.add_column("kind")
    table.add_column("rate", justify="right")
    table.add_column("delay", justify="right")
    table.add_column("paging")
    table.add_column("terms")
    table.add_column("robots.txt")
    for source in list_sources():
        table.add_row(
            source["code"],
            source["name"],
            source["kind"],
            f"{source['rate_limit_per_minute']}/min",
            f"{source['min_delay_seconds']}s",
            "yes" if source["supports_paging"] else "no",
            "allowed" if source["terms_allowed"] else "blocked",
            "respected" if source["robots_respected"] else "ignored",
        )
    console.print(table)
    console.print(
        "[dim]Only sources that allow automated access are queried. "
        "robots.txt is enforced by the HTTP client before every request.[/]"
    )


@sources_app.command("preview")
def sources_preview(
    code: str = typer.Argument(..., help="Source code"),
    limit: int = typer.Option(5, "--limit", "-n", min=1, max=25),
) -> None:
    """Fetch a few raw records and show the cleaned result."""
    from app.ingestion.base import get_source, transform_product

    source = get_source(code)
    table = Table(title=f"{source.name} - first {limit} records", header_style="bold cyan")
    table.add_column("id")
    table.add_column("name", overflow="ellipsis", max_width=38)
    table.add_column("category", overflow="ellipsis", max_width=24)
    table.add_column("price", justify="right")
    table.add_column("USD", justify="right")
    table.add_column("rating", justify="right")
    table.add_column("availability")
    table.add_column("flags")
    try:
        for index, raw in enumerate(source.fetch(limit=limit)):
            if index >= limit:
                break
            record = transform_product(raw)
            table.add_row(
                record.source_product_id,
                record.canonical_name[:38],
                record.category[:24],
                str(record.price),
                str(record.price_usd),
                str(record.rating),
                record.availability,
                ",".join(record.quality_flags) or "-",
            )
    finally:
        source.close()
    console.print(table)


@sources_app.command("check")
def sources_check() -> None:
    """Show the robots.txt decision cache statistics."""
    from app.ingestion.robots import get_robots_cache

    cache = get_robots_cache()
    _kv_table("robots.txt cache", dict(cache.stats))
    console.print(f"[dim]user-agent: {cache.user_agent}[/]")


# --------------------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------------------
@users_app.command("list")
def users_list(database: str = DB_OPTION) -> None:
    """List dashboard accounts."""
    import sqlalchemy as sa

    from app.core.db import session_scope
    from app.models.app_users import AppUser

    table = Table(title="Dashboard accounts", header_style="bold cyan")
    table.add_column("id", justify="right")
    table.add_column("email")
    table.add_column("name")
    table.add_column("role")
    table.add_column("active")
    table.add_column("logins", justify="right")
    table.add_column("last login")
    with session_scope(database) as session:
        rows = session.execute(sa.select(AppUser).order_by(AppUser.user_id)).scalars().all()
        for user in rows:
            table.add_row(
                str(user.user_id),
                user.email,
                user.full_name,
                user.role,
                "yes" if user.is_active else "no",
                str(user.login_count),
                str(user.last_login_at or "-"),
            )
    console.print(table)


@users_app.command("create")
def users_create(
    email: str = typer.Option(..., "--email"),
    full_name: str = typer.Option(..., "--name"),
    password: str = typer.Option(..., "--password"),
    role: str = typer.Option("viewer", "--role"),
    database: str = DB_OPTION,
) -> None:
    """Create a dashboard account."""
    import sqlalchemy as sa

    from app.api.security import hash_password
    from app.core.db import session_scope
    from app.models.app_users import AppUser

    with session_scope(database) as session:
        if session.execute(sa.select(AppUser).where(AppUser.email == email.lower())).scalars().first():
            console.print(f"[err]User '{email}' already exists[/]")
            raise typer.Exit(code=1)
        session.add(
            AppUser(
                email=email.lower(),
                full_name=full_name,
                hashed_password=hash_password(password),
                role=role,
                is_active=True,
                is_verified=True,
                password_changed_at=dt.datetime.now(dt.timezone.utc),
            )
        )
    _status_line(f"Created {role} account '{email}'")


@users_app.command("token")
def users_token(
    email: str = typer.Option(settings.seed_admin_email, "--email"),
    minutes: int = typer.Option(720, "--minutes", min=1, max=60 * 24 * 30),
) -> None:
    """Issue a JWT access token for an account (useful for curl / the frontend)."""
    from app.api.security import create_access_token

    token = create_access_token(email, role="admin", email=email, expires_minutes=minutes)
    _kv_table("Access token", {"email": email, "expires_in_minutes": minutes, "token": token})
    console.print(
        "\n[dim]curl -H 'Authorization: Bearer <token>' http://localhost:8000/api/v1/analytics/kpi[/]"
    )


# --------------------------------------------------------------------------------------
# serving
# --------------------------------------------------------------------------------------
@app.command("serve")
def serve(
    host: str = typer.Option(None, "--host"),
    port: int = typer.Option(None, "--port"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
    workers: int = typer.Option(1, "--workers", min=1, max=16),
    database: str = DB_OPTION,
) -> None:
    """Run the REST API with uvicorn."""
    import uvicorn

    if database:
        reload_settings()
    target_host = host or settings.app_host
    target_port = port or settings.app_port
    console.print(f"[info]API:[/] http://{target_host}:{target_port}/docs")
    console.print(f"[info]Health:[/] http://{target_host}:{target_port}/api/v1/health")
    if reload:
        uvicorn.run(
            "app.api.main:app",
            host=target_host,
            port=target_port,
            reload=True,
            log_level=settings.app_log_level.lower(),
        )
    else:
        uvicorn.run("app.api.main:app", host=target_host, port=target_port, workers=workers)


@app.command("status")
def status(database: str = DB_OPTION) -> None:
    """Show database health, row counts and the latest run."""
    from app.analytics import service as analytics
    from app.core.db import ping, session_scope
    from app.etl.bootstrap import table_report

    health = ping(database)
    _kv_table("Database", {key: value for key, value in health.items() if key != "error"})
    if not health["connected"]:
        _status_line(f"unreachable: {health['error']}", ok=False)
        raise typer.Exit(code=1)
    counts = {row["table"]: row["rows"] for row in table_report(database)}
    interesting = [
        "dim_product",
        "dim_category",
        "dim_source",
        "fact_price_snapshot",
        "chg_price_change",
        "chg_product_event",
        "agg_category_daily",
        "catalog_product",
        "etl_run",
        "dq_rule_result",
        "stg_raw_observation",
        "ingestion_http_log",
        "app_user",
    ]
    table = Table(title="Row counts", header_style="bold cyan")
    table.add_column("table")
    table.add_column("rows", justify="right")
    for name in interesting:
        table.add_row(name, f"{counts.get(name, 0):,}")
    console.print(table)

    with session_scope(database) as session:
        runs = analytics.pipeline_runs(session, limit=5)
    if runs:
        runs_table = Table(title="Recent pipeline runs", header_style="bold cyan")
        runs_table.add_column("run id")
        runs_table.add_column("status")
        runs_table.add_column("started")
        runs_table.add_column("extracted", justify="right")
        runs_table.add_column("snapshots", justify="right")
        runs_table.add_column("changes", justify="right")
        runs_table.add_column("dq", justify="right")
        for run in runs:
            colour = {"success": "green", "partial": "yellow", "failed": "red"}.get(run["status"], "white")
            runs_table.add_row(
                run["run_id"][:12],
                f"[{colour}]{run['status']}[/]",
                str(run["started_at"])[:16],
                str(run["records_extracted"]),
                str(run["records_valid"]),
                str(run["price_changes"]),
                str(run["dq_score"]),
            )
        console.print(runs_table)


@app.command("check-schema")
def check_schema(database: str = DB_OPTION) -> None:
    """Verify that the physical schema matches the ORM and list missing tables."""
    import sqlalchemy as sa

    from app.core.db import get_engine
    from app.models import CORE_TABLES

    engine = get_engine(database)
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names())
    expected = set(CORE_TABLES)
    missing = sorted(expected - existing)
    extra = sorted(existing - expected)
    _kv_table(
        "Schema check",
        {
            "expected tables": len(expected),
            "present": len(existing & expected),
            "missing": ", ".join(missing) or "none",
            "extra (views etc.)": ", ".join(extra) or "none",
            "dialect": engine.dialect.name,
        },
    )
    if missing:
        _status_line("Schema is incomplete - run 'make bootstrap'", ok=False)
        raise typer.Exit(code=1)
    _status_line("Schema matches the ORM definition")


@app.command("version")
def version_cmd() -> None:
    """Show version information."""
    _kv_table(
        "Version",
        {
            "application": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
            "active database": settings.active_database,
            "dialect": settings.dialect_name,
            "robots.txt": settings.respect_robots_txt,
            "user agent": settings.ingest_user_agent,
            "python": sys.version.split()[0],
        },
    )


@app.callback()
def main_callback(
    log_file: str = typer.Option(None, "--log-file", help="Also write logs to this file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    """Product Intelligence Pipeline CLI."""
    configure_logging("DEBUG" if verbose else settings.app_log_level, force=True)
    if log_file:
        setup_file_logging(log_file)


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
