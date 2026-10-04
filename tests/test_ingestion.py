"""Tests for the ingestion contracts: sources, transformation and staging."""

from __future__ import annotations

import pytest

from app.core.errors import SourceNotFoundError
from app.ingestion.base import (
    RawProduct,
    get_source,
    get_source_class,
    list_sources,
    load_builtin_sources,
    transform_product,
)
from app.ingestion.sources.local_fixture import LocalFixtureSource


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------
def test_registry_contains_every_bundled_source():
    load_builtin_sources()
    codes = {source["code"] for source in list_sources()}
    assert {"local_demo", "dummyjson_products", "fakestore_products", "openlibrary_books", "books_to_scrape"} <= codes


def test_every_source_declares_compliance_metadata():
    for source in list_sources():
        assert source["name"], source["code"]
        assert source["kind"] in {"api", "scrape", "synthetic"}
        assert source["base_url"]
        assert source["rate_limit_per_minute"] > 0
        assert source["min_delay_seconds"] >= 0
        assert source["description"]


def test_scrape_sources_declare_terms_and_robots_friendly():
    for source in list_sources():
        if source["kind"] == "scrape":
            assert source["terms_url"], f"{source['code']} must document why crawling is permitted"
            assert source["robots_respected"] is True


def test_unknown_source_raises_with_helpful_details():
    with pytest.raises(SourceNotFoundError) as error:
        get_source_class("does-not-exist")
    assert "available" in error.value.details


def test_source_is_a_singleton_class_not_instance():
    assert get_source_class("local_demo") is LocalFixtureSource
    assert isinstance(get_source("local_demo"), LocalFixtureSource)


# --------------------------------------------------------------------------------------
# Local fixture source
# --------------------------------------------------------------------------------------
def test_local_source_is_deterministic():
    first = [raw.name for raw in LocalFixtureSource(seed=7).fetch(limit=10)]
    second = [raw.name for raw in LocalFixtureSource(seed=7).fetch(limit=10)]
    assert first == second


def test_local_source_respects_the_limit():
    assert len(list(LocalFixtureSource().fetch(limit=5))) == 5


def test_local_source_injects_quality_defects():
    records = list(LocalFixtureSource().fetch(limit=200))
    assert any(record.name == "" for record in records), "a missing name defect is expected"
    assert any(record.price_text is None for record in records), "a missing price defect is expected"
    assert any((record.rating_text or "").startswith("9.") for record in records), "an out-of-range rating is expected"


def test_local_source_generates_mixed_currencies():
    currencies = {record.currency_hint for record in LocalFixtureSource().fetch(limit=80)}
    assert len(currencies) > 1


# --------------------------------------------------------------------------------------
# Transform
# --------------------------------------------------------------------------------------
def _raw(**overrides):
    payload = {
        "source_code": "test",
        "source_product_id": "T-1",
        "name": "SALE: Sony WH-1000XM5 Headphones (2024)",
        "category": "Electronics / Audio",
        "price_text": "\u00a3459.99",
        "currency_hint": "GBP",
        "rating_text": "4.6 out of 5",
        "availability_text": "In stock",
        "url": "https://example.com/p/1",
    }
    payload.update(overrides)
    return RawProduct(**payload)


def test_transform_produces_a_clean_valid_record():
    record = transform_product(_raw())
    assert record.is_valid is True
    assert record.canonical_name == "Sony WH-1000XM5 Headphones"
    assert record.category == "Electronics > Audio"
    assert record.currency == "GBP"
    assert record.price == pytest.approx(459.99)
    assert record.price_usd > record.price, "GBP must be converted to USD"
    assert record.fx_rate_to_usd > 1
    assert record.rating == pytest.approx(4.6)
    assert record.availability == "in_stock" and record.in_stock is True
    assert record.fingerprint and record.blocking_key


def test_transform_flags_missing_price_but_keeps_the_record():
    record = transform_product(_raw(price_text=None))
    assert record.is_valid is True
    assert "missing_price" in record.quality_flags


def test_transform_rejects_a_missing_name():
    record = transform_product(_raw(name=""))
    assert record.is_valid is False
    assert record.reject_reason == "missing_or_invalid_name"


def test_transform_strict_mode_rejects_missing_price():
    record = transform_product(_raw(price_text=None), strict=True)
    assert record.is_valid is False
    assert record.reject_reason == "missing_price"


def test_transform_flags_an_invalid_url():
    record = transform_product(_raw(url="not-a-url"))
    assert "invalid_url" in record.quality_flags


def test_transform_computes_discount_from_list_price():
    record = transform_product(_raw(price_text="\u00a3300.00", list_price_text="\u00a3500.00"))
    assert record.list_price == pytest.approx(500.0)
    assert record.discount_pct == pytest.approx(40.0)


def test_transform_content_hash_changes_with_content():
    left = transform_product(_raw()).payload_hash
    right = transform_product(_raw(price_text="\u00a3360.00")).payload_hash
    assert left != right


def test_transform_falls_back_to_source_id_when_name_is_blank():
    record = transform_product(_raw(name=""))
    assert record.canonical_name == ""   # invalid record keeps the raw (empty) name for audit
    assert record.source_product_id == "T-1"
