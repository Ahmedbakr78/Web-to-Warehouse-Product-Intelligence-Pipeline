"""Conformed and descriptive dimensions (``dim_*``).

A Kimball-style star is used deliberately: the analytical queries in
``db/analysis`` stay simple, fast and readable because all descriptive attributes
live in dimensions while ``fact_*`` tables only carry keys, measures and time.
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UTCDateTime, Base, JSONType, MediumStr, ShortStr, TimestampMixin, UrlStr, utcnow


class DimSource(Base, TimestampMixin):
    """One permitted upstream source (API endpoint or permitted website)."""

    __tablename__ = "dim_source"

    source_code: Mapped[str] = mapped_column(ShortStr, primary_key=True)
    name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    kind: Mapped[str] = mapped_column(ShortStr, nullable=False, default="api")  # api | scrape
    base_url: Mapped[str] = mapped_column(UrlStr, nullable=False)
    robots_url: Mapped[str | None] = mapped_column(UrlStr)
    terms_url: Mapped[str | None] = mapped_column(UrlStr)
    license_note: Mapped[str | None] = mapped_column(sa.Text)
    rate_limit_per_minute: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=30)
    min_delay_seconds: Mapped[float] = mapped_column(sa.Float, nullable=False, default=2.0)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    terms_allowed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    robots_checked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    last_run_id: Mapped[str | None] = mapped_column(ShortStr)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    total_records: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0)
    total_runs: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    success_rate_pct: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    avg_duration_seconds: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    config: Mapped[dict | None] = mapped_column(JSONType, default=dict)

    __table_args__ = (
        sa.Index("ix_dim_source_enabled", "enabled"),
        sa.Index("ix_dim_source_kind", "kind"),
    )


class DimCategory(Base, TimestampMixin):
    """Normalised category hierarchy (self referencing parent for drill-down)."""

    __tablename__ = "dim_category"

    category_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    slug: Mapped[str] = mapped_column(ShortStr, nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("dim_category.category_id"))
    level: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=1)
    path: Mapped[str | None] = mapped_column(MediumStr)
    source_category_raw: Mapped[str | None] = mapped_column(MediumStr)
    product_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    avg_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))

    __table_args__ = (
        sa.Index("ix_dim_category_parent", "parent_id"),
        sa.Index("ix_dim_category_name", "name"),
    )


class DimProduct(Base, TimestampMixin):
    """Canonical (deduplicated) product entity - the grain of the pipeline."""

    __tablename__ = "dim_product"

    product_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    source_product_id: Mapped[str | None] = mapped_column(ShortStr)
    source_code: Mapped[str | None] = mapped_column(ShortStr)
    canonical_name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    normalized_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(MediumStr)
    brand: Mapped[str | None] = mapped_column(ShortStr)
    category_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("dim_category.category_id"))
    product_url: Mapped[str | None] = mapped_column(UrlStr)
    image_url: Mapped[str | None] = mapped_column(UrlStr)
    description: Mapped[str | None] = mapped_column(sa.Text)
    currency: Mapped[str | None] = mapped_column(ShortStr)
    current_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    previous_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    current_rating: Mapped[float | None] = mapped_column(sa.Float)
    rating_count: Mapped[int | None] = mapped_column(sa.Integer)
    availability: Mapped[str | None] = mapped_column(ShortStr)  # in_stock | out_of_stock | preorder
    fingerprint: Mapped[str] = mapped_column(ShortStr, nullable=False, index=True)
    match_strategy: Mapped[str | None] = mapped_column(ShortStr)  # exact|normalized|fuzzy|manual
    match_score: Mapped[float | None] = mapped_column(sa.Float)
    matched_product_id: Mapped[int | None] = mapped_column(sa.Integer)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    observation_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    extra: Mapped[dict | None] = mapped_column(JSONType, default=dict)

    __table_args__ = (
        sa.Index("ix_dim_product_category", "category_id"),
        sa.Index("ix_dim_product_name_search", "canonical_name"),
        sa.Index("ix_dim_product_active_seen", "is_active", "last_seen_at"),
        sa.Index("ix_dim_product_brand", "brand"),
        sa.Index("ix_dim_product_source_ext", "source_code", "source_product_id"),
    )


class DimDate(Base):
    """Pre-populated date dimension for fast time filtering and labelling."""

    __tablename__ = "dim_date"

    date_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)  # YYYYMMDD
    full_date: Mapped[dt.date] = mapped_column(sa.Date, nullable=False, unique=True)
    year: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    quarter: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    day: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    month_name: Mapped[str | None] = mapped_column(ShortStr)
    day_name: Mapped[str | None] = mapped_column(ShortStr)
    week_of_year: Mapped[int | None] = mapped_column(sa.SmallInteger)
    is_weekend: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    is_month_start: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    is_month_end: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    iso_week: Mapped[int | None] = mapped_column(sa.SmallInteger)

    __table_args__ = (
        sa.Index("ix_dim_date_year_month", "year", "month"),
    )


class DimCurrency(Base, TimestampMixin):
    """Currency reference data used for FX normalisation."""

    __tablename__ = "dim_currency"

    currency_code: Mapped[str] = mapped_column(ShortStr, primary_key=True)
    currency_name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    symbol: Mapped[str | None] = mapped_column(sa.String(8))
    rate_to_usd: Mapped[float] = mapped_column(sa.Numeric(18, 6), nullable=False, default=1.0)
    rate_source: Mapped[str | None] = mapped_column(ShortStr, default="static")
    as_of: Mapped[dt.date | None] = mapped_column(sa.Date)


__all__ = ["DimSource", "DimCategory", "DimProduct", "DimDate", "DimCurrency"]