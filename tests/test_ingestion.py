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
    assert {
        "local_demo",
        "dummyjson_products",
        "fakestore_products",
        "openlibrary_books",
        "books_to_scrape",
        "scrapeme_products",
        "google_books",
    } <= codes


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
    assert any((record.rating_text or "").startswith("9.") for record in records), (
        "an out-of-range rating is expected"
    )


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
    assert record.canonical_name == ""  # invalid record keeps the raw (empty) name for audit
    assert record.source_product_id == "T-1"


# --------------------------------------------------------------------------------------
# ScrapeMe.live practice shop
# --------------------------------------------------------------------------------------
SCRAPEME_CARD = """
<li class="product type-product post-759 status-publish first instock product_cat-pokemon product_cat-seed purchasable product-type-simple">
  <a href="https://scrapeme.live/shop/Bulbasaur/" class="woocommerce-LoopProduct-link woocommerce-loop-product__link">
    <img src="https://scrapeme.live/wp-content/uploads/2018/08/001-350x350.png" />
    <h2 class="woocommerce-loop-product__title">Bulbasaur</h2>
    <span class="price"><span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">&pound;</span>63.00</bdi></span></span>
  </a>
</li>
"""

SCRAPEME_SALE_CARD = """
<li class="product type-product post-761 outofstock product_cat-pokemon purchasable product-type-simple">
  <a href="https://scrapeme.live/shop/Charmander/" class="woocommerce-LoopProduct-link woocommerce-loop-product__link">
    <h2 class="woocommerce-loop-product__title">Charmander</h2>
    <span class="price"><del><span class="woocommerce-Price-amount amount"><bdi>&pound;80.00</bdi></span></del> <ins><span class="woocommerce-Price-amount amount"><bdi>&pound;72.00</bdi></span></ins></span>
  </a>
</li>
"""

SCRAPEME_DETAIL = """
<html><body>
<h1 class="product_title">Bulbasaur</h1>
<div class="woocommerce-product-details__short-description"><p>A seed Pokemon.</p></div>
<div class="star-rating" role="img" aria-label="Rated 4.50 out of 5"></div>
<p class="stock in-stock">In stock</p>
</body></html>
"""


def _scrapeme_source():
    from app.ingestion.sources.scrapeme import ScrapeMeSource

    return ScrapeMeSource()


def _card(html: str):
    from bs4 import BeautifulSoup

    element = BeautifulSoup(html, "lxml").select_one("li.product")
    assert element is not None
    return element


def test_scrapeme_listing_card_parses_title_price_stock_and_category():
    raw = _scrapeme_source()._listing_raw(_card(SCRAPEME_CARD), "https://scrapeme.live/shop/")
    assert raw is not None
    assert raw.name == "Bulbasaur"
    assert raw.price_text == "£63.00"
    assert raw.list_price_text is None
    assert raw.currency_hint == "GBP"
    assert raw.source_product_id == "759"
    assert raw.category == "Pokemon"
    assert raw.in_stock_flag is True
    assert raw.url == "https://scrapeme.live/shop/Bulbasaur/"


def test_scrapeme_sale_card_splits_price_and_list_price():
    raw = _scrapeme_source()._listing_raw(_card(SCRAPEME_SALE_CARD), "https://scrapeme.live/shop/")
    assert raw is not None
    assert raw.price_text == "£72.00"
    assert raw.list_price_text == "£80.00"
    assert raw.in_stock_flag is False
    record = transform_product(raw)
    assert record.price == pytest.approx(72.0)
    assert record.discount_pct == pytest.approx(10.0)


def test_scrapeme_card_without_title_is_skipped():
    from bs4 import BeautifulSoup

    article = BeautifulSoup("<li class='product instock'></li>", "lxml").select_one("li")
    assert _scrapeme_source()._listing_raw(article, "https://scrapeme.live/shop/") is None


def test_scrapeme_enrich_adds_description_and_rating_without_network():
    class _FakeResponse:
        ok = True
        text = SCRAPEME_DETAIL

    class _FakeClient:
        def get(self, url: str):
            return _FakeResponse()

        def close(self) -> None:
            pass

    source = _scrapeme_source()
    raw = source._listing_raw(_card(SCRAPEME_CARD), "https://scrapeme.live/shop/")
    assert raw is not None
    source._client = _FakeClient()
    source._enrich_from_detail(raw)
    assert raw.description == "A seed Pokemon."
    assert raw.rating_text == "4.50 out of 5"


def test_scrapeme_enrich_keeps_listing_record_when_detail_fails():
    class _FailingClient:
        def get(self, url: str):
            raise ConnectionError("boom")

        def close(self) -> None:
            pass

    source = _scrapeme_source()
    raw = source._listing_raw(_card(SCRAPEME_CARD), "https://scrapeme.live/shop/")
    assert raw is not None
    source._client = _FailingClient()
    source._enrich_from_detail(raw)  # must not raise
    assert raw.name == "Bulbasaur"
    assert source.errors


# --------------------------------------------------------------------------------------
# Google Books API
# --------------------------------------------------------------------------------------
GOOGLE_BOOK_ITEM = {
    "id": "abc123",
    "volumeInfo": {
        "title": "The Hobbit",
        "authors": ["J.R.R. Tolkien"],
        "publisher": "HarperCollins",
        "categories": ["Fiction"],
        "averageRating": 4.5,
        "ratingsCount": 120,
        "description": "A fantasy novel.",
        "infoLink": "https://books.google.com/books?id=abc123",
        "imageLinks": {"thumbnail": "https://example.local/cover.jpg"},
    },
    "saleInfo": {
        "saleability": "FOR_SALE",
        "listPrice": {"amount": 12.99, "currencyCode": "USD"},
    },
}


def _google_source():
    from app.ingestion.sources.google_books import GoogleBooksSource

    return GoogleBooksSource()


def test_google_books_maps_price_rating_and_saleability():
    raw = _google_source()._to_raw(GOOGLE_BOOK_ITEM, "fiction")
    assert raw is not None
    assert raw.name == "The Hobbit - J.R.R. Tolkien"
    assert raw.price_text == "12.99"
    assert raw.currency_hint == "USD"
    assert raw.rating_text == "4.5 out of 5"
    assert raw.rating_count_text == "120"
    assert raw.in_stock_flag is True
    assert raw.source_product_id == "abc123"


def test_google_books_not_for_sale_has_no_availability_claim():
    item = {
        "id": "xyz",
        "volumeInfo": {"title": "Old Tome", "categories": ["History"]},
        "saleInfo": {"saleability": "NOT_FOR_SALE"},
    }
    raw = _google_source()._to_raw(item, "history")
    assert raw is not None
    assert raw.price_text is None
    assert raw.availability_text is None
    assert raw.in_stock_flag is None


def test_google_books_malformed_items_are_skipped():
    source = _google_source()
    assert source._to_raw({}, "fiction") is None  # no volumeInfo/title
    assert source._to_raw({"volumeInfo": {}}, "fiction") is None  # empty title
    assert source._to_raw("not-a-dict", "fiction") is None
    assert source._to_raw(None, "fiction") is None  # type: ignore[arg-type]


def test_google_books_params_include_key_only_when_configured(monkeypatch):
    from app.core.config import settings

    source = _google_source()
    monkeypatch.setattr(settings, "google_books_api_key", "")
    assert "key" not in source._params("fiction", 10)
    monkeypatch.setattr(settings, "google_books_api_key", "TESTKEY")
    assert source._params("fiction", 10)["key"] == "TESTKEY"
