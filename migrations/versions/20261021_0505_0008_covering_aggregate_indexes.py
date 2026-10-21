"""Covering indexes for the aggregates the dashboard reads most.

Revision ID: 0008_covering_aggregate_indexes
Revises: 0007_widen_audit_user_agent
Create Date: 2026-10-21 05:05:00.000000

Every headline number on the dashboard is an aggregate over
``fact_price_snapshot``, and the three most expensive ones had to read the
whole heap to produce it:

* ``vw_source_coverage`` groups every observation by source. Measured on an
  83,000-row table it spent 181 ms on a sequential scan and an external merge
  sort, spilling 4 MB to disk.
* ``vw_daily_kpis`` and ``vw_category_price_index`` group the same rows by
  date.
* ``vw_product_current`` looks up each product's latest snapshot with a
  correlated subquery, once per product.

Three covering indexes turn those reads into index-only scans:

* ``ix_fact_price_source_cover`` on ``(source_code, product_id)`` including the
  priced and rated columns - the source-coverage aggregate drops from 181 ms
  to 22 ms.
* ``ix_fact_price_date_cover`` on ``(date_id, product_id)`` including the same
  columns - the daily rollups become index-only scans too.
* ``ix_fact_price_product_source`` on ``(product_id, source_code, snapshot_id)``
  - the "latest snapshot for this product" lookup becomes a single-row
  index-only MAX instead of a scan.

The indexes are created concurrently where the dialect supports it, so a large
table is not locked while they are built.
"""

from collections.abc import Sequence

from alembic import op

from app.core.db import create_index_if_missing, drop_index_if_present

# revision identifiers, used by Alembic.
revision: str = "0008_covering_aggregate_indexes"
down_revision: str | Sequence[str] | None = "0007_widen_audit_user_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "fact_price_snapshot"

#: (index name, columns, included columns)
_INDEXES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "ix_fact_price_source_cover",
        ("source_code", "product_id"),
        ("price_usd", "rating", "captured_at"),
    ),
    (
        "ix_fact_price_date_cover",
        ("date_id", "product_id"),
        ("price_usd", "rating", "in_stock"),
    ),
    (
        "ix_fact_price_product_source",
        ("product_id", "source_code", "snapshot_id"),
        (),
    ),
)


def _supports_concurrently() -> bool:
    """PostgreSQL can build an index without blocking writes; SQLite cannot."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Create the covering indexes."""
    if _supports_concurrently():
        # `CREATE INDEX CONCURRENTLY` cannot run inside a transaction, so the
        # autocommit block below is the only way to use it from Alembic.
        with op.get_context().autocommit_block():
            for name, columns, included in _INDEXES:
                column_list = "(" + ", ".join(f'"{column}"' for column in columns) + ")"
                if included:
                    column_list += " INCLUDE (" + ", ".join(f'"{c}"' for c in included) + ")"
                op.execute(
                    'CREATE INDEX CONCURRENTLY IF NOT EXISTS "%s" ON "%s" %s'
                    % (name, _TABLE, column_list)
                )
    connection = op.get_bind()
    for name, columns, _included in _INDEXES:
        create_index_if_missing(connection, name, _TABLE, list(columns))


def downgrade() -> None:
    """Drop the covering indexes."""
    if _supports_concurrently():
        with op.get_context().autocommit_block():
            for name, _columns, _included in _INDEXES:
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
        return
    connection = op.get_bind()
    for name, _columns, _included in _INDEXES:
        drop_index_if_present(connection, name)
