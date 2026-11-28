"""Fact tables: the historical price snapshot, catalog facts and change events."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, ShortStr, UrlStr, UTCDateTime, utcnow


class FactPriceSnapshot(Base):
    """Historical product-price table (append-only, one row per product/run).

    This is the single most important deliverable of the project: every price that
    has ever been observed is preserved here, which makes trend, volatility and
    change analysis a pure SQL exercise.
    """

    __tablename__ = "fact_price_snapshot"

    snapshot_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("dim_product.product_id"), nullable=False
    )
    source_code: Mapped[str] = mapped_column(
        ShortStr, sa.ForeignKey("dim_source.source_code"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(ShortStr, sa.ForeignKey("etl_run.run_id"), nullable=False)
    date_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("dim_date.date_id"), nullable=False)
    captured_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    list_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    currency: Mapped[str] = mapped_column(ShortStr, nullable=False, default="USD")
    fx_rate_to_usd: Mapped[float] = mapped_column(sa.Numeric(18, 6), default=1.0)
    price_usd: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    discount_pct: Mapped[float | None] = mapped_column(sa.Float)
    rating: Mapped[float | None] = mapped_column(sa.Float)
    rating_count: Mapped[int | None] = mapped_column(sa.Integer)
    availability: Mapped[str | None] = mapped_column(ShortStr)
    in_stock: Mapped[bool | None] = mapped_column(sa.Boolean)
    price_change_abs: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    price_change_pct: Mapped[float | None] = mapped_column(sa.Float)
    is_first_sighting: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    product_url: Mapped[str | None] = mapped_column(UrlStr)
    raw_price_text: Mapped[str | None] = mapped_column(ShortStr)
    quality_flags: Mapped[list | None] = mapped_column(JSONType, default=None)

    __table_args__ = (
        sa.UniqueConstraint("product_id", "run_id", name="uq_fact_price_product_run"),
        sa.Index("ix_fact_price_product_time", "product_id", "captured_at"),
        sa.Index("ix_fact_price_date", "date_id"),
        sa.Index("ix_fact_price_source_date", "source_code", "date_id"),
        sa.Index("ix_fact_price_run", "run_id"),
        sa.Index("ix_fact_price_change", "price_change_pct"),
    )


class FactCatalogSnapshot(Base):
    """Comparison of scraped records against the retailer internal catalog per run."""

    __tablename__ = "fact_catalog_snapshot"

    match_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ShortStr, sa.ForeignKey("etl_run.run_id"), nullable=False)
    catalog_sku: Mapped[str] = mapped_column(ShortStr, sa.ForeignKey("catalog_product.sku"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("dim_product.product_id"))
    source_code: Mapped[str | None] = mapped_column(ShortStr, sa.ForeignKey("dim_source.source_code"))
    date_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("dim_date.date_id"))
    match_status: Mapped[str] = mapped_column(ShortStr, nullable=False, default="matched")
    match_strategy: Mapped[str | None] = mapped_column(ShortStr)
    similarity_score: Mapped[float | None] = mapped_column(sa.Float)
    scraped_name: Mapped[str | None] = mapped_column(sa.Text)
    catalog_name: Mapped[str | None] = mapped_column(sa.Text)
    scraped_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    catalog_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    price_gap_abs: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    price_gap_pct: Mapped[float | None] = mapped_column(sa.Float)
    category_match: Mapped[bool | None] = mapped_column(sa.Boolean)
    brand_match: Mapped[bool | None] = mapped_column(sa.Boolean)
    is_price_mismatch: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    matched_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONType, default=dict)

    __table_args__ = (
        sa.UniqueConstraint("run_id", "catalog_sku", name="uq_fact_catalog_run_sku"),
        sa.Index("ix_fact_catalog_status", "match_status"),
        sa.Index("ix_fact_catalog_similarity", "similarity_score"),
        sa.Index("ix_fact_catalog_price_gap", "price_gap_pct"),
    )


class ChgPriceChange(Base):
    """Price-change event feed derived from consecutive snapshots."""

    __tablename__ = "chg_price_change"

    change_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("dim_product.product_id"), nullable=False
    )
    source_code: Mapped[str] = mapped_column(
        ShortStr, sa.ForeignKey("dim_source.source_code"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(ShortStr, sa.ForeignKey("etl_run.run_id"), nullable=False)
    date_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("dim_date.date_id"), nullable=False)
    previous_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    new_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    change_abs: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    change_pct: Mapped[float | None] = mapped_column(sa.Float)
    direction: Mapped[str] = mapped_column(ShortStr, nullable=False, default="increase")
    currency: Mapped[str] = mapped_column(ShortStr, default="USD")
    magnitude_band: Mapped[str | None] = mapped_column(ShortStr)
    is_significant: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    previous_price_usd: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    new_price_usd: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    detected_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("product_id", "run_id", name="uq_chg_price_product_run"),
        sa.Index("ix_chg_price_date_dir", "date_id", "direction"),
        sa.Index("ix_chg_price_pct", "change_pct"),
        sa.Index("ix_chg_price_significant", "is_significant"),
    )


class ChgProductEvent(Base):
    """Product lifecycle events: new, recurring, removed, reactivated, recategorised."""

    __tablename__ = "chg_product_event"

    event_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("dim_product.product_id"), nullable=False
    )
    source_code: Mapped[str] = mapped_column(
        ShortStr, sa.ForeignKey("dim_source.source_code"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(ShortStr, sa.ForeignKey("etl_run.run_id"), nullable=False)
    date_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("dim_date.date_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(
        ShortStr, nullable=False
    )  # new|removed|recurring|reactivated|category_changed|availability_changed
    severity: Mapped[str] = mapped_column(ShortStr, default="info")
    old_value: Mapped[str | None] = mapped_column(sa.Text)
    new_value: Mapped[str | None] = mapped_column(sa.Text)
    old_category_id: Mapped[int | None] = mapped_column(sa.Integer)
    new_category_id: Mapped[int | None] = mapped_column(sa.Integer)
    days_missing: Mapped[int | None] = mapped_column(sa.Integer)
    detected_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONType, default=dict)

    __table_args__ = (
        sa.Index("ix_chg_event_type_date", "event_type", "date_id"),
        sa.Index("ix_chg_event_product", "product_id"),
        sa.Index("ix_chg_event_run", "run_id"),
    )


class AggCategoryDaily(Base):
    """Pre-aggregated daily category rollup (fast dashboards, cheap refresh)."""

    __tablename__ = "agg_category_daily"

    agg_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    date_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("dim_date.date_id"), nullable=False)
    category_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("dim_category.category_id"), nullable=False
    )
    source_code: Mapped[str | None] = mapped_column(ShortStr)
    product_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    new_product_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    removed_product_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    avg_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    median_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    min_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    max_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    avg_rating: Mapped[float | None] = mapped_column(sa.Float)
    price_change_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    avg_price_change_pct: Mapped[float | None] = mapped_column(sa.Float)
    computed_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("date_id", "category_id", "source_code", name="uq_agg_cat_date_cat_source"),
        sa.Index("ix_agg_cat_date", "date_id"),
    )


__all__ = [
    "FactPriceSnapshot",
    "FactCatalogSnapshot",
    "ChgPriceChange",
    "ChgProductEvent",
    "AggCategoryDaily",
]
