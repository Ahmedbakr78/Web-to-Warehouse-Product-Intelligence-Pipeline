"""SampleAPIs Switch-games source (free sample-data API, no key required).

Endpoint: https://api.sampleapis.com/switch/games
Terms:     https://sampleapis.com/ - sample data published for learning use;
           the whole 1000+ title catalogue arrives in a single JSON array.

Switch titles with genres, developers, publishers and release dates. No
prices are published, so rows land as catalogue depth for the games
vertical next to the priced Steam and CheapShark feeds.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source


@register_source
class SampleApisSwitchSource(ProductSource):
    """Nintendo Switch catalogue with genres, studios and release dates."""

    code: ClassVar[str] = "sampleapis_switch"
    name: ClassVar[str] = "SampleAPIs Switch Games"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.sampleapis.com/switch/games"
    terms_url: ClassVar[str] = "https://sampleapis.com/"
    license_note: ClassVar[str] = "Free sample data for learning use, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Switch catalogue: genres, developers, publishers and release dates per title."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        self._count_request()
        try:
            items = self.client.get_json(self.base_url)
        except Exception as exc:  # without the catalogue there is nothing to do
            self.errors.append(f"catalogue: {exc}")
            return
        if not isinstance(items, list):
            return
        emitted = 0
        seen: set[str] = set()
        for item in items:
            if emitted >= limit:
                return
            raw = self._to_raw(item)
            if raw is None or raw.source_product_id in seen:
                continue
            seen.add(raw.source_product_id)
            yield raw
            emitted += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        if not name:
            return None
        genres = [str(genre) for genre in item.get("genre") or []]
        developers = [str(dev) for dev in item.get("developers") or []]
        publishers = [str(pub) for pub in item.get("publishers") or []]
        releases = item.get("releaseDates") or {}
        year = releases.get("Japan") or releases.get("NorthAmerica") or releases.get("Europe") or ""
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or name),
            name=str(name),
            category="Video Games",
            brand=developers[0] if developers else None,
            price_text=None,
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=None,
            image_url=None,
            description=". ".join(
                part
                for part in [
                    f"Genres: {', '.join(genres)}" if genres else "",
                    f"Publishers: {', '.join(publishers)}" if publishers else "",
                    f"Released: {year}" if year else "",
                ]
                if part
            )
            or None,
        )
