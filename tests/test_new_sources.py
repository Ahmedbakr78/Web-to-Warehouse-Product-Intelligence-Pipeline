"""New real sources (TVMaze, Archive.org, DummyJSON recipes), the Scrapy engine
and conditional-GET plumbing: registration, offline mapping and prod guards."""

from __future__ import annotations

import pytest

from app.etl.pipeline import Pipeline, PipelineConfig
from app.ingestion.base import (
    DATA_TRUST_REAL,
    RawProduct,
    get_source,
    list_sources,
    transform_product,
)


def test_new_sources_are_registered_with_compliance_metadata():
    codes = {source["code"] for source in list_sources()}
    assert {"tvmaze_shows", "archive_texts", "dummyjson_recipes"} <= codes
    for code in ("tvmaze_shows", "archive_texts", "dummyjson_recipes"):
        source = get_source(code)
        assert source.kind == "api"
        assert source.terms_url and source.rate_limit_per_minute > 0
        source.close()


def test_prod_auto_select_is_real_only(database):
    """A bare pipeline run only ever collects genuine market data.

    Every registered source is classified by ``data_trust``. A source that
    publishes a demo catalogue, a mock API or locally generated rows is never
    picked up automatically - a run without parameters must not mix fabricated
    rows into production data. Such sources stay reachable by explicit code
    selection.

    Takes the session ``database`` fixture so the schema exists before the
    auto-select opens its session: otherwise this module (alphabetically
    first) would cache a pre-bootstrap engine and poison later tests.
    """
    codes = set(Pipeline(PipelineConfig(database=database))._source_codes())
    assert "local_demo" not in codes

    untrusted = {
        source["code"]
        for source in list_sources()
        if source.get("enabled")
        and source.get("terms_allowed", True)
        and source.get("data_trust") != DATA_TRUST_REAL
    }
    assert untrusted, "expected at least one non-real source to guard against"
    assert not (codes & untrusted), f"auto-select leaked untrusted sources: {codes & untrusted}"

    trusted = {
        source["code"]
        for source in list_sources()
        if source.get("enabled")
        and source.get("terms_allowed", True)
        and source.get("data_trust") == DATA_TRUST_REAL
    }
    assert trusted <= codes, f"auto-select dropped real sources: {trusted - codes}"
    assert {"openlibrary_books", "tvmaze_shows", "archive_texts"} <= codes


def test_tvmaze_mapping_is_valid():
    raw = get_source("tvmaze_shows")._to_raw(
        {
            "id": 526,
            "name": "The Office",
            "genres": ["Comedy"],
            "network": {"name": "NBC"},
            "rating": {"average": 8.8},
            "image": {"medium": "https://example.com/poster.jpg"},
            "url": "https://www.tvmaze.com/shows/526/the-office",
            "summary": "<p>A mockumentary.</p>",
            "status": "Ended",
            "premiered": "2005-03-24",
            "runtime": 30,
        }
    )
    assert raw is not None and raw.source_product_id == "526"
    record = transform_product(raw)
    assert record.is_valid
    assert record.category == "Comedy"
    assert record.rating is not None and 0 <= record.rating <= 5
    assert "missing_price" in record.quality_flags  # honest: catalogue has no price


def test_archive_mapping_is_valid():
    raw = get_source("archive_texts")._to_raw(
        {
            "identifier": "moby_dick",
            "title": "Moby Dick",
            "creator": ["Herman Melville"],
            "downloads": 12345,
            "date": "2001-01-01",
        }
    )
    assert raw is not None
    assert raw.url == "https://archive.org/details/moby_dick"
    record = transform_product(raw)
    assert record.is_valid and record.category == "Books"


def test_dummyjson_recipes_mapping_is_valid():
    raw = get_source("dummyjson_recipes")._to_raw(
        {
            "id": 1,
            "name": "Classic Margherita Pizza",
            "image": "https://example.com/pizza.jpg",
            "rating": 4.6,
            "reviewCount": 98,
            "mealType": ["Dinner"],
            "tags": ["Italian"],
            "ingredients": ["dough", "tomato", "mozzarella"],
        }
    )
    assert raw is not None
    record = transform_product(raw)
    assert record.is_valid and record.rating == 4.6


def test_scrapy_engine_is_installed_and_parses_offline():
    pytest.importorskip("scrapy")
    from scrapy.http import Request, TextResponse

    from app.ingestion.scrapy_spider import book_spider_class, scrapy_available

    assert scrapy_available() is True
    spider = book_spider_class()(limit=5)
    html = b"""
    <html><body>
    <article class="product_pod">
      <div class="image_container"><img src="media/cache/1.jpg"/></div>
      <p class="star-rating Three"></p>
      <h3><a href="catalogue/a-book_1/index.html" title="A Book">A Book</a></h3>
      <p class="price_color">\xc2\xa351.77</p>
      <p class="instock availability">In stock</p>
    </article>
    </body></html>
    """
    response = TextResponse("https://books.toscrape.com/", body=html, encoding="utf-8")
    requests = [r for r in spider.parse(response) if isinstance(r, Request)]
    assert len(requests) == 1 and requests[0].meta["name"] == "A Book"

    detail_html = b"""
    <html><body>
    <ul class="breadcrumb"><li><a>Home</a></li><li><a>Books</a></li><li><a>Poetry</a></li></ul>
    <table class="table-striped">
      <tr><th>UPC</th><td>ABC123</td></tr>
      <tr><th>Price (incl. tax)</th><td>\xc2\xa351.77</td></tr>
      <tr><th>Availability</th><td>In stock (22 available)</td></tr>
    </table>
    </body></html>
    """
    detail = TextResponse(
        "https://books.toscrape.com/catalogue/a-book_1/index.html",
        body=detail_html,
        encoding="utf-8",
        request=Request(
            "https://books.toscrape.com/catalogue/a-book_1/index.html",
            meta={
                "name": "A Book",
                "price_text": "\u00a351.77",
                "availability_text": "In stock",
                "rating_class": "star-rating Three",
                "image_url": "https://books.toscrape.com/media/cache/1.jpg",
            },
        ),
    )
    items = list(spider.parse_detail(detail))
    assert len(items) == 1
    assert items[0]["source_product_id"] == "ABC123"
    assert items[0]["category"] == "Poetry"
    record = transform_product(
        RawProduct(
            source_code="books_to_scrape",
            source_product_id=items[0]["source_product_id"],
            name=items[0]["name"],
            category=items[0]["category"],
            price_text=items[0]["price_text"],
            currency_hint="GBP",
            rating_text="3 out of 5",
            star_elements=3,
            availability_text=items[0]["availability_text"],
            url=items[0]["url"],
        )
    )
    assert record.is_valid and record.price == 51.77 and record.rating == 3.0
