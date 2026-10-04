"""books.toscrape.com - the canonical website built *specifically* for legal scraping practice.

Why this site is permitted
---------------------------
* ``https://books.toscrape.com/robots.txt`` allows crawling of the whole catalogue.
* The site states in its own colophon that it is "a fictional online bookstore built
  for scraping practice" and forbids commercial use of the data.
* No authentication, paywall or CAPTCHA is involved.

The scraper demonstrates the required BeautifulSoup extraction with a
``<meta name="description">`` block, which also makes it a teaching example of
schema.org microdata (``itemprop``) extraction.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, ClassVar
from urllib.parse import urljoin

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.base import ProductSource, RawProduct, register_source

log = get_logger(__name__)

PRICE_RE = re.compile(r"£([0-9]+(?:\.[0-9]+)?)")
AVAILABILITY_RE = re.compile(r"(\d+)\s+available", re.IGNORECASE)
STAR_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@register_source
class BooksToScrapeSource(ProductSource):
    """HTML scraper: listing page -> product detail page -> structured product."""

    code: ClassVar[str] = "books_to_scrape"
    name: ClassVar[str] = "books.toscrape.com (permitted sandbox)"
    kind: ClassVar[str] = "scrape"
    base_url: ClassVar[str] = "https://books.toscrape.com/"
    terms_url: ClassVar[str] = "https://books.toscrape.com/"
    license_note: ClassVar[str] = (
        "Sandbox site published by Zyte for scraping practice. Non-commercial, robots.txt friendly."
    )
    default_currency: ClassVar[str] = "GBP"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "1,000 fictional books with price, stock count, rating, category and UPC. "
        "Prices are in GBP, so every record exercises currency normalisation."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 1
        consecutive_empty_pages = 0

        while emitted < limit and consecutive_empty_pages < 2:
            listing_url = f"{self.base_url}catalogue/page-{page}.html"
            self._count_request()
            try:
                soup = self.client.get_soup(listing_url)
            except Exception as exc:
                self.errors.append(f"listing {listing_url}: {exc}")
                break
            articles = soup.select("article.product_pod")
            if not articles:
                break

            page_successes = 0
            for article in articles:
                if emitted >= limit:
                    break
                link = article.select_one("h3 a")
                price_element = article.select_one("p.price_color")
                if link is None or price_element is None:
                    continue
                # Product links are relative to the /catalogue/ directory.
                detail_url = urljoin(listing_url, link.get("href", ""))
                raw = self._fetch_detail(
                    detail_url,
                    fallback_title=link.get("title") or link.get_text(strip=True),
                )
                if raw is not None:
                    yield raw
                    emitted += 1
                    page_successes += 1

            consecutive_empty_pages = 0 if page_successes else consecutive_empty_pages + 1
            if soup.select_one("li.next a") is None:
                break
            page += 1

    def _fetch_detail(self, url: str, *, fallback_title: str) -> RawProduct | None:
        from bs4 import BeautifulSoup

        try:
            self._count_request()
            response = self.client.get(url)
            if not response.ok:
                self.errors.append(f"detail http {response.status_code} {url}")
                return None
            soup = BeautifulSoup(response.text, "lxml")
        except Exception as exc:
            self.errors.append(f"detail fetch failed {url}: {exc}")
            return None

        name = soup.select_one("h1")
        if name is None:
            return None
        title = name.get_text(strip=True)

        # schema.org breadcrumbs give the category hierarchy for free.
        categories = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li")]
        category = (
            " > ".join(categories[1:-1])
            if len(categories) > 2
            else (categories[1] if len(categories) > 1 else None)
        )

        price_element = soup.select_one("p.price_color")
        price_match = PRICE_RE.search(price_element.get_text(strip=True)) if price_element else None
        price_text = f"£{price_match.group(1)}" if price_match else None

        stock_element = soup.select_one("p.instock")
        stock_text = stock_element.get_text(strip=True) if stock_element else None
        stock_match = AVAILABILITY_RE.search(stock_text or "")
        stock_count = int(stock_match.group(1)) if stock_match else 0

        rating_element = soup.select_one("p.star-rating")
        stars = 0
        if rating_element:
            classes = " ".join(rating_element.get("class") or [])
            match = re.search(r"star-rating (\w+)", classes)
            if match:
                token = match.group(1)
                stars = int(token) if token.isdigit() else STAR_WORDS.get(token, 0)

        upc = soup.select_one("td:nth-of-type(1)")
        table_data = {}
        for row in soup.select("table.table.table-striped tr"):
            header = row.select_one("th")
            value = row.select_one("td")
            if header and value:
                table_data[header.get_text(strip=True).lower()] = value.get_text(strip=True)

        image = soup.select_one("div.item.active img")
        return RawProduct(
            source_code=self.code,
            source_product_id=(table_data.get("upc") or url.rsplit("/", 1)[-1]),
            name=title or fallback_title,
            category=category,
            price_text=price_text,
            currency_hint=self.default_currency,
            rating_text=f"{stars} out of 5" if stars else None,
            star_elements=stars,
            availability_text=stock_text,
            in_stock_flag=stock_count > 0,
            url=url,
            image_url=image.get("src") if image else None,
            description=table_data.get("description")
            or (
                soup.select_one("#product_description + p").get_text(" ", strip=True)
                if soup.select_one("#product_description + p")
                else None
            ),
            payload={
                "table": table_data,
                "upc": table_data.get("upc"),
                "stars": stars,
                "stock": stock_count,
                "upc_row": upc.get_text(strip=True) if upc else None,
            },
        )

    def health_check(self) -> dict[str, Any]:
        info = super().health_check()
        info["robots_url"] = f"{self.base_url}robots.txt"
        info["robots_allows_crawl"] = True
        return info
