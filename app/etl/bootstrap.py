"""Database bootstrap: schemas, ORM table creation, reference data and views.

Runs identically on PostgreSQL, MySQL 8 and SQLite so the project can be verified on
every target without changing a single line of application code.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import re
import time
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import DB_DIR, settings
from app.core.db import get_engine, session_scope
from app.core.logging import get_logger
from app.ingestion.cleaning import CURRENCY_NAMES, STATIC_FX_RATES
from app.models import Base
from app.models.dimensions import DimCurrency, DimDate, DimSource

log = get_logger(__name__)


# --------------------------------------------------------------------------------------
# Schema / table creation
# --------------------------------------------------------------------------------------
def create_schema(database: str | None = None, *, drop: bool = False) -> dict[str, Any]:
    """Create (or recreate) every table defined by the ORM."""
    engine = get_engine(database)
    started = time.perf_counter()
    if drop:
        log.warning("dropping all tables on %s", engine.url.render_as_string(hide_password=True))
        # Analytical views depend on the tables, so they must go first.
        try:
            drop_views(database)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            log.debug("view cleanup before drop failed: %s", exc)
        Base.metadata.drop_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
    Base.metadata.create_all(engine, checkfirst=True)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    tables = sorted(Base.metadata.tables)
    log.info("schema ready on %s (%d tables, %sms)", engine.dialect.name, len(tables), elapsed)
    return {
        "database": (database or settings.active_database).lower(),
        "dialect": engine.dialect.name,
        "tables": tables,
        "table_count": len(tables),
        "duration_ms": elapsed,
    }


def quote_identifier(engine: Any, name: str) -> str:
    """Dialect-correct quoting (double quotes on PostgreSQL/SQLite, backticks on MySQL)."""
    return engine.dialect.identifier_preparer.quote(name)


def table_report(database: str | None = None) -> list[dict[str, Any]]:
    """Row counts per table (used by ``verify`` and the health endpoint)."""
    engine = get_engine(database)
    inspector = sa.inspect(engine)
    report: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for table in sorted(inspector.get_table_names()):
            quoted = quote_identifier(engine, table)
            try:
                count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {quoted}")).scalar() or 0
            except Exception:  # pragma: no cover - view/permission issues
                count = None
            report.append({"table": table, "rows": count})
    return report


# --------------------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------------------
def date_id(value: dt.date | dt.datetime) -> int:
    """``YYYYMMDD`` surrogate key."""
    if isinstance(value, dt.datetime):
        value = value.date()
    return value.year * 10_000 + value.month * 100 + value.day


def _isoweek(value: dt.date) -> int:
    return value.isocalendar()[1]


MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def seed_dim_date(session: Session, start: dt.date, end: dt.date) -> int:
    """Populate the date dimension between two dates (inclusive, idempotent)."""
    existing = {row[0] for row in session.execute(sa.select(DimDate.date_id))}
    inserted = 0
    current = start
    while current <= end:
        key = date_id(current)
        if key not in existing:
            session.add(
                DimDate(
                    date_id=key,
                    full_date=current,
                    year=current.year,
                    quarter=(current.month - 1) // 3 + 1,
                    month=current.month,
                    day=current.day,
                    month_name=MONTH_NAMES[current.month - 1],
                    day_name=DAY_NAMES[current.weekday()],
                    week_of_year=current.isocalendar()[1],
                    is_weekend=current.weekday() >= 5,
                    is_month_start=current.day == 1,
                    is_month_end=current
                    == (current.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1),
                    iso_week=_isoweek(current),
                )
            )
            inserted += 1
        current += dt.timedelta(days=1)
    session.flush()
    return inserted


def ensure_date_range(session: Session, days_back: int = 400, days_forward: int = 2) -> int:
    today = dt.date.today()
    return seed_dim_date(
        session, today - dt.timedelta(days=days_back), today + dt.timedelta(days=days_forward)
    )


def seed_dim_currency(session: Session) -> int:
    """Reference currencies + offline FX rates."""
    existing = {row[0] for row in session.execute(sa.select(DimCurrency.currency_code))}
    inserted = 0
    today = dt.date.today()
    for code, rate in STATIC_FX_RATES.items():
        if code in existing:
            continue
        session.add(
            DimCurrency(
                currency_code=code,
                currency_name=CURRENCY_NAMES.get(code, code),
                symbol=CURRENCY_SYMBOL_OUT.get(code),
                rate_to_usd=rate,
                rate_source="static_reference_table",
                as_of=today,
            )
        )
        inserted += 1
    session.flush()
    return inserted


CURRENCY_SYMBOL_OUT = {
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "JPY": "\u00a5",
    "CNY": "\u00a5",
    "INR": "\u20b9",
    "AUD": "A$",
    "CAD": "C$",
    "TRY": "\u20ba",
    "RUB": "\u20bd",
    "BRL": "R$",
    "PLN": "z\u0142",
    "SEK": "kr",
    "CHF": "CHF",
}


def sync_dim_source(session: Session, source: Any) -> DimSource:
    """Insert or refresh the dimension row describing a registered source."""
    row = session.get(DimSource, source.code)
    if row is None:
        row = DimSource(source_code=source.code)
        session.add(row)
        row.total_runs = 0
    row.name = source.name
    row.kind = source.kind
    row.base_url = source.base_url
    row.robots_url = f"{source.base_url.rstrip('/')}/robots.txt" if source.kind == "scrape" else None
    row.terms_url = source.terms_url
    row.license_note = source.license_note
    row.rate_limit_per_minute = source.rate_limit_per_minute
    row.min_delay_seconds = source.min_delay_seconds
    row.enabled = source.enabled and (source.terms_allowed or not settings.respect_terms_whitelist)
    row.terms_allowed = source.terms_allowed
    row.robots_checked_at = dt.datetime.now(dt.timezone.utc)
    return row


def bootstrap(database: str | None = None, *, drop: bool = False) -> dict[str, Any]:
    """Full bootstrap: schema + reference data (+ views)."""
    result = create_schema(database, drop=drop)
    with session_scope(database) as session:
        dates = ensure_date_range(session)
        currencies = seed_dim_currency(session)
    result["dim_date_rows_added"] = dates
    result["dim_currency_rows_added"] = currencies
    views = apply_views(database)
    result["views_applied"] = views
    log.info("bootstrap complete: %s", {k: v for k, v in result.items() if k != "tables"})
    return result


# --------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------
VIEWS_DIR = DB_DIR


def _load_sql_statements(path: Any) -> list[str]:
    text = path.read_text(encoding="utf-8")
    statements: list[str] = []
    buffer: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buffer).strip().rstrip(";"))
            buffer = []
    if buffer:
        statements.append("\n".join(buffer).strip().rstrip(";"))
    return [s for s in statements if s]


def apply_views(database: str | None = None) -> list[str]:
    """Create the analytical views (portable SQL only).

    Every statement runs in its own connection/transaction.  That isolates failures
    (one bad view never aborts the batch) and works identically on PostgreSQL, MySQL -
    where DDL triggers an implicit commit and therefore invalidates SAVEPOINTs - and
    SQLite.
    """
    engine = get_engine(database)
    path = VIEWS_DIR / "views.sql"
    if not path.exists():
        log.warning("views.sql not found at %s", path)
        return []

    quote = "`" if engine.dialect.name == "mysql" else '"'
    cascade = " CASCADE" if engine.dialect.name == "postgresql" else ""
    statements = [
        statement
        for statement in _load_sql_statements(path)
        if statement.lower().startswith(("create", "replace"))
    ]
    names = [_view_name(statement) for statement in statements]
    applied: list[str] = []
    failed: list[str] = []

    # Drop first (reverse order + CASCADE) so dependent views never block the refresh.
    with engine.connect() as conn:
        for name in reversed(names):
            with contextlib.suppress(Exception):
                conn.execute(sa.text(f"DROP VIEW IF EXISTS {quote}{name}{quote}{cascade}"))
        conn.commit()

    for statement, name in zip(statements, names, strict=False):
        try:
            with engine.connect() as conn:
                conn.execute(sa.text(statement))
                conn.commit()
            applied.append(name)
        except Exception as exc:
            message = str(getattr(exc, "orig", exc)).splitlines()[0][:200]
            log.warning("view %s failed on %s: %s", name, engine.dialect.name, message)
            failed.append(name)

    log.info("applied %d/%d views on %s", len(applied), len(statements), engine.dialect.name)
    if failed:
        log.warning("views not applied on %s: %s", engine.dialect.name, ", ".join(failed))
    return applied


_CREATE_VIEW_RE = re.compile(
    r"create\s+(?:or\s+replace\s+)?(?:(?:temp|temporary|unlogged|materialized)\s+)*view\s+"
    r'(?:(?:if\s+not\s+exists)\s+)?(?P<name>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?|"[^"]+"|`[^`]+`)',
    re.IGNORECASE,
)


def _view_name(statement: str) -> str:
    """Extract the view name from a CREATE VIEW statement.

    The previous implementation searched for the first occurrence of the substring
    "view", which mis-parsed any statement whose comment or column list contained
    that word. This anchors on the statement keyword instead.
    """
    match = _CREATE_VIEW_RE.search(statement)
    if not match:
        return "unknown_view"
    return match.group("name").strip('"`')


def expected_view_names() -> set[str]:
    """The analytical views declared in `db/views.sql`.

    Used by the readiness probe and by the documentation consistency check so the
    count is never hard-coded in two places.
    """
    path = VIEWS_DIR / "views.sql"
    if not path.exists():
        return set()
    names = {
        _view_name(statement)
        for statement in _load_sql_statements(path)
        if statement.lower().startswith(("create", "replace"))
    }
    names.discard("unknown_view")
    return names


def drop_views(database: str | None = None) -> int:
    """Drop every analytical view that currently exists in the target database."""
    engine = get_engine(database)
    try:
        views = sa.inspect(engine).get_view_names()
    except Exception:  # pragma: no cover - dialect without view introspection
        views = []
    quote = "`" if engine.dialect.name == "mysql" else '"'
    cascade = " CASCADE" if engine.dialect.name == "postgresql" else ""
    dropped = 0
    with engine.connect() as conn:
        for name in views:
            try:
                conn.execute(sa.text(f"DROP VIEW IF EXISTS {quote}{name}{quote}{cascade}"))
                dropped += 1
            except Exception as exc:  # pragma: no cover
                log.debug("could not drop view %s: %s", name, exc)
        conn.commit()
    log.info("dropped %d views on %s", dropped, engine.dialect.name)
    return dropped


__all__ = [
    "quote_identifier",
    "create_schema",
    "table_report",
    "seed_dim_date",
    "seed_dim_currency",
    "ensure_date_range",
    "sync_dim_source",
    "bootstrap",
    "apply_views",
    "drop_views",
    "date_id",
]
