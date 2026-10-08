"""Gutendex (Project Gutenberg) books source (free, no key, open catalogue).

Endpoint: https://gutendex.com/books?page=1
Terms:     https://gutendex.com/ - free API over the public-domain Gutenberg
           catalogue; paged with ``page`` and a ``next`` link.

Like the Google Books source, Gutenberg records carry no price, so they flow
through the pipeline as catalogue depth for category/author analysis while
the completeness DQ rules record the missing prices honestly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 32

#: One run never walks the 70k+ catalogue.
MAX_PAGES = 12


@register_source
class GutendexBooksSource(ProductSource):
    """Public-domain books with authors, subjects and popularity counts."""

    code: ClassVar[str] = "gutendex_books"
    name: ClassVar[str] = "Gutendex Books API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://gutendex.com/books"
    terms_url: ClassVar[str] = "https://gutendex.com/"
    license_note: ClassVar[str] = "Free API over the public-domain Gutenberg catalogue."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Public-domain books: title, authors, subject shelves and download "
        "counts, paged through the Gutenberg catalogue."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 1

        while emitted < limit and page <= MAX_PAGES:
            self._count_request()
            try:
                payload = self.client.get_json(self.base_url, params={"page": page})
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            items = payload.get("results") if isinstance(payload, dict) else None
            if not items:
                return
            for item in items:
                raw = self._to_raw(item)
                if raw is None:
                    continue
                yield raw
                emitted += 1
                if emitted >= limit:
                    return
            if not payload.get("next"):
                return
            page += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        if not title:
            return None
        authors = item.get("authors") or []
        author = authors[0].get("name") if authors and isinstance(authors[0], dict) else None
        subjects = [entry for entry in (item.get("subjects") or []) if isinstance(entry, str)]
        category = self._shelf(subjects)
        formats = item.get("formats") or {}
        book_id = item.get("id")
        summaries = [entry for entry in (item.get("summaries") or []) if isinstance(entry, str)]
        return RawProduct(
            source_code=self.code,
            source_product_id=str(book_id or title),
            name=f"{title} - {author}" if author else str(title),
            category=category,
            price_text=None,  # public-domain catalogue: no price published
            currency_hint=self.default_currency,
            rating_text=None,
            rating_count_text=None,
            availability_text=None,
            in_stock_flag=None,
            url=f"https://www.gutenberg.org/ebooks/{book_id}" if book_id is not None else None,
            image_url=formats.get("image/jpeg") if isinstance(formats, dict) else None,
            brand=str(author) if author else None,
            description=(summaries[0][:600] if summaries else None),
            payload={
                "languages": item.get("languages"),
                "download_count": item.get("download_count"),
                "bookshelves": item.get("bookshelves"),
            },
        )

    @staticmethod
    def _shelf(subjects: list[str]) -> str:
        """First subject shelf, cleaned for the category normaliser."""
        if not subjects:
            return "Books"
        shelf = subjects[0].split("--")[0].strip()
        return shelf.title()[:64] or "Books"
