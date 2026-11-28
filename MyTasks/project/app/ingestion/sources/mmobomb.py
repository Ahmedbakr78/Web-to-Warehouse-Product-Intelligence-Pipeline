"""MMOBomb (formerly MMOs.com) free-to-play games directory (free API, no key).

Endpoint: https://www.mmobomb.com/api1/games?sort-by=popularity
Terms:     https://www.mmobomb.com/api - free API for developers; the whole
           catalogue arrives in one response, so a run costs a single request.

Games carry real genres, platforms, publishers and thumbnails. No prices are
published (free-to-play directory), so records contribute catalogue depth for
category/platform analysis while the completeness rules note the gap.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source


@register_source
class MMOBombGamesSource(ProductSource):
    """Free-to-play games with genre, platform, publisher and artwork."""

    code: ClassVar[str] = "mmobomb_games"
    name: ClassVar[str] = "MMOBomb Games API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://www.mmobomb.com/api1/games"
    terms_url: ClassVar[str] = "https://www.mmobomb.com/api"
    license_note: ClassVar[str] = "Free games-directory API, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Free-to-play games directory: title, genre, platform, publisher, "
        "thumbnail and short description in a single response."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        self._count_request()
        try:
            items = self.client.get_json(self.base_url, params={"sort-by": "popularity"})
        except Exception as exc:  # without the catalogue there is nothing to do
            self.errors.append(f"catalogue: {exc}")
            return
        if not isinstance(items, list):
            self.errors.append("catalogue: unexpected response shape")
            return
        emitted = 0
        for item in items:
            if emitted >= limit:
                return
            raw = self._to_raw(item)
            if raw is None:
                continue
            yield raw
            emitted += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        if not title:
            return None
        publisher = item.get("publisher") or item.get("developer")
        platform = item.get("platform") or ""
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or title),
            name=str(title),
            category=str(item.get("genre") or "Games").title(),
            price_text=None,  # free-to-play directory: no price published
            currency_hint=self.default_currency,
            rating_text=None,
            rating_count_text=None,
            availability_text=None,
            in_stock_flag=None,
            url=item.get("game_url"),
            image_url=item.get("thumbnail"),
            brand=str(publisher) if publisher else None,
            description=str(item.get("short_description") or "")[:600] or None,
            payload={"platform": platform, "developer": item.get("developer"), "release_date": item.get("release_date")},
        )
