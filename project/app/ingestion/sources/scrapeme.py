"""scrapeme.live - a WooCommerce shop built *specifically* for scraping practice.

Why this site is permitted
---------------------------
* ``https://scrapeme.live/robots.txt`` allows the shop catalogue (it only
  disallows ``/wp-admin/``, ``add-to-cart`` URLs and upload internals).
* The site presents itself as a scraping sandbox (Pokemon products with
  stable markup, no authentication, paywall, CAPTCHA or blocking).
* Prices are in GBP, which exercises the same FX normalisation path as
  :mod:`app.ingestion.sources.books_to_scrape`.

Extraction strategy
-------------------
Listing cards already carry title, price (including ``<del>``/``<ins>`` sale
pairs), product URL, image, stock status and category slugs in the ``<li>``
classes. A detail fetch adds the short description and any star rating; when
the detail fetch fails the listing-level record is kept rather than dropped.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, ClassVar
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.base import ProductSource, RawProduct, register_source

log = get_logger(__name__)

POST_ID_RE = re.compile(r"post-(\d+)")
CATEGORY_CLASS_RE = re.compile(r"product_cat-([a-z0-9_-]+)")
RATING_RE = re.compile(r"Rated\s+([0-9]+(?:\.[0-9]+)?)\s+out of 5", re.IGNORECASE)


def _text(element: Tag | None) -> str | None:
    if element is None:
        return None
    text = element.get_text(" ", strip=True)
    return text or None


def _compact_price(text: str | None) -> str | None:
    """Glue currency symbols back to the amount (``£ 63.00`` -> ``£63.00``).

    WooCommerce wraps the symbol in its own ``<span>``, so space-joined text
    separates them; the price parser accepts both, but compact form keeps the
    raw audit trail identical to the shop display.
    """
    if text is None:
        return None
    return re.sub(r"([£$€¥₹])\s+", r"\1", text)


@register_source
class ScrapeMeSource(ProductSource):
    """HTML scraper: WooCommerce listing pages with an enriching detail fetch."""

    code: ClassVar[str] = "scrapeme_products"
    name: ClassVar[str] = "ScrapeMe.live shop (permitted sandbox)"
    kind: ClassVar[str] = "scrape"
    base_url: ClassVar[str] = "https://scrapeme.live/shop/"
    terms_url: ClassVar[str] = "https://scrapeme.live/"
    license_note: ClassVar[str] = (
        "Practice shop published for scraping exercises. Non-commercial, robots.txt friendly."
    )
    default_currency: ClassVar[str] = "GBP"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "WooCommerce practice shop with GBP prices, sale pairs, stock flags and "
        "category slugs in the markup. Detail pages add descriptions and ratings."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 1

        while emitted < limit:
            listing_url = self.base_url if page == 1 else f"{self.base_url}page/{page}/"
            self._count_request()
            try:
                soup = self.client.get_soup(listing_url)
            except Exception as exc:
                self.errors.append(f"listing {listing_url}: {exc}")
                break
            articles = soup.select("ul.products li.product")
            if not articles:
                break

            for article in articles:
                if emitted >= limit:
                    break
                if not isinstance(article, Tag):
                    continue
                raw = self._listing_raw(article, listing_url)
                if raw is None:
                    continue
                self._enrich_from_detail(raw)
                yield raw
                emitted += 1

            if soup.select_one("nav.woocommerce-pagination a.next") is None:
                break
            page += 1

    # ------------------------------------------------------------------ parsing
    def _listing_raw(self, article: Tag, listing_url: str) -> RawProduct | None:
        """Build a record from one ``li.product`` card (pure function of markup)."""
        link = article.select_one("a.woocommerce-LoopProduct-link")
        title_element = article.select_one("h2.woocommerce-loop-product__title")
        name = _text(title_element)
        if link is None or not name:
            return None
        detail_url = urljoin(listing_url, str(link.get("href") or ""))

        price_text, list_price_text = self._price_texts(article.select_one("span.price"))

        classes: list[str] = [str(cls) for cls in (article.get("class") or [])]
        post_id = next(
            (match.group(1) for cls in classes if (match := POST_ID_RE.match(cls))),
            None,
        )
        categories = [
            match.group(1).replace("-", " ").replace("_", " ")
            for cls in classes
            if (match := CATEGORY_CLASS_RE.match(cls))
        ]
        image = article.select_one("img")
        image_url = str(image.get("src") or "") or None if image else None

        return RawProduct(
            source_code=self.code,
            source_product_id=post_id or detail_url.rstrip("/").rsplit("/", 1)[-1],
            name=name,
            category=categories[0].title() if categories else None,
            price_text=price_text,
            list_price_text=list_price_text,
            currency_hint=self.default_currency,
            availability_text="in_stock" if "instock" in classes else "out_of_stock",
            in_stock_flag=("outofstock" not in classes),
            url=detail_url or None,
            image_url=image_url,
            payload={"categories": categories, "post_id": post_id},
        )

    @staticmethod
    def _price_texts(price_element: Tag | None) -> tuple[str | None, str | None]:
        """Split a WooCommerce price block into (sale, regular) texts.

        A sale renders as ``<del>£80.00</del> <ins>£63.00</ins>``; a regular
        price is the whole block's text.
        """
        if price_element is None:
            return None, None
        sale = price_element.select_one("ins")
        regular = price_element.select_one("del")
        if sale is not None:
            return _compact_price(_text(sale)), _compact_price(_text(regular))
        return _compact_price(_text(price_element)), None

    def _enrich_from_detail(self, raw: RawProduct) -> None:
        """Add description and rating from the product page; never raises."""
        if not raw.url:
            return
        try:
            self._count_request()
            response = self.client.get(raw.url)
            if not response.ok:
                self.errors.append(f"detail http {response.status_code} {raw.url}")
                return
            soup = BeautifulSoup(response.text, "lxml")
        except Exception as exc:
            self.errors.append(f"detail fetch failed {raw.url}: {exc}")
            return

        description = soup.select_one("div.woocommerce-product-details__short-description")
        if (text := _text(description)) and not raw.description:
            raw.description = text
        rating = soup.select_one("div.star-rating")
        if rating is not None and raw.rating_text is None:
            label = str(rating.get("aria-label") or "")
            if match := RATING_RE.search(label):
                raw.rating_text = f"{match.group(1)} out of 5"
        stock = soup.select_one("p.stock")
        if (stock_text := _text(stock)) and raw.availability_text in (None, "unknown"):
            raw.availability_text = stock_text

    def health_check(self) -> dict[str, Any]:
        info = super().health_check()
        info["robots_url"] = "https://scrapeme.live/robots.txt"
        info["robots_allows_crawl"] = True
        return info
