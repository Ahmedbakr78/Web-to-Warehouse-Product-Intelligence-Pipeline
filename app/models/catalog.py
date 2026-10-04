"""The retailer's internal product catalog (the comparison target of the pipeline)."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, MediumStr, ShortStr, TimestampMixin, UrlStr


class CatalogProduct(Base, TimestampMixin):
    """Internal ERP/PIM catalog row that scraped data is reconciled against."""

    __tablename__ = "catalog_product"

    sku: Mapped[str] = mapped_column(ShortStr, primary_key=True)
    name: Mapped[str] = mapped_column(MediumStr, nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(sa.Text)
    brand: Mapped[str | None] = mapped_column(ShortStr)
    category: Mapped[str | None] = mapped_column(MediumStr)
    supplier: Mapped[str | None] = mapped_column(ShortStr)
    cost_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    list_price: Mapped[float | None] = mapped_column(sa.Numeric(18, 4))
    currency: Mapped[str] = mapped_column(ShortStr, default="USD")
    qty_on_hand: Mapped[int] = mapped_column(sa.Integer, default=0)
    status: Mapped[str] = mapped_column(ShortStr, default="active")  # active | discontinued
    product_url: Mapped[str | None] = mapped_column(UrlStr)
    image_url: Mapped[str | None] = mapped_column(UrlStr)
    attributes: Mapped[dict | None] = mapped_column(JSONType, default=dict)

    __table_args__ = (
        sa.Index("ix_catalog_product_brand", "brand"),
        sa.Index("ix_catalog_product_category", "category"),
        sa.Index("ix_catalog_product_status", "status"),
    )


__all__ = ["CatalogProduct"]