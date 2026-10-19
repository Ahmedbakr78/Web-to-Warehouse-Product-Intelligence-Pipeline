"""Open Library Books API source (Internet Archive, free and open).

Endpoint: https://openlibrary.org/subjects/<subject>.json (robots-allowed; the
``/search.json`` and ``/api/books`` paths are disallowed by robots.txt, so this
source deliberately uses the subject feed instead).
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

DEFAULT_SUBJECTS = ("electronics", "computers", "cooking", "history", "science")


@register_source
class OpenLibraryBooksSource(ProductSource):
    """Bibliographic feed with prices in mixed currencies (exercises FX normalisation)."""

    code: ClassVar[str] = "openlibrary_books"
    name: ClassVar[str] = "Open Library Books API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://openlibrary.org/subjects"
    terms_url: ClassVar[str] = "https://openlibrary.org/terms"
    license_note: ClassVar[str] = "Open Library / Internet Archive - open bibliographic data."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.2
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Subject feed returning books with author, publish year and edition "
        "counts. Missing prices/availability are expected."
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
                    f"{self.base_url}/{subject}.json",
                    params={"limit": per_subject},
                )
            except Exception as exc:  # a failing subject must not kill the run
                self.errors.append(f"{subject}: {exc}")
                # robots.txt / circuit decisions are host-wide: one block means
                # every subject will be blocked. Fail fast instead of logging
                # the same block five times.
                message = str(exc).lower()
                if any(marker in message for marker in ("robots", "circuit", "rate limited", "429")):
                    break
                continue

            for item in payload.get("works") or []:
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
        authors = item.get("authors") or []
        author = None
        if authors and isinstance(authors[0], dict):
            author = authors[0].get("name")
        key = str(item.get("key") or title)
        return RawProduct(
            source_code=self.code,
            source_product_id=key,
            name=f"{title} - {author}" if author else str(title),
            category=subject.title(),
            price_text=None,
            currency_hint=self.default_currency,
            rating_text=None,
            rating_count_text=str(item.get("edition_count")) if item.get("edition_count") else None,
            availability_text=None,
            in_stock_flag=None,
            url=f"https://openlibrary.org{key}" if key.startswith("/") else None,
            brand=author,
            description=(
                f"{item.get('first_publish_year', '')} edition, {item.get('edition_count', 0)} editions"
            ),
            payload=item,
        )
