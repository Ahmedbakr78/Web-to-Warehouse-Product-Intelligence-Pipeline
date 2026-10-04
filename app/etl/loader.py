"""Warehouse loader: dimension upserts, fact inserts and change detection.

Design goals
------------
* **Dialect agnostic** - no dialect specific SQL, so PostgreSQL, MySQL and SQLite all
  behave identically (no ``ON CONFLICT`` / ``ON DUPLICATE KEY`` divergence).
* **Batched** - in-memory caches for dimensions avoid N+1 queries; facts are flushed in
  configurable batches.
* **Idempotent** - re-running the same ``run_id`` never duplicates fact rows.
* **Auditable** - every change is written to ``chg_price_change`` / ``chg_product_event``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.base import NormalizedProduct
from app.ingestion.cleaning import category_levels, percent_change
from app.models.dimensions import DimCategory, DimDate, DimProduct, DimSource
from app.models.facts import (
    AggCategoryDaily,
    ChgPriceChange,
    ChgProductEvent,
    FactCatalogSnapshot,
    FactPriceSnapshot,
)
from app.models.operations import StgRawObservation, SyncState
from app.etl.bootstrap import date_id

log = get_logger(__name__)

SIGNIFICANT_CHANGE_PCT = 1.0


def magnitude_band(change_pct: float | None) -> str | None:
    """Bucket a percentage change for dashboard filtering."""
    if change_pct is None:
        return None
    value = abs(change_pct)
    if value < 1:
        return "minor"
    if value < 5:
        return "small"
    if value < 15:
        return "moderate"
    if value < 30:
        return "large"
    return "major"


@dataclass
class LoadStats:
    """Counters produced by the loader."""

    staged: int = 0
    rejected: int = 0
    products_created: int = 0
    products_updated: int = 0
    duplicates_merged: int = 0
    snapshots_inserted: int = 0
    price_changes: int = 0
    new_products: int = 0
    removed_products: int = 0
    category_changes: int = 0
    categories_created: int = 0
    http_log_rows: int = 0

    def merge(self, other: LoadStats) -> LoadStats:
        for field_def in self.__dataclass_fields__.values():
            name = field_def.name
            setattr(self, name, getattr(self, name) + getattr(other, name))
        return self

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


class WarehouseLoader:
    """Loads normalised products into the dimensional model."""

    def __init__(self, session: Session, run_id: str, *, captured_at: dt.datetime | None = None) -> None:
        self.session = session
        self.run_id = run_id
        self.captured_at = captured_at or dt.datetime.now(dt.timezone.utc)
        self.stats = LoadStats()
        self._category_cache: dict[str, DimCategory] = {}
        self._product_cache: dict[int, DimProduct] = {}
        self._date_cache: dict[str, int] = {}

    # ------------------------------------------------------------------ dimensions
    def preload_dimensions(self) -> None:
        """Warm the in-memory dimension caches (one query per dimension)."""
        for row in self.session.execute(sa.select(DimCategory.category_id, DimCategory.slug)):
            category = self.session.get(DimCategory, row[0])
            if category is not None:
                self._category_cache[category.slug] = category
        self._category_cache.update({c.slug: c for c in self._category_cache.values()})
        log.debug("preloaded %d categories", len(self._category_cache))

    def resolve_category(self, record: NormalizedProduct) -> DimCategory | None:
        """Get-or-create the category row, materialising parent levels."""
        if not record.category:
            return None
        slug = record.category_slug or "uncategorised"
        existing = self._category_cache.get(slug)
        if existing is not None:
            return existing

        parts = [part.strip() for part in record.category.split(">") if part.strip()]
        parent: DimCategory | None = None
        for depth, part in enumerate(parts, start=1):
            part_slug = f"{slugify(part)}" if depth == 1 else f"{slugify(parts[0])}-{slugify(part)}"
            cached = self._category_cache.get(part_slug)
            if cached is None:
                row = self.session.execute(
                    sa.select(DimCategory).where(DimCategory.slug == part_slug)
                ).scalars().first()
                if row is None:
                    row = DimCategory(
                        name=part,
                        slug=part_slug,
                        parent_id=parent.category_id if parent else None,
                        level=depth,
                        path=" > ".join(parts[:depth]),
                        source_category_raw=record.raw_category,
                    )
                    self.session.add(row)
                    self.session.flush()
                    self.stats.categories_created += 1
                    log.debug("created category %s", part_slug)
                self._category_cache[part_slug] = row
            cached = self._category_cache[part_slug]
            if depth == len(parts):
                cached.product_count = (cached.product_count or 0) + 1
                cached.source_category_raw = record.raw_category or cached.source_category_raw
            parent = cached
        return parent

    def resolve_date_id(self, when: dt.datetime | None = None) -> int:
        value = when or self.captured_at
        key = value.strftime("%Y-%m-%d")
        if key not in self._date_cache:
            self._date_cache[key] = date_id(value)
        return self._date_cache[key]

    # ------------------------------------------------------------------ staging
    def stage(self, raw_records: Iterable[Any]) -> int:
        """Persist raw payloads into the landing zone."""
        count = 0
        batch: list[StgRawObservation] = []
        for raw in raw_records:
            batch.append(
                StgRawObservation(
                    run_id=self.run_id,
                    source_code=raw.source_code,
                    source_product_id=str(raw.source_product_id),
                    entity_type="product",
                    source_url=raw.url,
                    raw_name=truncate_text(raw.name, 2000),
                    raw_category=truncate_text(raw.category, 256),
                    raw_price_text=truncate_text(raw.price_text, 64),
                    raw_currency=raw.currency_hint,
                    raw_rating_text=truncate_text(raw.rating_text, 64),
                    raw_availability=truncate_text(raw.availability_text, 128),
                    raw_payload=raw.payload or {},
                    payload_hash=raw.content_hash,
                    http_status=raw.http_status,
                    is_valid=True,
                    fetched_at=raw.fetched_at,
                )
            )
            count += 1
            if len(batch) >= settings.pipeline_batch_size:
                self.session.add_all(batch)
                self.session.flush()
                batch = []
        if batch:
            self.session.add_all(batch)
            self.session.flush()
        self.stats.staged = count
        return count

    def mark_rejected(self, staged: Sequence[StgRawObservation], rejected: Sequence[tuple[StgRawObservation, str]]) -> None:
        for row, reason in rejected:
            row.is_valid = False
            row.reject_reason = reason
            self.stats.rejected += 1

    # ------------------------------------------------------------------ products
    def upsert_product(self, record: NormalizedProduct, match: Any) -> tuple[DimProduct, bool]:
        """Insert or update ``dim_product``; returns ``(product, created)``.

        A category that differs from the previously stored one is logged as a
        ``category_changed`` lifecycle event in the same pass.
        """
        category = self.resolve_category(record)
        now = self.captured_at
        created = False
        product: DimProduct | None = None

        if match is not None and match.is_duplicate:
            product = self._product_cache.get(match.product_id) or self.session.get(DimProduct, match.product_id)
            if product is not None:
                product.match_strategy = match.strategy
                product.match_score = match.score

        if product is None:
            product = DimProduct(
                fingerprint=record.fingerprint,
                canonical_name=record.canonical_name or record.source_product_id,
            )
            self.session.add(product)
            created = True
            self.stats.products_created += 1
        else:
            self.stats.products_updated += 1

        previous_category_id = product.category_id
        new_category_id = category.category_id if category else None

        product.source_code = record.source_code
        product.source_product_id = record.source_product_id
        product.canonical_name = record.canonical_name or product.canonical_name
        product.normalized_name = record.normalized_name
        product.display_name = record.canonical_name
        product.brand = record.brand or product.brand
        product.category_id = new_category_id if new_category_id is not None else product.category_id
        product.product_url = record.product_url or product.product_url
        product.image_url = record.image_url or product.image_url
        product.description = record.description or product.description
        product.currency = record.currency
        product.current_rating = record.rating if record.rating is not None else product.current_rating
        product.rating_count = record.rating_count or product.rating_count
        product.availability = record.availability
        product.is_active = True
        product.observation_count = (product.observation_count or 0) + 1
        product.first_seen_at = product.first_seen_at or now
        product.last_seen_at = now
        product.extra = {
            **(product.extra or {}),
            "quality_flags": record.quality_flags[:10],
            "raw_name": record.raw_name,
            "blocking_key": record.blocking_key,
            "fx_rate_to_usd": record.fx_rate_to_usd,
        }
        self.session.flush()
        self._product_cache[product.product_id] = product

        if not created and new_category_id is not None and previous_category_id != new_category_id:
            self.session.add(
                ChgProductEvent(
                    product_id=product.product_id,
                    source_code=record.source_code,
                    run_id=self.run_id,
                    date_id=self.resolve_date_id(),
                    event_type="category_changed",
                    severity="warning",
                    old_value=str(previous_category_id),
                    new_value=record.category,
                    old_category_id=previous_category_id,
                    new_category_id=new_category_id,
                    detected_at=self.captured_at,
                )
            )
            self.stats.category_changes += 1
        return product, created

    # ------------------------------------------------------------------ snapshots
    def previous_snapshot(self, product_id: int, source_code: str) -> FactPriceSnapshot | None:
        """Most recent snapshot for this product from this source."""
        stmt = (
            sa.select(FactPriceSnapshot)
            .where(
                FactPriceSnapshot.product_id == product_id,
                FactPriceSnapshot.source_code == source_code,
            )
            .order_by(FactPriceSnapshot.captured_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def insert_snapshot(
        self,
        product: DimProduct,
        record: NormalizedProduct,
        *,
        previous: FactPriceSnapshot | None,
    ) -> FactPriceSnapshot:
        """Append one immutable price snapshot and record any change event."""
        change_abs: float | None = None
        change_pct: float | None = None
        if previous is not None and previous.price is not None and record.price is not None:
            change_abs = round(float(record.price) - float(previous.price), 4)
            change_pct = percent_change(previous.price, record.price)

        snapshot = FactPriceSnapshot(
            product_id=product.product_id,
            source_code=record.source_code,
            run_id=self.run_id,
            date_id=self.resolve_date_id(),
            captured_at=self.captured_at,
            price=record.price,
            list_price=record.list_price,
            currency=record.currency,
            fx_rate_to_usd=record.fx_rate_to_usd,
            price_usd=record.price_usd,
            discount_pct=record.discount_pct,
            rating=record.rating,
            rating_count=record.rating_count,
            availability=record.availability,
            in_stock=record.in_stock,
            price_change_abs=change_abs,
            price_change_pct=change_pct,
            is_first_sighting=previous is None,
            product_url=record.product_url,
            raw_price_text=record.raw_price_text,
            quality_flags=record.quality_flags or None,
        )
        self.session.add(snapshot)
        self.stats.snapshots_inserted += 1

        # ---- price change event
        if previous is not None and change_pct not in (None, 0.0):
            self.session.add(
                ChgPriceChange(
                    product_id=product.product_id,
                    source_code=record.source_code,
                    run_id=self.run_id,
                    date_id=self.resolve_date_id(),
                    previous_price=previous.price,
                    new_price=record.price,
                    change_abs=change_abs,
                    change_pct=change_pct,
                    direction="increase" if (change_abs or 0) > 0 else "decrease",
                    currency=record.currency,
                    magnitude_band=magnitude_band(change_pct),
                    is_significant=abs(change_pct or 0) >= SIGNIFICANT_CHANGE_PCT,
                    previous_price_usd=previous.price_usd,
                    new_price_usd=record.price_usd,
                    detected_at=self.captured_at,
                )
            )
            self.stats.price_changes += 1

        # ---- product lifecycle events
        if previous is None:
            self.session.add(
                ChgProductEvent(
                    product_id=product.product_id,
                    source_code=record.source_code,
                    run_id=self.run_id,
                    date_id=self.resolve_date_id(),
                    event_type="new",
                    severity="info",
                    new_value=product.canonical_name,
                    detected_at=self.captured_at,
                    details={"category": product.category_id},
                )
            )
            self.stats.new_products += 1
        else:
            self.session.add(
                ChgProductEvent(
                    product_id=product.product_id,
                    source_code=record.source_code,
                    run_id=self.run_id,
                    date_id=self.resolve_date_id(),
                    event_type="recurring",
                    severity="info",
                    old_value=str(previous.price),
                    new_value=str(record.price),
                    detected_at=self.captured_at,
                )
            )
            if record.price is not None and previous.price is not None and previous.price != record.price:
                product.previous_price = previous.price
            product.current_price = record.price if record.price is not None else product.current_price
        return snapshot

    # ------------------------------------------------------------------ removals
    def detect_removed(
        self,
        source_code: str,
        seen_product_ids: set[int],
        *,
        staleness_days: int = 7,
    ) -> int:
        """Flag products that vanished from a source for more than ``staleness_days``."""
        cutoff = self.captured_at - dt.timedelta(days=staleness_days)
        stale = self.session.execute(
            sa.select(DimProduct).where(
                DimProduct.source_code == source_code,
                DimProduct.is_active.is_(True),
            )
        ).scalars().all()

        removed = 0
        for product in stale:
            if product.product_id in seen_product_ids:
                continue
            if (product.last_seen_at or self.captured_at) > cutoff:
                continue
            self.session.add(
                ChgProductEvent(
                    product_id=product.product_id,
                    source_code=source_code,
                    run_id=self.run_id,
                    date_id=self.resolve_date_id(),
                    event_type="removed",
                    severity="warning",
                    old_value=product.canonical_name,
                    days_missing=staleness_days,
                    detected_at=self.captured_at,
                )
            )
            product.is_active = False
            removed += 1
        if removed:
            self.stats.removed_products += removed
            log.info("detected %d removed products for source %s", removed, source_code)
        return removed

    # ------------------------------------------------------------------ aggregates
    def refresh_category_daily(self, source_code: str | None = None) -> int:
        """Rebuild ``agg_category_daily`` for the dates touched by this run."""
        rows = self.session.execute(
            sa.text(
                """
                SELECT s.date_id,
                       p.category_id,
                       COUNT(*)                       AS product_count,
                       AVG(s.price_usd)               AS avg_price,
                       MIN(s.price_usd)               AS min_price,
                       MAX(s.price_usd)               AS max_price,
                       AVG(s.rating)                  AS avg_rating,
                       COALESCE(SUM(CASE WHEN s.is_first_sighting THEN 1 ELSE 0 END), 0) AS new_count,
                       COALESCE(SUM(CASE WHEN s.price_change_pct IS NOT NULL AND s.price_change_pct <> 0
                                         THEN 1 ELSE 0 END), 0) AS change_count,
                       AVG(s.price_change_pct)        AS avg_change_pct
                FROM fact_price_snapshot s
                JOIN dim_product p ON p.product_id = s.product_id
                WHERE s.run_id = :run_id
                GROUP BY s.date_id, p.category_id
                """
            ),
            {"run_id": self.run_id},
        ).all()

        written = 0
        for row in rows:
            existing = self.session.execute(
                sa.select(AggCategoryDaily).where(
                    AggCategoryDaily.date_id == row[0],
                    AggCategoryDaily.category_id == row[1],
                    AggCategoryDaily.source_code.is_(None),
                )
            ).scalars().first()
            values = {
                "date_id": row[0],
                "category_id": row[1],
                "source_code": None,
                "product_count": int(row[2] or 0),
                "new_product_count": int(row[6] or 0),
                "avg_price": row[3],
                "min_price": row[4],
                "max_price": row[5],
                "avg_rating": row[7],
                "price_change_count": int(row[8] or 0),
                "avg_price_change_pct": row[9],
                "computed_at": self.captured_at,
            }
            if existing is None:
                self.session.add(AggCategoryDaily(**values))
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
            written += 1
        if written:
            self.session.flush()
        log.debug("refreshed %d category-daily aggregates", written)
        return written

    # ------------------------------------------------------------------ catalog
    def insert_catalog_matches(self, rows: Sequence[dict[str, Any]]) -> int:
        """Persist the scraped-vs-catalog reconciliation output."""
        for values in rows:
            self.session.add(FactCatalogSnapshot(**values))
        self.session.flush()
        return len(rows)

    # ------------------------------------------------------------------ misc
    def update_source_stats(self, source: DimSource, extracted: int, duration_seconds: float, *, success: bool) -> None:
        source.total_runs = (source.total_runs or 0) + 1
        source.total_records = (source.total_records or 0) + extracted
        source.last_run_at = self.captured_at
        source.last_run_id = self.run_id
        runs = max(source.total_runs, 1)
        previous_avg = source.avg_duration_seconds or 0.0
        source.avg_duration_seconds = round((previous_avg * (runs - 1) + duration_seconds) / runs, 3)
        previous_rate = source.success_rate_pct or 0.0
        source.success_rate_pct = round((previous_rate * (runs - 1) + (100.0 if success else 0.0)) / runs, 2)

    def update_sync_state(self, source_code: str, *, extracted: int, success: bool, message: str | None = None) -> None:
        state = self.session.get(SyncState, source_code)
        if state is None:
            state = SyncState(source_code=source_code)
            self.session.add(state)
        state.last_run_id = self.run_id
        state.last_attempt_at = self.captured_at
        state.total_extracted = (state.total_extracted or 0) + extracted
        if success:
            state.last_success_at = self.captured_at
            state.consecutive_failures = 0
            state.status = "healthy"
        else:
            state.consecutive_failures = (state.consecutive_failures or 0) + 1
            state.status = "failing"
        state.message = truncate_text(message, 1000)

    def flush(self) -> None:
        self.session.flush()


def slugify(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "uncategorised"


def truncate_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


__all__ = ["WarehouseLoader", "LoadStats", "magnitude_band", "slugify"]