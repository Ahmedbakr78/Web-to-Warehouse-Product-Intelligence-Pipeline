"""Database engine / session management for PostgreSQL, MySQL and SQLite.

The project must run identically on all three targets, so every engine is built
through :func:`build_engine` which adapts pool arguments and pragmas per dialect.
Engines and session factories are cached per target so repeated CLI calls inside a
single process reuse the same connection pool (fast repeated runs).
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator, Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_ENGINES: dict[str, Engine] = {}
_FACTORIES: dict[str, sessionmaker[Session]] = {}


def _dialect_of(url: str) -> str:
    for name in ("postgresql", "postgres", "mysql", "mariadb", "sqlite"):
        if url.startswith(name):
            return "mysql" if name == "mariadb" else name
    return url.split(":", 1)[0]


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
    """Foreign keys are off by default in SQLite - turn them on for integrity."""
    module = type(dbapi_connection).__module__ or ""
    if "sqlite" not in module.lower():
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        # WAL still allows only one writer at a time. Without a busy timeout SQLite
        # raises "database is locked" the instant a second connection writes, which
        # the background job worker does routinely while the pipeline holds a
        # transaction. Waiting is always better than failing the job.
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


def build_engine(url: str | None = None, **overrides: Any) -> Engine:
    """Create (but do not register) a dialect-aware SQLAlchemy engine."""
    target_url = url or settings.sqlalchemy_url
    dialect = _dialect_of(target_url)
    options: dict[str, Any] = {"future": True, "pool_pre_ping": True, "echo": settings.db_echo}

    if dialect.startswith("postgres"):
        options.update(
            pool_size=overrides.pop("pool_size", settings.db_pool_size),
            max_overflow=overrides.pop("max_overflow", settings.db_max_overflow),
            pool_recycle=overrides.pop("pool_recycle", settings.db_pool_recycle),
            pool_timeout=overrides.pop("pool_timeout", 30),
        )
        options.update(overrides)
        engine = create_engine(target_url, **options)
        with contextlib.suppress(Exception), engine.connect() as conn:
            conn.execute(text(f"SET statement_timeout = {int(settings.db_statement_timeout_ms)}"))
        return engine

    if dialect == "mysql":
        options.update(
            pool_size=overrides.pop("pool_size", settings.db_pool_size),
            max_overflow=overrides.pop("max_overflow", settings.db_max_overflow),
            pool_recycle=overrides.pop("pool_recycle", settings.db_pool_recycle),
            pool_timeout=overrides.pop("pool_timeout", 30),
            connect_args=overrides.pop(
                "connect_args", {"connect_timeout": 10, "charset": "utf8mb4", "autocommit": False}
            ),
        )
        options.update(overrides)
        return create_engine(target_url, **options)

    if dialect == "sqlite":
        options.pop("pool_size", None)
        options.pop("max_overflow", None)
        connect_args = overrides.pop("connect_args", {})
        connect_args.setdefault("timeout", 30)
        options["connect_args"] = connect_args
        options["pool_pre_ping"] = True
        options.update(overrides)
        return create_engine(target_url, **options)

    return create_engine(target_url, **options)


def get_engine(database: str | None = None) -> Engine:
    """Return (and cache) the engine for the requested target database."""
    key = (database or settings.active_database).lower()
    if key in _ENGINES:
        return _ENGINES[key]
    engine = build_engine(settings.url_for(key))
    _ENGINES[key] = engine
    log.debug("engine created target=%s dialect=%s", key, engine.dialect.name)
    return engine


def get_session_factory(database: str | None = None) -> sessionmaker[Session]:
    """Return (and cache) a session factory bound to the target engine."""
    key = (database or settings.active_database).lower()
    if key not in _FACTORIES:
        _FACTORIES[key] = sessionmaker(
            bind=get_engine(key), autoflush=False, expire_on_commit=False, future=True
        )
    return _FACTORIES[key]


@contextlib.contextmanager
def session_scope(database: str | None = None) -> Generator[Session, None, None]:
    """Transactional session scope: commit on success, rollback on error."""
    factory = get_session_factory(database)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextlib.contextmanager
def read_session(database: str | None = None) -> Generator[Session, None, None]:
    """Read-only session scope (no commit, rollback instead)."""
    factory = get_session_factory(database)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def ping(database: str | None = None) -> dict[str, Any]:
    """Health probe used by ``/health`` and the CLI ``verify`` command."""
    target = (database or settings.active_database).lower()
    result: dict[str, Any] = {
        "database": target,
        "connected": False,
        "latency_ms": None,
        "dialect": None,
        "server_version": None,
        "error": None,
        "tables": 0,
    }
    try:
        engine = get_engine(target)
        result["dialect"] = engine.dialect.name
        started = _now_ms()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            result["latency_ms"] = round(_now_ms() - started, 2)
            try:
                version = conn.exec_driver_sql(_version_sql(engine)).scalar()
                result["server_version"] = str(version)[:80] if version else None
            except Exception:  # pragma: no cover - informational only
                result["server_version"] = None
            try:
                result["tables"] = _count_tables(conn, engine)
            except Exception:  # pragma: no cover - informational only
                result["tables"] = 0
        result["connected"] = True
    except Exception as exc:  # pragma: no cover - depends on environment
        result["error"] = f"{type(exc).__name__}: {exc}"
        log.warning("database ping failed target=%s error=%s", target, exc)
    return result


def _version_sql(engine: Engine) -> str:
    name = engine.dialect.name
    if name == "postgresql":
        return "SHOW server_version"
    if name == "mysql":
        return "SELECT VERSION()"
    return "SELECT sqlite_version()"


def _count_tables(conn: Any, engine: Engine) -> int:
    inspector = __import__("sqlalchemy").inspect(conn)
    return len(inspector.get_table_names())


def _now_ms() -> float:
    import time

    return time.perf_counter() * 1000


def dispose_all() -> None:
    """Dispose every cached engine (used by tests)."""
    for engine in _ENGINES.values():
        with contextlib.suppress(Exception):
            engine.dispose()
    _ENGINES.clear()
    _FACTORIES.clear()


def iter_targets() -> Iterator[tuple[str, bool]]:
    """Yield ``(target, configured)`` for every supported database target."""
    yield "postgres", bool(settings.database_url)
    yield "mysql", bool(settings.mysql_url)
    yield "sqlite", settings.database_url.startswith("sqlite")


__all__ = [
    "build_engine",
    "get_engine",
    "get_session_factory",
    "session_scope",
    "read_session",
    "ping",
    "dispose_all",
    "iter_targets",
]
