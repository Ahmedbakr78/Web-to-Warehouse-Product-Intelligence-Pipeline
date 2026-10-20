"""Scrapy crawling engine for the books.toscrape.com sandbox.

This is the second HTML engine beside the default BeautifulSoup source: the
same sandbox, crawled with Scrapy's scheduler, robots middleware, autothrottle
and item-count cap instead of hand-rolled paging. Output is identical in shape
(:class:`RawProduct`), so cleaning, dedupe, DQ and the warehouse never know
which engine produced a row.

Requires the optional dependency (``pip install -e ".[scrapy]"``). The module
is import-safe without it: :func:`scrapy_available` reports ``False`` and
:func:`crawl_books` raises a helpful error.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import PipelineError
from app.ingestion.base import RawProduct

BASE_URL = "https://books.toscrape.com/"
START_URL = "https://books.toscrape.com/catalogue/page-1.html"
USER_AGENT = "ProductIntelligenceBot/1.9 (+https://github.com/Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline)"


def scrapy_available() -> bool:
    """True when the optional Scrapy dependency is installed."""
    try:
        import scrapy  # noqa: F401
    except ImportError:
        return False
    return True


def _spider_class() -> Any:
    """Define the spider lazily so importing this module never needs Scrapy."""
    import scrapy

    class BookSpider(scrapy.Spider):
        """Listing then detail crawl of the scrape sandbox (robots-obeying)."""

        name = "books_toscrape"
        allowed_domains = ["books.toscrape.com"]
        start_urls = [START_URL]
        custom_settings = {
            "ROBOTSTXT_OBEY": True,
            "DOWNLOAD_DELAY": 1.0,
            "AUTOTHROTTLE_ENABLED": True,
            "AUTOTHROTTLE_START_DELAY": 1.0,
            "AUTOTHROTTLE_MAX_DELAY": 10.0,
            "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
            "USER_AGENT": USER_AGENT,
        }

        def __init__(self, limit: int = 20, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.limit = max(int(limit or 20), 1)
            self.seen = 0

        def parse(self, response: Any, **kwargs: Any) -> Any:
            for card in response.css("article.product_pod"):
                if self.seen >= self.limit:
                    return
                link = card.css("h3 a::attr(href)").get()
                if not link:
                    continue
                self.seen += 1
                yield response.follow(
                    link,
                    callback=self.parse_detail,
                    meta={
                        "name": card.css("h3 a::attr(title)").get(),
                        "price_text": card.css("p.price_color::text").get(),
                        "availability_text": " ".join(card.css("p.instock ::text").getall()).strip(),
                        "rating_class": card.css("p.star-rating::attr(class)").get(),
                        "image_url": response.urljoin(
                            card.css("div.image_container img::attr(src)").get() or ""
                        ),
                    },
                )
            if self.seen < self.limit:
                nxt = response.css("li.next a::attr(href)").get()
                if nxt:
                    yield response.follow(nxt, callback=self.parse)

        def parse_detail(self, response: Any) -> Any:
            meta = response.meta
            crumbs = response.css("ul.breadcrumb li a::text").getall()
            table: dict[str, str] = {}
            for row in response.css("table.table-striped tr"):
                key = row.css("th::text").get()
                val = row.css("td::text").get()
                if key and val:
                    table[key.strip()] = val.strip()
            desc = response.css("#product_description ~ p::text").get()
            yield {
                "source_product_id": table.get("UPC") or response.url.rsplit("/", 1)[-1],
                "name": meta.get("name"),
                "category": crumbs[-1].strip() if crumbs else None,
                "price_text": meta.get("price_text")
                or table.get("Price (incl. tax)")
                or table.get("Price (excl. tax)"),
                "availability_text": table.get("Availability") or meta.get("availability_text"),
                "rating_class": meta.get("rating_class"),
                "url": response.url,
                "image_url": meta.get("image_url"),
                "description": (desc or "")[:600] or None,
            }

    return BookSpider


def crawl_books(limit: int = 20) -> list[RawProduct]:
    """Crawl the sandbox with Scrapy and return raw products.

    Polite by construction: robots middleware, 1s delay, autothrottle and a
    hard item cap. Raises :class:`PipelineError` when Scrapy is not installed.
    """
    if not scrapy_available():
        raise PipelineError(
            "scrapy_engine_missing",
            details={"hint": 'install the engine with: pip install -e ".[scrapy]"'},
        )
    from scrapy.crawler import CrawlerProcess
    from scrapy.signals import item_scraped
    from scrapy.utils.project import get_project_settings

    collected: list[dict[str, Any]] = []

    def _on_item(item: Any, response: Any, spider: Any) -> None:
        collected.append(dict(item))

    settings = get_project_settings()
    settings.set("CLOSESPIDER_ITEMCOUNT", max(int(limit or 20), 1))
    settings.set("LOG_ENABLED", False)
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(_spider_class())
    crawler.signals.connect(_on_item, signal=item_scraped)
    process.crawl(crawler, limit=limit)
    process.start()  # blocks until the crawl finishes or the cap hits

    raws: list[RawProduct] = []
    for entry in collected[:limit]:
        rating_class = str(entry.get("rating_class") or "")
        stars: int | None = None
        for word, value in (
            ("One", 1),
            ("Two", 2),
            ("Three", 3),
            ("Four", 4),
            ("Five", 5),
        ):
            if word in rating_class:
                stars = value
                break
        raws.append(
            RawProduct(
                source_code="books_to_scrape",
                source_product_id=str(entry.get("source_product_id") or entry.get("url") or ""),
                name=str(entry.get("name") or ""),
                category=entry.get("category"),
                price_text=entry.get("price_text"),
                currency_hint="GBP",
                rating_text=f"{stars} out of 5" if stars else None,
                star_elements=stars,
                availability_text=entry.get("availability_text"),
                url=entry.get("url"),
                image_url=entry.get("image_url"),
                description=entry.get("description"),
                payload={"engine": "scrapy"},
            )
        )
    return raws


__all__ = ["BASE_URL", "USER_AGENT", "book_spider_class", "crawl_books", "scrapy_available"]


def book_spider_class() -> Any:
    """Public accessor for the spider class (useful for tests and the shell)."""
    return _spider_class()
