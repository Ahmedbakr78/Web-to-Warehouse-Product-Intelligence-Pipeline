"""Declarative base, reusable mixins and dialect-portable column types."""

from __future__ import annotations

import datetime as dt
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, registry

# --------------------------------------------------------------------------------------
# Portability helpers
# --------------------------------------------------------------------------------------
# MySQL has no native JSON guarantee on old versions and TEXT columns behave more
# predictably for our payloads, while PostgreSQL keeps its rich JSONB type.
JSONType = sa.JSON().with_variant(sa.Text(length=65_535), "mysql")
# Short VARCHARs everywhere: MySQL cannot index unbounded TEXT columns.
ShortStr = sa.String(128)
MediumStr = sa.String(512)
UrlStr = sa.String(2048)


class Base(DeclarativeBase):
    """Declarative base with a shared metadata and naming convention."""

    metadata = sa.MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )

    type_annotation_map = {dict[str, Any]: JSONType, dt.date: sa.Date}

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Shallow dict representation (API friendly)."""
        exclude = exclude or set()
        return {
            column.name: getattr(self, column.name)
            for column in sa.inspect(type(self)).columns
            if column.name not in exclude
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        pk = sa.inspect(self).identity
        return f"<{type(self).__name__} {pk}>"


class TimestampMixin:
    """``created_at`` / ``updated_at`` columns maintained by the ORM."""

    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), default=dt.datetime.now(dt.timezone.utc), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=dt.datetime.now(dt.timezone.utc),
        onupdate=dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )


class NumericMixin:
    """Money columns are always ``Numeric(18, 4)`` so PG and MySQL agree exactly."""

    @staticmethod
    def money() -> Any:
        return sa.Numeric(18, 4)

    @staticmethod
    def ratio() -> Any:
        return sa.Numeric(9, 6)


def utcnow() -> dt.datetime:
    """Timezone-aware ``now`` used across the codebase."""
    return dt.datetime.now(dt.timezone.utc)


def as_aware(value: dt.datetime | None) -> dt.datetime | None:
    """Attach UTC to naive datetimes (MySQL drops tz information)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def table_args_indexes(*indexes: tuple[sa.Index, ...]) -> tuple[Any, ...]:
    """Small helper so model definitions stay readable."""
    return tuple(indexes)


__all__ = [
    "Base",
    "TimestampMixin",
    "NumericMixin",
    "JSONType",
    "ShortStr",
    "MediumStr",
    "UrlStr",
    "utcnow",
    "as_aware",
    "table_args_indexes",
    "registry",
]