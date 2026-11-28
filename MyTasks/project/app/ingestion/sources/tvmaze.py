"""TVMaze shows source (free, no key, open TV catalogue).

Endpoint: https://api.tvmaze.com/shows?page=0 (250 shows per page, paged)
Terms:     https://www.tvmaze.com/api - free API, no authentication required.

Shows map to the retailer's media shelf: title, genres, network, poster image
and a 0-10 average rating (rescaled to 0-5 by the rating parser). No price or
stock is published, so these rows exercise the completeness DQ rules honestly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 250

#: One run never walks the whole catalogue.
MAX_PAGES = 4


@register_source
class TVMazeShowsSource(ProductSource):
    """TV shows with genres, network, posters and average ratings."""

    code: ClassVar[str] = "tvmaze_shows"
    name: ClassVar[str] = "TVMaze Shows API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.tvmaze.com/shows"
    terms_url: ClassVar[str] = "https://www.tvmaze.com/api"
    license_note: ClassVar[str] = "TVMaze - free TV catalogue API, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "TV shows: title, genres, network, poster, average rating and run dates, "
        "paged through the full catalogue."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 0

        while emitted < limit and page <= MAX_PAGES:
            self._count_request()
            try:
                payload = self.client.get_json(self.base_url, params={"page": page})
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            if not isinstance(payload, list) or not payload:
                return
            for item in payload:
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
        name = item.get("name")
        if not name:
            return None
        show_id = item.get("id")
        genres = [g for g in (item.get("genres") or []) if isinstance(g, str)]
        category = genres[0] if genres else "TV Shows"
        network = item.get("network") or {}
        network_name = network.get("name") if isinstance(network, dict) else None
        rating = (item.get("rating") or {}).get("average")
        image = item.get("image") or {}
        summary = str(item.get("summary") or "")
        return RawProduct(
            source_code=self.code,
            source_product_id=str(show_id or name),
            name=str(name),
            category=str(category).title(),
            price_text=None,  # catalogue API: no price published
            currency_hint=self.default_currency,
            rating_text=f"{rating} out of 10" if rating else None,
            rating_count_text=None,
            availability_text=None,
            in_stock_flag=None,
            url=item.get("url") if isinstance(item.get("url"), str) else None,
            image_url=image.get("medium") if isinstance(image, dict) else None,
            brand=str(network_name) if network_name else None,
            description=(summary[:600] if summary else None),
            payload={
                "status": item.get("status"),
                "premiered": item.get("premiered"),
                "runtime": item.get("runtime"),
                "genres": genres,
            },
        )
