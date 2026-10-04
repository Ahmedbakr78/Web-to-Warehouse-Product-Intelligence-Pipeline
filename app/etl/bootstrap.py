"""Database bootstrap: schemas, ORM table creation, reference data and views.

Runs identically on PostgreSQL, MySQL 8 and SQLite so the project can be verified on
every target without changing a single line of application code.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
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


def table_report(database: str | None = None) -> list[dict[str, Any]]:
    """Row counts per table (used by ``verify`` and the health endpoint)."""
    engine = get_engine(database)
    inspector = sa.inspect(engine)
    report: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for table in sorted(inspector.get_table_names()):
            try:
                count = conn.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
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
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
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
                    is_month_end=current == (current.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1),
                    iso_week=_isoweek(current),
                )
            )
            inserted += 1
        current += dt.timedelta(days=1)
    session.flush()
    return inserted


def ensure_date_range(session: Session, days_back: int = 400, days_forward: int = 2) -> int:
    today = dt.date.today()
    return seed_dim_date(session, today - dt.timedelta(days=days_back), today + dt.timedelta(days=days_forward))


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
    "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5", "CNY": "\u00a5",
    "INR": "\u20b9", "AUD": "A$", "CAD": "C$", "TRY": "\u20ba", "RUB": "\u20bd",
    "BRL": "R$", "PLN": "z\u0142", "SEK": "kr", "CHF": "CHF",
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
VIEWS_DIR = settings.DB_DIR


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
    """Create the analytical views (portable SQL only)."""
    engine = get_engine(database)
    path = VIEWS_DIR / "views.sql"
    if not path.exists():
        log.warning("views.sql not found at %s", path)
        return []
    applied: list[str] = []
    with engine.begin() as conn:
        for statement in _load_sql_statements(path):
            if not statement.lower().startswith(("create", "replace")):
                continue
            name = _view_name(statement)
            drop = f'DROP VIEW IF EXISTS "{name}"' if engine.dialect.name == "postgresql" else f"DROP VIEW IF EXISTS `{name}`"
            try:
                conn.execute(sa.text(drop))
                conn.execute(sa.text(statement))
                applied.append(name)
            except Exception as exc:  # pragma: no cover - dialect specific failures
                log.warning("view %s failed: %s", name, exc)
    log.info("applied %d views on %s", len(applied), engine.dialect.name)
    return applied


def _view_name(statement: str) -> str:
    lowered = statement.lower()
    marker = "view"
    index = lowered.find(marker)
    remainder = statement[index + len(marker) :]
    for token in ['"', "`", " ", ".", "("]:
        remainder = remainder.replace(token, " ")
    parts = remainder.split()
    return parts[0] if parts else "unknown_view"


def drop_views(database: str | None = None) -> int:
    """Remove every view created by :func:`apply_views`."""
    engine = get_engine(database)
    applied = apply_views(database)
    with engine.begin() as conn:
        quote = '"' if engine.dialect.name != "mysql" else "`"
        for name in applied:
            try:
                conn.execute(sa.text(f"DROP VIEW IF EXISTS {quote}{name}{quote}"))
            except Exception:  # pragma: no cover
                pass
    return len(applied)


__all__ = [
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