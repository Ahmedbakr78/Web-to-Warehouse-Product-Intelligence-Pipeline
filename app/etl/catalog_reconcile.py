"""Reconciliation between scraped records and the retailer's internal catalog.

For every active catalog SKU the pipeline looks for the best matching scraped product
using a three-stage match cascade:

1. ``source_product_id`` == catalog SKU (exact identifier match)
2. normalised-name equality
3. fuzzy similarity above the configured threshold

The result is stored in ``fact_catalog_snapshot`` including the **price gap**, which
is the single most valuable output for a retailer (are we cheaper or dearer than the
market?).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion.cleaning import normalise_name_key, percent_change
from app.ingestion.dedupe import combined_similarity
from app.models.catalog import CatalogProduct
from app.models.facts import FactCatalogSnapshot
from app.models.operations import EtlRun

log = get_logger(__name__)

PRICE_GAP_THRESHOLD_PCT = 1.0


@dataclass
class CatalogMatchResult:
    """Outcome of reconciling one catalog SKU."""

    catalog_sku: str
    product_id: int | None
    match_status: str          # matched | unmatched | ambiguous
    strategy: str | None = None
    similarity: float | None = None
    scraped_name: str | None = None
    catalog_name: str | None = None
    scraped_price: float | None = None
    catalog_price: float | None = None
    price_gap_abs: float | None = None
    price_gap_pct: float | None = None
    category_match: bool | None = None
    brand_match: bool | None = None
    candidates: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_price_mismatch(self) -> bool:
        if self.price_gap_pct is None:
            return False
        return abs(self.price_gap_pct) >= PRICE_GAP_THRESHOLD_PCT


class CatalogReconciler:
    """Matches the internal catalog against the freshly loaded warehouse."""

    def __init__(
        self,
        session: Session,
        run_id: str,
        *,
        threshold: float = 0.86,
        block_length: int = 4,
        min_pool: int = 12,
        max_pool: int = 400,
    ) -> None:
        self.session = session
        self.run_id = run_id
        self.threshold = threshold
        self.block_length = block_length
        self.min_pool = min_pool
        self.max_pool = max_pool
        self._by_block: dict[str, list[Any]] = {}
        self._by_token: dict[str, list[Any]] = {}
        self._index_ready = False

    # ------------------------------------------------------------------ helpers
    def _catalog_rows(self, only_active: bool = True) -> list[CatalogProduct]:
        stmt = sa.select(CatalogProduct)
        if only_active:
            stmt = stmt.where(CatalogProduct.status == "active")
        return list(self.session.execute(stmt.limit(5000)).scalars())

    def _latest_prices(self) -> dict[int, tuple[float | None, str | None, int | None, str | None]]:
        """product_id -> (price, currency, rating, category_name) from the newest snapshot."""
        rows = self.session.execute(
            sa.text(
                """
                SELECT s.product_id, s.price, s.currency, p.canonical_name, p.brand,
                       c.name AS category_name, s.captured_at
                FROM fact_price_snapshot s
                JOIN dim_product p ON p.product_id = s.product_id
                LEFT JOIN dim_category c ON c.category_id = p.category_id
                WHERE s.captured_at = (
                    SELECT MAX(s2.captured_at) FROM fact_price_snapshot s2
                    WHERE s2.product_id = s.product_id AND s2.source_code = s.source_code
                )
                """
            )
        ).all()
        latest: dict[int, tuple[Any, ...]] = {}
        for row in rows:
            current = latest.get(row[0])
            if current is None or str(row[6]) > str(current[5]):
                latest[row[0]] = (row[1], row[2], row[3], row[4], row[5], row[6])
        return {pid: (value[0], value[1], value[4]) for pid, value in latest.items()}

    def _candidate_products(self, catalog: Sequence[CatalogProduct]) -> list[Any]:
        """Load the products worth comparing (active, seen recently)."""
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
        return list(
            self.session.execute(
                sa.text(
                    """
                    SELECT DISTINCT p.product_id, p.canonical_name, p.normalized_name,
                                    p.brand, p.source_code, p.source_product_id,
                                    p.fingerprint, p.match_strategy, p.match_score
                    FROM dim_product p
                    LEFT JOIN dim_category c ON c.category_id = p.category_id
                    WHERE p.is_active AND (p.last_seen_at >= :cutoff OR p.last_seen_at IS NULL)
                    """
                ),
                {"cutoff": cutoff},
            )
        )

    # ------------------------------------------------------------------ blocking
    def _build_indexes(self, candidates: Sequence[Any]) -> None:
        """Pre-compute blocking indexes so each catalog row only sees a handful of
        candidate products instead of the whole catalogue (O(n*m) -> ~O(n))."""
        if self._index_ready:
            return
        self._by_block: dict[str, list[Any]] = {}
        self._by_token: dict[str, list[Any]] = {}
        for candidate in candidates:
            key = candidate.normalized_name or ""
            self._by_block.setdefault(key[: self.block_length], []).append(candidate)
            for token in set(key.split()):
                self._by_token.setdefault(token, []).append(candidate)
        self._index_ready = True

    def _narrow_candidates(
        self, catalog_row: CatalogProduct, catalog_key: str, candidates: Sequence[Any]
    ) -> list[Any]:
        self._build_indexes(candidates)
        pool: list[Any] = []
        seen: set[int] = set()

        for candidate in self._by_block.get(catalog_key[: self.block_length], []):
            if candidate.product_id not in seen:
                seen.add(candidate.product_id)
                pool.append(candidate)

        if len(pool) < self.min_pool:
            # Fall back to a rare-token pre-filter (two shared tokens is a strong signal).
            shared: dict[int, Any] = {}
            for token in set(catalog_key.split()):
                for candidate in self._by_token.get(token, []):
                    shared[candidate.product_id] = candidate
            for candidate in shared.values():
                if candidate.product_id not in seen:
                    seen.add(candidate.product_id)
                    pool.append(candidate)

        if not pool:
            pool = list(candidates)[: self.min_pool * 3]
        return pool[: self.max_pool]

    # ------------------------------------------------------------------ matching
    def match_one(
        self,
        catalog_row: CatalogProduct,
        candidates: Sequence[Any],
        latest_prices: dict[int, tuple[Any, ...]],
    ) -> CatalogMatchResult:
        catalog_key = normalise_name_key(catalog_row.name)
        by_id: dict[str, Any] = {}
        by_key: dict[str, list[Any]] = {}
        for candidate in candidates:
            if candidate.source_product_id:
                by_id[str(candidate.source_product_id).strip().lower()] = candidate
            by_key.setdefault(candidate.normalized_name or "", []).append(candidate)

        # ---- stage 1: identifier match
        chosen: Any = None
        strategy = None
        similarity: float | None = None
        if catalog_row.sku:
            chosen = by_id.get(catalog_row.sku.strip().lower())
            if chosen is not None:
                strategy, similarity = "sku", 1.0

        # ---- stage 2: exact normalised name
        if chosen is None and catalog_key:
            exact = by_key.get(catalog_key)
            if exact:
                chosen = exact[0]
                strategy, similarity = "normalized_name", 1.0

        # ---- stage 3: fuzzy (restricted to plausible candidates via blocking)
        if chosen is None and catalog_key:
            pool = self._narrow_candidates(catalog_row, catalog_key, candidates)
            best_score, best_candidate = 0.0, None
            for candidate in pool:
                if not candidate.normalized_name:
                    continue
                score, _parts = combined_similarity(
                    catalog_row.name,
                    candidate.canonical_name,
                    brand_a=catalog_row.brand,
                    brand_b=candidate.brand,
                    category_a=catalog_row.category,
                )
                if score > best_score:
                    best_score, best_candidate = score, candidate
            if best_candidate is not None and best_score >= self.threshold:
                chosen = best_candidate
                strategy, similarity = "fuzzy", round(best_score, 4)

        if chosen is None:
            return CatalogMatchResult(
                catalog_sku=catalog_row.sku,
                product_id=None,
                match_status="unmatched",
                catalog_name=catalog_row.name,
                catalog_price=float(catalog_row.list_price) if catalog_row.list_price is not None else None,
                candidates=len(candidates),
            )

        raw_scraped, scraped_currency, category_name = latest_prices.get(chosen.product_id, (None, None, None))
        # PostgreSQL returns Decimal for Numeric columns - normalise to float here.
        scraped_price = float(raw_scraped) if raw_scraped is not None else None
        catalog_price = float(catalog_row.list_price) if catalog_row.list_price is not None else None
        gap_abs = None
        gap_pct = None
        if scraped_price is not None and catalog_price is not None:
            gap_abs = round(scraped_price - catalog_price, 4)
            gap_pct = percent_change(catalog_price, scraped_price)

        brand_match = None
        if catalog_row.brand and chosen.brand:
            brand_match = catalog_row.brand.strip().lower() == (chosen.brand or "").strip().lower()
        category_match = None
        if catalog_row.category and category_name:
            category_match = catalog_row.category.strip().lower() == category_name.strip().lower()

        return CatalogMatchResult(
            catalog_sku=catalog_row.sku,
            product_id=int(chosen.product_id),
            match_status="matched",
            strategy=strategy,
            similarity=similarity,
            scraped_name=chosen.canonical_name,
            catalog_name=catalog_row.name,
            scraped_price=float(scraped_price) if scraped_price is not None else None,
            catalog_price=catalog_price,
            price_gap_abs=gap_abs,
            price_gap_pct=gap_pct,
            category_match=category_match,
            brand_match=brand_match,
            candidates=len(candidates),
            details={
                "scraped_currency": scraped_currency,
                "scraped_source": chosen.source_code,
                "scraped_category": category_name,
                "catalog_category": catalog_row.category,
                "supplier": catalog_row.supplier,
            },
        )

    # ------------------------------------------------------------------ entry point
    def run(self, *, persist: bool = True) -> list[CatalogMatchResult]:
        catalog_rows = self._catalog_rows()
        if not catalog_rows:
            log.info("catalog reconciliation skipped - internal catalog is empty")
            return []
        candidates = self._candidate_products(catalog_rows)
        latest_prices = self._latest_prices()

        results: list[CatalogMatchResult] = []
        for catalog_row in catalog_rows:
            result = self.match_one(catalog_row, candidates, latest_prices)
            results.append(result)
            if persist:
                self.session.add(
                    FactCatalogSnapshot(
                        run_id=self.run_id,
                        catalog_sku=result.catalog_sku,
                        product_id=result.product_id,
                        match_status=result.match_status,
                        match_strategy=result.strategy,
                        similarity_score=result.similarity,
                        scraped_name=(result.scraped_name or None),
                        catalog_name=result.catalog_name,
                        scraped_price=result.scraped_price,
                        catalog_price=result.catalog_price,
                        price_gap_abs=result.price_gap_abs,
                        price_gap_pct=result.price_gap_pct,
                        category_match=result.category_match,
                        brand_match=result.brand_match,
                        is_price_mismatch=result.is_price_mismatch,
                        matched_at=dt.datetime.now(dt.timezone.utc),
                        details={**result.details, "candidates": result.candidates},
                    )
                )
        self.session.flush()

        matched = sum(1 for r in results if r.match_status == "matched")
        mismatches = sum(1 for r in results if r.is_price_mismatch)
        log.info(
            "catalog reconciliation run=%s matched=%d/%d price_mismatches=%d",
            self.run_id, matched, len(results), mismatches,
        )
        return results


def reconciliation_summary(results: Sequence[CatalogMatchResult]) -> dict[str, Any]:
    """Aggregate counters used by the run record and the dashboard."""
    if not results:
        return {
            "total": 0, "matched": 0, "unmatched": 0, "match_rate_pct": 0.0,
            "price_mismatches": 0, "avg_similarity": None, "by_strategy": {},
        }
    matched = sum(1 for r in results if r.match_status == "matched")
    similarities = [r.similarity for r in results if r.similarity is not None]
    by_strategy: dict[str, int] = {}
    for result in results:
        if result.strategy:
            by_strategy[result.strategy] = by_strategy.get(result.strategy, 0) + 1
    return {
        "total": len(results),
        "matched": matched,
        "unmatched": len(results) - matched,
        "match_rate_pct": round(matched / len(results) * 100, 2),
        "price_mismatches": sum(1 for r in results if r.is_price_mismatch),
        "avg_similarity": round(sum(similarities) / len(similarities), 4) if similarities else None,
        "by_strategy": by_strategy,
    }


__all__ = ["CatalogReconciler", "CatalogMatchResult", "reconciliation_summary", "PRICE_GAP_THRESHOLD_PCT"]