"""Internet Archive texts source (free, no key, open library).

Endpoint: https://archive.org/advancedsearch.php?q=mediatype:texts (JSON, paged)
Terms:     https://archive.org/about/terms.php - open metadata, robots-allowed
            paths only (``/control`` and ``/report`` are never touched).

Public-domain texts with title, creator, download counts and full-text links.
No price or rating is published, so these rows deepen the Books shelf while
the completeness DQ rules record the gaps honestly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 50

#: One run never walks the 50M+ collection.
MAX_PAGES = 6


@register_source
class ArchiveTextsSource(ProductSource):
    """Public-domain texts with creators and download counts."""

    code: ClassVar[str] = "archive_texts"
    name: ClassVar[str] = "Internet Archive Texts"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://archive.org/advancedsearch.php"
    terms_url: ClassVar[str] = "https://archive.org/about/terms.php"
    license_note: ClassVar[str] = "Internet Archive - open metadata via advancedsearch."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Public-domain texts: title, creator, download counts and reader links, "
        "paged through the texts collection."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 0

        while emitted < limit and page < MAX_PAGES:
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={
                        "q": "mediatype:texts",
                        "fl[]": ["identifier", "title", "creator", "downloads", "date"],
                        "rows": min(PAGE_SIZE, max(limit - emitted, 1)),
                        "page": page + 1,
                        "output": "json",
                    },
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            docs = (payload.get("response") or {}).get("docs") if isinstance(payload, dict) else None
            if not docs:
                return
            for item in docs:
                raw = self._to_raw(item)
                if raw is None:
                    continue
                yield raw
                emitted += 1
                if emitted >= limit:
                    return
            page += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        identifier = item.get("identifier")
        title = item.get("title")
        if not title:
            return None
        if isinstance(title, list):
            title = title[0] if title else None
        if not title:
            return None
        creator = item.get("creator")
        if isinstance(creator, list):
            creator = creator[0] if creator else None
        downloads = item.get("downloads")
        return RawProduct(
            source_code=self.code,
            source_product_id=str(identifier or title),
            name=f"{title} - {creator}" if creator else str(title),
            category="Books",
            price_text=None,  # open library catalogue: no price published
            currency_hint=self.default_currency,
            rating_text=None,
            rating_count_text=str(downloads) if downloads is not None else None,
            availability_text=None,
            in_stock_flag=None,
            url=f"https://archive.org/details/{identifier}" if identifier else None,
            image_url=f"https://archive.org/services/img/{identifier}" if identifier else None,
            brand=str(creator) if creator else None,
            description=(f"Added {item.get('date')}" if item.get("date") else None),
            payload={"downloads": downloads, "date": item.get("date")},
        )
