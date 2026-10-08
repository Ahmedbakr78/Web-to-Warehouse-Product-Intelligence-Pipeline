"""Google Books API source (official, free, programmatic-access API).

Endpoint: https://www.googleapis.com/books/v1/volumes?q=subject:fiction
Terms:    https://developers.google.com/books/terms - the API exists for
          programmatic access; keyless quota is limited, a free API key
          raises it substantially.

Compliance notes
----------------
* ``https://www.googleapis.com/robots.txt`` does not exist (404), which the
  transport layer treats as allow-all per the RFC 9309 fallback semantics.
* Set ``GOOGLE_BOOKS_API_KEY`` (free from Google Cloud Console, no billing)
  when the shared keyless quota is exhausted; without it the API returns
  HTTP 429 and the subject is recorded as a warning instead of killing the
  run, like every other source failure.

Prices come from ``saleInfo.listPrice`` (often USD) when Google sells the
ebook; most records carry ratings but no price, which exercises the
completeness rules of the data-quality framework.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

DEFAULT_SUBJECTS = ("fiction", "computers", "cooking", "history", "science")

#: Google Books saleability values that mean a copy can actually be obtained.
SALEABLE = {"FOR_SALE", "FOR_SALE_AND_RENTAL", "FREE", "FOR_RENTAL_ONLY"}


@register_source
class GoogleBooksSource(ProductSource):
    """Book metadata with author, publisher, ratings and optional list prices."""

    code: ClassVar[str] = "google_books"
    name: ClassVar[str] = "Google Books API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://www.googleapis.com/books/v1/volumes"
    terms_url: ClassVar[str] = "https://developers.google.com/books/terms"
    license_note: ClassVar[str] = "Google Books API - free quota, keyless for testing, API key recommended."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Official Books API returning title, authors, publisher, categories, "
        "ratings and Google list prices where the ebook is sold."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        per_subject = max(5, limit // len(DEFAULT_SUBJECTS))
        emitted = 0

        for subject in DEFAULT_SUBJECTS:
            if emitted >= limit:
                break
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params=self._params(subject, per_subject),
                )
            except Exception as exc:  # a failing subject must not kill the run
                self.errors.append(f"{subject}: {exc}")
                continue

            for item in payload.get("items") or []:
                if emitted >= limit:
                    break
                raw = self._to_raw(item, subject)
                if raw is None:
                    continue
                yield raw
                emitted += 1

    def _params(self, subject: str, per_subject: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": f"subject:{subject}",
            "maxResults": max(1, min(40, per_subject)),
            "printType": "books",
            "orderBy": "relevance",
        }
        if settings.google_books_api_key:
            params["key"] = settings.google_books_api_key
        return params

    def _to_raw(self, item: dict[str, Any], subject: str) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        info = item.get("volumeInfo") or {}
        title = info.get("title")
        if not title:
            return None
        authors = info.get("authors") or []
        author = authors[0] if isinstance(authors, list) and authors else None
        categories = info.get("categories") or []
        category = categories[0] if isinstance(categories, list) and categories else subject

        sale = item.get("saleInfo") or {}
        saleability = str(sale.get("saleability") or "")
        list_price = sale.get("listPrice") or {}
        amount = list_price.get("amount")
        currency = list_price.get("currencyCode") or self.default_currency
        saleable = saleability in SALEABLE

        rating = info.get("averageRating")
        rating_count = info.get("ratingsCount")
        image_links = info.get("imageLinks") or {}
        volume_id = str(item.get("id") or title)
        return RawProduct(
            source_code=self.code,
            source_product_id=volume_id,
            name=f"{title} - {author}" if author else str(title),
            category=str(category).title(),
            price_text=str(amount) if amount not in (None, "") else None,
            currency_hint=str(currency),
            rating_text=f"{rating} out of 5" if rating else None,
            rating_count_text=str(rating_count) if rating_count else None,
            availability_text="in_stock" if saleable else None,
            in_stock_flag=True if saleable else None,
            url=str(info.get("infoLink") or f"https://books.google.com/books?id={volume_id}"),
            image_url=str(image_links.get("thumbnail") or image_links.get("smallThumbnail") or ""),
            brand=str(info.get("publisher") or "") or None,
            description=str(info.get("description") or "") or None,
            payload={"saleability": saleability, "subject": subject},
        )
