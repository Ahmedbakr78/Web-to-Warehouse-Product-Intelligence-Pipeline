"""Open Library Books API source (Internet Archive, free and open).

Endpoint: https://openlibrary.org/search.json?q=subject:electronics&limit=50&fields=...
Terms:    https://openlibrary.org/terms - open data, CC0 for bibliographic metadata.

This source intentionally publishes *no* availability information and often *no*
price, which makes it a perfect regression case for the completeness rules of the
data-quality framework.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

DEFAULT_FIELDS = "key,title,author_name,first_publish_year,edition_count,ratings_average,price,currency,isbn,subject,number_of_pages_median"
DEFAULT_SUBJECTS = ("electronics", "computers", "cooking", "history", "science")


@register_source
class OpenLibraryBooksSource(ProductSource):
    """Bibliographic feed with prices in mixed currencies (exercises FX normalisation)."""

    code: ClassVar[str] = "openlibrary_books"
    name: ClassVar[str] = "Open Library Books API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://openlibrary.org/search.json"
    terms_url: ClassVar[str] = "https://openlibrary.org/terms"
    license_note: ClassVar[str] = "Open Library / Internet Archive - open bibliographic data."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.2
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Search API returning books with author, publish year, ratings and optional "
        "prices. Multi-currency prices and missing availability are expected."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        per_subject = max(10, limit // len(DEFAULT_SUBJECTS))
        emitted = 0

        for subject in DEFAULT_SUBJECTS:
            if emitted >= limit:
                break
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={
                        "q": f"subject:{subject}",
                        "fields": DEFAULT_FIELDS,
                        "limit": per_subject,
                        "page": 1,
                    },
                )
            except Exception as exc:  # a failing subject must not kill the run
                self.errors.append(f"{subject}: {exc}")
                continue

            for item in payload.get("docs") or []:
                if emitted >= limit:
                    break
                raw = self._to_raw(item, subject)
                if raw is None:
                    continue
                yield raw
                emitted += 1

    def _to_raw(self, item: dict[str, Any], subject: str) -> RawProduct | None:
        title = item.get("title")
        if not title:
            return None
        price = item.get("price")
        if isinstance(price, list):
            price = price[0] if price else None
        authors = item.get("author_name") or []
        author = authors[0] if isinstance(authors, list) and authors else None
        subjects = item.get("subject") or []
        category = subjects[0] if isinstance(subjects, list) and subjects else subject
        rating = item.get("ratings_average")
        return RawProduct(
            source_code=self.code,
            source_product_id=str(
                item.get("key") or item.get("isbn", [""])[0] if item.get("isbn") else title
            ),
            name=f"{title} - {author}" if author else str(title),
            category=str(category).title(),
            price_text=str(price) if price not in (None, "") else None,
            currency_hint=str(item.get("currency") or self.default_currency),
            rating_text=f"{rating} out of 5" if rating else None,
            rating_count_text=str(item.get("ratings_count")) if item.get("ratings_count") else None,
            availability_text="in_stock",  # a physical book on sale
            in_stock_flag=True,
            url=f"https://openlibrary.org{item.get('key')}"
            if str(item.get("key", "")).startswith("/")
            else None,
            brand=author,
            description=(
                f"{item.get('first_publish_year', '')} edition, "
                f"{item.get('edition_count', 0)} editions, "
                f"{item.get('number_of_pages_median', 'n/a')} pages"
            ),
            payload=item,
        )
