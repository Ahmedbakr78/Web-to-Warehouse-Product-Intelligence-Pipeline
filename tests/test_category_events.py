"""Category-change events: per-source, never a cross-source disagreement."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.etl.loader import WarehouseLoader
from app.ingestion.base import NormalizedProduct
from app.ingestion.dedupe import MatchResult
from app.models import DimCategory, DimProduct, EtlRun

pytestmark = pytest.mark.integration

FINGERPRINT = "fp-pride-and-prejudice-regression"


def _record(source: str, category: str) -> NormalizedProduct:
    return NormalizedProduct(
        source_code=source,
        source_product_id=f"{source}-1342",
        canonical_name="Pride and Prejudice - Austen Jane",
        normalized_name="pride and prejudice austen jane",
        fingerprint=FINGERPRINT,
        blocking_key="prid",
        category=category,
        category_slug=category.lower(),
        raw_category=category,
    )


def _upsert(session, run_id: str, record: NormalizedProduct, product_id: int | None) -> DimProduct:
    match = MatchResult(
        product_id=product_id,
        strategy="exact" if product_id else "new",
        score=1.0 if product_id else 0.0,
        fingerprint=record.fingerprint,
        blocking_key=record.blocking_key,
    )
    product, _ = WarehouseLoader(session, run_id).upsert_product(record, match)
    return product


def _category_events(session, product_id: int) -> int:
    return session.execute(
        sa.text(
            "SELECT COUNT(*) FROM chg_product_event "
            "WHERE product_id = :pid AND event_type = 'category_changed'"
        ),
        {"pid": product_id},
    ).scalar()


def _run(session, records: list[NormalizedProduct], product_id: int | None) -> int:
    run_id = uuid.uuid4().hex
    session.add(EtlRun(run_id=run_id, status="running", trigger="test"))
    session.flush()
    for record in records:
        product_id = _upsert(session, run_id, record, product_id).product_id
    session.flush()
    return product_id


def test_two_sources_disagreeing_on_a_shelf_is_not_a_category_change(session):
    """Open Library and Gutendex file the same merged book differently, every run."""
    records = [_record("openlibrary_books", "History"), _record("gutendex_books", "Courtship")]
    product_id = _run(session, records, None)
    first_category = session.get(DimProduct, product_id).category_id
    product_id = _run(session, records, product_id)
    product_id = _run(session, records, product_id)

    assert _category_events(session, product_id) == 0
    # The first source to categorise the product keeps owning its category.
    assert session.get(DimProduct, product_id).category_id == first_category


def test_a_source_recategorising_its_own_product_is_one_event(session):
    product_id = _run(session, [_record("openlibrary_books", "History")], None)
    product_id = _run(session, [_record("openlibrary_books", "Romance")], product_id)
    product_id = _run(session, [_record("openlibrary_books", "Romance")], product_id)

    assert _category_events(session, product_id) == 1
    category_id = session.get(DimProduct, product_id).category_id
    assert session.get(DimCategory, category_id).slug == "romance"
