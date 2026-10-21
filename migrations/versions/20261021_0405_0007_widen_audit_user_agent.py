"""Widen ``app_audit_log.user_agent`` so a real browser string fits.

Revision ID: 0007_widen_audit_user_agent
Revises: 0006_source_data_trust
Create Date: 2026-10-21 04:05:00.000000

The column was ``VARCHAR(128)`` while the code truncated the header to 255
characters, so any user-agent longer than 128 characters overflowed the column.
Chrome, Safari and Edge all send longer strings than that - which made *sign-in*
fail with a 500 on mobile, because the audit row written for a successful
login was the one that did not fit.

The column is widened to 512 characters, matching ``app_session.user_agent``
and the truncation the code already applies.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_widen_audit_user_agent"
down_revision: str | Sequence[str] | None = "0006_source_data_trust"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "app_audit_log"
_COLUMN = "user_agent"
_WIDTH = 512


def upgrade() -> None:
    """Widen the column to hold a full user-agent string."""
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(_COLUMN, type_=sa.String(length=_WIDTH), existing_type=sa.String(length=128))


def downgrade() -> None:
    """Narrow the column again."""
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(_COLUMN, type_=sa.String(length=128), existing_type=sa.String(length=_WIDTH))
