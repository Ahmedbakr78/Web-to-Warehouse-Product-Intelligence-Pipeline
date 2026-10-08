"""Appearance axis: scrollbar presentation preference.

Revision ID: 0002_appearance_scrollbars
Revises: 0001_initial
Create Date: 2026-10-07 21:00:00.000000

Adds ``app_user.scrollbars`` (`modern` | `auto` | `hidden`, default `modern`)
alongside the existing appearance axes (`theme`, `accent`, `density`, `motion`,
`direction`, `font_scale`). The batch form keeps SQLite ALTER working - it
rewrites the table instead - and stays a no-op on PostgreSQL/MySQL where a
plain ADD COLUMN applies.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_appearance_scrollbars"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the scrollbars column with the safe default."""
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scrollbars", sa.String(length=128), nullable=False, server_default="modern"))


def downgrade() -> None:
    """Drop the scrollbars column."""
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.drop_column("scrollbars")
