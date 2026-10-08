"""Pipeline resilience: cross-source duplicates and mid-run source failures.

Regression tests for production incidents where one bad source took down the
whole run:

* two marketplace sources resolving to the same canonical product violated the
  one-row-per-(product, run) grain (UniqueViolation at flush);
* a dead database connection mid-flush (server restart, network blip) poisoned
  the run-wide transaction, so bookkeeping itself raised PendingRollbackError
  and the run died as ``failed`` instead of continuing as ``partial``.

Covered here:

* a product observed by two sources in one run yields exactly one snapshot;
* a source that explodes mid-run does not take the good sources (or the
  ``etl_run`` row) down with it;
* a severed database connection mid-source is survived: rollback, reconnect,
  and the run continues with earlier sources' data intact.
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


@register_source
class PytestResilienceCutterSource(ProductSource):
    code: ClassVar[str] = "pytest_resilience_cutter"
    name: ClassVar[str] = "pytest resilience cutter"
    base_url: ClassVar[str] = "https://example.com"
    terms_url: ClassVar[str | None] = "https://example.com/terms"
    description: ClassVar[str] = "severs the database connection during staging"

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        yield _raw(self.code, "CUTTER-1", name="pytest cutter widget")


def test_severed_connection_mid_run_recovers_and_continues(db, monkeypatch):
    """Transport death mid-source: rollback, reconnect, earlier data intact."""
    from app.etl.loader import WarehouseLoader

    real_stage = WarehouseLoader.stage
    armed = {"kill": True}

    def killer_stage(self, raw_records):
        if armed["kill"] and raw_records and raw_records[0].source_code == "pytest_resilience_cutter":
            armed["kill"] = False
            # Simulate the database dropping the TCP connection mid-flush.
            # The pooled connection is closed underneath the session; the next
            # statement must fail, and the pipeline must recover from there.
            self.session.connection().close()
        return real_stage(self, raw_records)

    monkeypatch.setattr(WarehouseLoader, "stage", killer_stage)

    result = Pipeline(
        PipelineConfig(
            sources=["pytest_resilience_alpha", "pytest_resilience_cutter"],
            limit_per_source=10,
            skip_dq=True,
            skip_catalog=True,
        )
    ).run()

    assert result.status == "partial", result.error
    assert "pytest_resilience_alpha" in result.sources_processed
    assert "pytest_resilience_cutter" in result.sources_failed
    # The good source committed before the connection died.
    assert len(_snapshots_for_run(db, result.run_id, SHARED_NAME)) == 1
    row = db.execute(
        sa.text("SELECT status FROM etl_run WHERE run_id = :rid"), {"rid": result.run_id}
    ).scalar()
    assert row == "partial"
