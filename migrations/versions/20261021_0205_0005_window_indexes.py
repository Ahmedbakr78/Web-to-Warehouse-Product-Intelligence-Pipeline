"""Index the fact and change timestamps the dashboards filter on.

Revision ID: 0005_window_indexes
Revises: 0004_remove_scrollbars
Create Date: 2026-10-21 02:05:00.000000

Every headline number in the product is windowed: "price changes in the last
30 days", "observations in the last 7 days", "new products in the last 90
days". Those queries filter on ``captured_at`` (facts) and ``detected_at``
(change tables) - and neither column carried an index, so the planner
sequential-scanned the whole table on every dashboard load.

At 45k snapshots the KPI query spent 190 ms of its budget on a sequential
scan of the fact table. The same plan against a half-million-row warehouse is
the difference between a responsive dashboard and a timeout. Three indexes
remove the scan:

* ``ix_fact_price_captured_product`` on ``(captured_at, product_id)`` serves
  the window filter *and* the distinct-product count in one index-only scan.
* ``ix_chg_event_detected`` on ``(detected_at)`` serves the lifecycle counters.
* ``ix_chg_price_detected`` on ``(detected_at)`` serves the price-change
  counters and the top-movers window.

The indexes are created concurrently where the dialect supports it, so a
large table is not locked for the duration of the build.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_window_indexes"
down_revision: str | Sequence[str] | None = "0004_remove_scrollbars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: (index name, table, columns)
_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_fact_price_captured_product", "fact_price_snapshot", ("captured_at", "product_id")),
    ("ix_chg_event_detected", "chg_product_event", ("detected_at",)),
    ("ix_chg_price_detected", "chg_price_change", ("detected_at",)),
)


def _supports_concurrently() -> bool:
    """PostgreSQL can build an index without blocking writes; SQLite cannot."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Create the window indexes."""
    if _supports_concurrently():
        # `CREATE INDEX CONCURRENTLY` cannot run inside a transaction, so the
        # autocommit block below is the only way to use it from Alembic.
        with op.get_context().autocommit_block():
            for name, table, columns in _INDEXES:
                column_list = ", ".join('"%s"' % column for column in columns)
                op.execute(
                    'CREATE INDEX CONCURRENTLY IF NOT EXISTS "%s" ON "%s" (%s)'
                    % (name, table, column_list)
                )
        return
    for name, table, columns in _INDEXES:
        op.create_index(name, table, list(columns), unique=False, if_not_exists=True)


def downgrade() -> None:
    """Drop the window indexes."""
    if _supports_concurrently():
        with op.get_context().autocommit_block():
            for name, _, _ in _INDEXES:
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"')
        return
    for name, _, _ in _INDEXES:
        op.drop_index(name, if_exists=True)
