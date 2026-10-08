"""Pipeline resilience: cross-source duplicates and mid-run source failures.

Regression tests for a production incident where two marketplace sources resolved
to the same canonical product inside one run. The fact grain is one row per
(product, run), so the second snapshot violated ``uq_fact_price_product_run``;
worse, the failed flush poisoned the run-wide transaction, so the run died as
``failed`` instead of continuing as ``partial``.

Covered here:

* a product observed by two sources in one run yields exactly one snapshot;
* a source that explodes mid-run does not take the good sources (or the
  ``etl_run`` row) down with it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

import pytest
import sqlalchemy as sa

from app.etl.pipeline import Pipeline, PipelineConfig
from app.ingestion.base import ProductSource, RawProduct, register_source

pytestmark = pytest.mark.integration

SHARED_NAME = "pytest resilience widget 3000"


def _raw(code: str, pid: str, name: str = SHARED_NAME) -> RawProduct:
    return RawProduct(
        source_code=code,
        source_product_id=pid,
        name=name,
        category="pytest widgets",
        price_text="$19.99",
        currency_hint="USD",
        availability_text="in stock",
        url=f"https://example.com/{pid}",
    )


@register_source
class PytestResilienceAlphaSource(ProductSource):
    code: ClassVar[str] = "pytest_resilience_alpha"
    name: ClassVar[str] = "pytest resilience alpha"
    base_url: ClassVar[str] = "https://example.com"
    terms_url: ClassVar[str | None] = "https://example.com/terms"
    description: ClassVar[str] = "first of a same-product pair"

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        yield _raw(self.code, "ALPHA-1")


@register_source
class PytestResilienceBetaSource(ProductSource):
    code: ClassVar[str] = "pytest_resilience_beta"
    name: ClassVar[str] = "pytest resilience beta"
    base_url: ClassVar[str] = "https://example.com"
    terms_url: ClassVar[str | None] = "https://example.com/terms"
    description: ClassVar[str] = "second of a same-product pair"

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        yield _raw(self.code, "BETA-1")


@register_source
class PytestResilienceBoomSource(ProductSource):
    code: ClassVar[str] = "pytest_resilience_boom"
    name: ClassVar[str] = "pytest resilience boom"
    base_url: ClassVar[str] = "https://example.com"
    terms_url: ClassVar[str | None] = "https://example.com/terms"
    description: ClassVar[str] = "explodes after one valid record"

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        yield _raw(self.code, "BOOM-1", name="pytest boom widget")
        raise RuntimeError("boom: upstream exploded mid-fetch")


def _snapshots_for_run(db, run_id: str, name: str) -> list:
    # Names are cleaned on the way in (lower-case titles are title-cased), so
    # match case-insensitively rather than repeating the cleaning rules here.
    return (
        db.execute(
            sa.text(
                """
                SELECT s.snapshot_id FROM fact_price_snapshot s
                JOIN dim_product p ON p.product_id = s.product_id
                WHERE s.run_id = :rid AND lower(p.canonical_name) = lower(:name)
                """
            ),
            {"rid": run_id, "name": name},
        )
        .scalars()
        .all()
    )


def test_two_sources_sharing_one_product_yield_one_snapshot(db):
    """The exact production incident: no UniqueViolation, run stays healthy."""
    result = Pipeline(
        PipelineConfig(
            sources=["pytest_resilience_alpha", "pytest_resilience_beta"],
            limit_per_source=10,
            skip_dq=True,
            skip_catalog=True,
        )
    ).run()

    assert result.status in {"success", "partial"}, result.error
    assert result.sources_processed == ["pytest_resilience_alpha", "pytest_resilience_beta"]
    assert not result.sources_failed
    assert (
        _snapshots_for_run(db, result.run_id, SHARED_NAME)
        and len(_snapshots_for_run(db, result.run_id, SHARED_NAME)) == 1
    )


def test_exploding_source_does_not_kill_the_run(db):
    """Good source first, boom source second: partial run, good data committed."""
    result = Pipeline(
        PipelineConfig(
            sources=["pytest_resilience_alpha", "pytest_resilience_boom"],
            limit_per_source=10,
            skip_dq=True,
            skip_catalog=True,
        )
    ).run()

    assert result.status == "partial", result.error
    assert "pytest_resilience_alpha" in result.sources_processed
    assert "pytest_resilience_boom" in result.sources_failed
    assert result.warnings
    # The good source's snapshot survived: the failed source rolled back alone.
    assert len(_snapshots_for_run(db, result.run_id, SHARED_NAME)) == 1
    # And the run row itself was persisted with its partial status.
    row = db.execute(
        sa.text("SELECT status FROM etl_run WHERE run_id = :rid"), {"rid": result.run_id}
    ).scalar()
    assert row == "partial"
