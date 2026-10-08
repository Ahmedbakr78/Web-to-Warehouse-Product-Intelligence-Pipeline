"""Remove the scrollbar appearance axis.

Revision ID: 0004_remove_scrollbars
Revises: 0002_appearance_scrollbars
Create Date: 2026-10-08 10:10:00.000000

Drops ``app_user.scrollbars``. Scrollbars are gone from the product entirely -
hidden globally by CSS with no preference, control or stored value - so the
column has no reader or writer left. The downgrade re-adds it with the same
default for a clean round trip.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_remove_scrollbars"
down_revision: str | Sequence[str] | None = "0002_appearance_scrollbars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the scrollbars column."""
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.drop_column("scrollbars")


def downgrade() -> None:
    """Re-add the scrollbars column."""
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("scrollbars", sa.String(length=128), nullable=False, server_default="modern")
        )
