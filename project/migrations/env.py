"""Alembic environment.

Wired to the application's own `Settings` rather than `alembic.ini`, so a migration
runs against whichever of the three supported dialects `ACTIVE_DATABASE` selects and
with the same credentials the application uses. There is no second place to configure.

Three details matter for portability across PostgreSQL, MySQL and SQLite:

* **Schema.** MySQL has no schemas; PostgreSQL uses `DB_SCHEMA` (default `public`);
  SQLite ignores it entirely.
* **Generated identity.** `batch_alter_table` is used for column changes, which is
  what makes `ALTER` work on SQLite at all - it rewrites the table instead.
* **Comparisons.** Autogenerate compares types through SQLAlchemy's dialect-aware
  type system, so a `Numeric(18,4)` is not reported as changed on every run.
* **Exclusions.** `app.core.schema_scope` decides what counts as a warehouse table, so
  the analytical views and any foreign service's tables are never proposed for a DROP.
  The policy lives with the application rather than here, which is also what makes it
  testable without an Alembic runtime context.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.schema_scope import include_object  # noqa: E402
from app.models import ALL_MODELS, Base  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _configure(connection) -> None:  # noqa: ANN001
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        version_table=settings.alembic_version_table,
        # SQLite cannot ALTER most things in place.
        render_as_batch=connection.dialect.name == "sqlite",
        # A schema name only means something on PostgreSQL.
        include_schema=settings.db_schema if connection.dialect.name == "postgresql" else None,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade --sql`)."""
    context.configure(
        url=settings.url_for(settings.active_database),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        version_table=settings.alembic_version_table,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect through the application's own engine and run the migrations."""
    engine = get_engine(settings.active_database)
    with engine.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
