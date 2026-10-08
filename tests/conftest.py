"""Pytest configuration shared by every test module.

The suite runs against **SQLite** by default so ``pytest`` works with no services
running; set ``PIP_TEST_DATABASE_URL`` to exercise PostgreSQL or MySQL instead.
"""

from __future__ import annotations

import os
from pathlib import Path

# The database URL must be set before app.core.config is imported anywhere.
TEST_DATABASE = os.getenv("PIP_TEST_DATABASE_URL", "sqlite:///./var/test-pipeline.sqlite3")
os.environ["DATABASE_URL"] = TEST_DATABASE
os.environ.setdefault("ACTIVE_DATABASE", "sqlite")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-32chars")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("RESPECT_ROBOTS_TXT", "true")
os.environ.setdefault("REQUESTS_PER_SECOND", "1000")
os.environ.setdefault("REQUESTS_PER_MINUTE", "60000")
os.environ.setdefault("CRAWL_DELAY_FALLBACK_SECONDS", "0")
os.environ.setdefault("CACHE_ENABLED", "false")
# The API's per-caller request budget (240/min) is a production guard. A full
# suite run issues thousands of requests as the same seed users within a few
# minutes, so the middleware would 429 unrelated tests depending on file order.
# The limiter itself is covered by unit tests in test_new_features.py.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest  # noqa: E402

from app.core.db import dispose_all, get_engine, session_scope  # noqa: E402
from app.etl.bootstrap import bootstrap, drop_views  # noqa: E402
from app.etl.seed import run_full_seed  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def database() -> str:
    """Create the schema once per test session and return the target name."""
    target = "sqlite" if TEST_DATABASE.startswith("sqlite") else "postgres"
    path = Path(TEST_DATABASE.replace("sqlite:///", ""))
    if target == "sqlite":
        path.parent.mkdir(parents=True, exist_ok=True)
        # Remove the database AND its WAL sidecars. A stale -wal / -shm pair left
        # behind by an interrupted run makes the next session fail with
        # "disk I/O error" on the first PRAGMA.
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{path}{suffix}")
            if candidate.exists():
                candidate.unlink()
    bootstrap(target)
    run_full_seed(target, days=30)
    yield target
    dispose_all()


@pytest.fixture()
def clean_database(database: str) -> str:
    """Per-test isolation: delete every warehouse row but keep the schema."""
    engine = get_engine(database)
    drop_views(database)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.exec_driver_sql(f'DELETE FROM "{table.name}"')
    bootstrap(database)
    run_full_seed(database, days=30)
    yield database


@pytest.fixture()
def session(clean_database: str):
    with session_scope(clean_database) as db_session:
        yield db_session


@pytest.fixture()
def db(database: str):
    """Read-only session against the seeded demo warehouse."""
    with session_scope(database) as db_session:
        yield db_session
