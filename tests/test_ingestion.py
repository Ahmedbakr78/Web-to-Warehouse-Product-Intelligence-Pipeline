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
        "steam_store",
        "openfoodfacts_prices",
        "platzi_products",
        "kraken_tickers",
        "makeup_products",
        "ygoprodeck_cards",
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


# --------------------------------------------------------------------------------------
# Steam Store API
# --------------------------------------------------------------------------------------
STEAM_DETAIL = {
    "steam_appid": 550,
    "name": "Left 4 Dead 2",
    "type": "game",
    "is_free": False,
    "header_image": "https://cdn.example.local/header.jpg",
    "short_description": "Co-operative zombie shooter.",
    "developers": ["Valve"],
    "publishers": ["Valve"],
    "price_overview": {
        "currency": "USD",
        "initial": 999,
        "final": 199,
        "discount_percent": 80,
    },
    "genres": [{"id": "1", "description": "Action"}],
    "release_date": {"coming_soon": False, "date": "Nov 16, 2009"},
}

STEAM_SUMMARY = {
    "review_score_desc": "Overwhelmingly Positive",
    "total_positive": 1036290,
    "total_negative": 26359,
    "total_reviews": 1062649,
}


def _steam_source():
    from app.ingestion.sources.steam_store import SteamStoreSource

    return SteamStoreSource()


def test_steam_maps_cents_price_discount_and_rating():
    raw = _steam_source()._to_raw(STEAM_DETAIL, STEAM_SUMMARY, 550)
    assert raw is not None
    assert raw.source_product_id == "550"
    assert raw.name == "Left 4 Dead 2"
    assert raw.price_text == "1.99"  # final cents -> dollars
    assert raw.list_price_text == "9.99"  # initial cents -> dollars
    assert raw.currency_hint == "USD"
    assert raw.category == "Action"
    assert raw.in_stock_flag is True
    assert raw.brand == "Valve"
    assert raw.url == "https://store.steampowered.com/app/550/"
    assert raw.payload["discount_percent"] == 80
    # 1036290 / 1062649 * 5 = 4.876...
    assert raw.rating_text == "4.88 out of 5"
    assert raw.rating_count_text == "1062649"


def test_steam_free_title_maps_zero_price_without_rating():
    detail = {**STEAM_DETAIL, "steam_appid": 440, "name": "Team Fortress 2", "is_free": True}
    detail.pop("price_overview", None)
    raw = _steam_source()._to_raw(detail, None, 440)
    assert raw is not None
    assert raw.price_text == "0"
    assert raw.list_price_text is None
    assert raw.rating_text is None
    assert raw.in_stock_flag is True


def test_steam_coming_soon_maps_preorder():
    detail = {**STEAM_DETAIL, "release_date": {"coming_soon": True, "date": "2027"}}
    detail.pop("price_overview", None)
    detail["is_free"] = False
    raw = _steam_source()._to_raw(detail, STEAM_SUMMARY, 550)
    assert raw is not None
    assert raw.availability_text == "preorder"
    assert raw.in_stock_flag is False


def test_steam_malformed_payloads_are_skipped():
    source = _steam_source()
    assert source._to_raw({}, STEAM_SUMMARY, 1) is None  # no name
    assert source._to_raw({"name": ""}, STEAM_SUMMARY, 1) is None  # empty name
    assert source._to_raw("not-a-dict", STEAM_SUMMARY, 1) is None  # type: ignore[arg-type]
    assert source._to_raw(None, STEAM_SUMMARY, 1) is None  # type: ignore[arg-type]
    assert source._cents("bogus") is None
    assert source._cents(999) == "9.99"


# --------------------------------------------------------------------------------------
# Open Food Facts Prices
# --------------------------------------------------------------------------------------
OFF_PRICE_ITEM = {
    "id": 342476,
    "product_id": 3883915,
    "price": 2.39,
    "price_is_discounted": False,
    "price_without_discount": None,
    "currency": "AUD",
    "date": "2026-10-08",
    "product": {
        "code": "4061459104981",
        "product_name": "CREAM CHEESE SPREADABLE",
        "brands": "WESTACRE DAIRY",
        "categories_tags": ["en:salty-spreads"],
        "image_url": "https://images.openfoodfacts.org/front.jpg",
        "quantity": "250g",
        "nutriscore_grade": "unknown",
    },
    "location": {
        "osm_name": "Woodgrove Shopping Centre",
        "osm_address_city": "Melbourne",
        "osm_address_country": "Australia",
    },
}


def _off_source():
    from app.ingestion.sources.openfoodfacts_prices import OpenFoodFactsPricesSource

    return OpenFoodFactsPricesSource()


def test_off_prices_maps_product_price_store_and_category():
    raw = _off_source()._to_raw(OFF_PRICE_ITEM)
    assert raw is not None
    assert raw.source_product_id == "4061459104981"
    assert raw.name == "CREAM CHEESE SPREADABLE"
    assert raw.price_text == "2.39"
    assert raw.currency_hint == "AUD"
    assert raw.category == "Salty Spreads"
    assert raw.brand == "WESTACRE DAIRY"
    assert raw.in_stock_flag is True
    assert raw.list_price_text is None
    assert raw.url == "https://world.openfoodfacts.org/product/4061459104981"
    assert "Melbourne" in (raw.description or "")
    assert raw.payload["country"] == "Australia"


def test_off_prices_discount_yields_list_price():
    item = {**OFF_PRICE_ITEM, "price": 4.5, "price_is_discounted": True, "price_without_discount": 6.0}
    raw = _off_source()._to_raw(item)
    assert raw is not None
    assert raw.price_text == "4.5"
    assert raw.list_price_text == "6.0"


def test_off_prices_missing_name_or_price_are_skipped():
    source = _off_source()
    item = {**OFF_PRICE_ITEM, "product": {**OFF_PRICE_ITEM["product"], "product_name": ""}}
    assert source._to_raw(item) is None
    item = {**OFF_PRICE_ITEM, "price": None}
    assert source._to_raw(item) is None
    assert source._to_raw({}) is None
    assert source._to_raw(None) is None  # type: ignore[arg-type]


def test_off_prices_tags_are_humanised():
    from app.ingestion.sources.openfoodfacts_prices import OpenFoodFactsPricesSource

    assert OpenFoodFactsPricesSource._clean_tag("en:salty-spreads") == "Salty Spreads"
    assert OpenFoodFactsPricesSource._clean_tag("whole-milk") == "Whole Milk"


# --------------------------------------------------------------------------------------
# New sources: platzi, kraken, makeup, ygoprodeck
# --------------------------------------------------------------------------------------
PLATZI_ITEM = {
    "id": 8,
    "title": "Classic Red Jogger Sweatpants",
    "price": 98,
    "description": "Soft joggers.",
    "category": {"id": 1, "name": "Clothes", "image": "https://example.com/c.png"},
    "images": ["https://example.com/p.png"],
    "slug": "classic-red-jogger-sweatpants",
}

KRAKEN_PAIRS = {
    "error": [],
    "result": {
        "XXBTZUSD": {"quote": "ZUSD", "status": "online"},
        "XETHZUSD": {"quote": "ZUSD", "status": "online"},
        "XXBTZEUR": {"quote": "ZEUR", "status": "online"},
        "OFFLINE": {"quote": "ZUSD", "status": "offline"},
    },
}

KRAKEN_TICKERS = {
    "error": [],
    "result": {
        "XXBTZUSD": {"c": ["82846.0", "1.2"], "h": ["84340.0", "84340.0"], "l": ["82823.0", "82823.0"], "o": "84100.0"},
        "XETHZUSD": {"c": ["3100.5", "3.0"], "h": ["3200.0", "3200.0"], "l": ["3050.0", "3050.0"], "o": "3150.0"},
    },
}

MAKEUP_ITEM = {
    "id": 97,
    "brand": "maybelline",
    "name": "Maybelline Vivid Matte Liquid Lip Colour",
    "price": "12.99",
    "price_sign": "$",
    "currency": None,
    "image_link": "https://example.com/lip.png",
    "product_link": "https://example.com/lip",
    "description": "Bold vivid colour.",
    "rating": 4.2,
    "product_type": "lipstick",
    "tag_list": ["matte"],
}

YGO_ITEM = {
    "id": 46986414,
    "name": "Dark Magician",
    "type": "Normal Monster",
    "race": "Spellcaster",
    "attribute": "DARK",
    "archetype": "Dark Magician",
    "desc": "The ultimate wizard.",
    "ygoprodeck_url": "https://ygoprodeck.com/card/dark-magician-4003",
    "card_images": [{"image_url": "https://example.com/dm.png"}],
    "card_sets": [{"set_name": "2016 Mega-Tins", "set_price": "6.97"}],
    "card_prices": [{"tcgplayer_price": "7.50", "cardmarket_price": "5.10"}],
}


def test_platzi_maps_paged_product():
    from app.ingestion.sources.platzi import PlatziProductsSource

    raw = PlatziProductsSource()._to_raw(PLATZI_ITEM)
    assert raw is not None
    assert raw.source_code == "platzi_products"
    assert raw.source_product_id == "8"
    assert raw.name == "Classic Red Jogger Sweatpants"
    assert raw.category == "Clothes"
    assert raw.price_text == "98"
    assert raw.currency_hint == "USD"
    assert raw.image_url == "https://example.com/p.png"
    assert raw.in_stock_flag is True
    assert PlatziProductsSource()._to_raw({}) is None
    assert PlatziProductsSource()._to_raw(None) is None  # type: ignore[arg-type]


def test_platzi_fetch_pages_until_short_page():
    from app.ingestion.sources.platzi import PlatziProductsSource

    def _page(ids):
        return [{**PLATZI_ITEM, "id": i} for i in ids]

    pages = [_page(range(50)), _page((50, 51, 52))]

    class _StubClient:
        def get_json(self, url, params=None):
            return pages.pop(0)

    raws = list(PlatziProductsSource(client=_StubClient()).fetch(limit=60))
    assert [r.source_product_id for r in raws] == [str(i) for i in list(range(50)) + [50, 51, 52]]


def test_kraken_keeps_online_usd_pairs_and_batches_tickers():
    from app.ingestion.sources.kraken import KrakenTickersSource

    calls = []

    class _StubClient:
        def get_json(self, url, params=None):
            calls.append(url)
            if "AssetPairs" in url:
                return KRAKEN_PAIRS
            assert params["pair"] == "XETHZUSD,XXBTZUSD"
            return KRAKEN_TICKERS

    raws = list(KrakenTickersSource(client=_StubClient()).fetch(limit=10))
    assert [r.source_product_id for r in raws] == ["XETHZUSD", "XXBTZUSD"]
    assert len(calls) == 2  # one pair listing + one ticker batch


def test_kraken_maps_ticker_price_and_ranges():
    from app.ingestion.sources.kraken import KrakenTickersSource

    raw = KrakenTickersSource()._to_raw("XXBTZUSD", KRAKEN_TICKERS["result"]["XXBTZUSD"])
    assert raw is not None
    assert raw.source_code == "kraken_tickers"
    assert raw.category == "Cryptocurrency"
    assert raw.price_text == "82846.0"
    assert raw.currency_hint == "USD"
    assert raw.payload["high_24h"] == "84340.0"
    assert raw.payload["open_24h"] == "84100.0"
    assert KrakenTickersSource()._to_raw("X", None) is None
    assert KrakenTickersSource()._to_raw("X", {"c": []}) is None


def test_kraken_api_errors_are_recorded_not_raised():
    from app.ingestion.sources.kraken import KrakenTickersSource

    class _StubClient:
        def get_json(self, url, params=None):
            return {"error": ["EQuery:Unknown asset pair"], "result": {}}

    source = KrakenTickersSource(client=_StubClient())
    assert list(source.fetch(limit=5)) == []
    assert source.errors


def test_makeup_maps_price_brand_and_rating():
    from app.ingestion.sources.makeup import MakeupProductsSource

    raw = MakeupProductsSource()._to_raw(MAKEUP_ITEM)
    assert raw is not None
    assert raw.source_code == "makeup_products"
    assert raw.price_text == "12.99"
    assert raw.currency_hint == "USD"
    assert raw.brand == "Maybelline"
    assert raw.category == "Lipstick"
    assert raw.rating_text == "4.2 out of 5"
    assert MakeupProductsSource._price("0.0") is None
    assert MakeupProductsSource._price(None) is None
    assert MakeupProductsSource._rating(0) is None
    assert MakeupProductsSource()._to_raw({}) is None


def test_ygoprodeck_prefers_tcgplayer_market_price():
    from app.ingestion.sources.ygoprodeck import YGOProDeckCardsSource

    raw = YGOProDeckCardsSource()._to_raw(YGO_ITEM)
    assert raw is not None
    assert raw.source_code == "ygoprodeck_cards"
    assert raw.source_product_id == "46986414"
    assert raw.category == "Spellcaster"
    assert raw.brand == "Dark Magician"
    assert raw.price_text == "7.50"
    assert raw.url == "https://ygoprodeck.com/card/dark-magician-4003"
    assert raw.image_url == "https://example.com/dm.png"


def test_ygoprodeck_falls_back_to_set_price_and_skips_bad_rows():
    from app.ingestion.sources.ygoprodeck import YGOProDeckCardsSource

    source = YGOProDeckCardsSource()
    item = {**YGO_ITEM, "card_prices": [{"tcgplayer_price": "0.00"}]}
    assert source._to_raw(item).price_text == "6.97"  # set-price fallback
    item = {**YGO_ITEM, "card_prices": [], "card_sets": []}
    assert source._to_raw(item).price_text is None
    assert source._to_raw({}) is None
    assert source._to_raw(None) is None  # type: ignore[arg-type]
