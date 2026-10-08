"""Scryfall card-search source (free public Magic: The Gathering API, no key).

Endpoint: https://api.scryfall.com/cards/search?q=game%3Apaper+usd%3E0&order=edhrec
Terms:     https://scryfall.com/docs/api - free for developers; a descriptive
           User-Agent is required (the ingestion client already sends one).
           Follow ``next_page`` while ``has_more`` is true.

Paper cards with a USD price carry real retail prices (regular and foil), the
set name, rarity and type line, which feeds price-level and spread analysis
for physical collectibles.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: Paper cards that actually have a USD price, most-played first.
SEARCH_QUERY = "game:paper usd>0"
ORDER = "edhrec"


@register_source
class ScryfallCardsSource(ProductSource):
    """Magic paper cards with USD/foil prices, set, rarity and type line."""

    code: ClassVar[str] = "scryfall_cards"
    name: ClassVar[str] = "Scryfall Cards API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.scryfall.com/cards/search"
    terms_url: ClassVar[str] = "https://scryfall.com/docs/api"
    license_note: ClassVar[str] = "Free public API; descriptive User-Agent required, supplied by the client."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Magic paper cards with real retail USD and foil prices, set name, "
        "rarity and type line."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        url: str | None = self.base_url
        params: dict[str, Any] | None = {"q": SEARCH_QUERY, "order": ORDER}
        seen: set[str] = set()

        while emitted < limit and url is not None:
            self._count_request()
            try:
                payload = self.client.get_json(url, params=params or {})
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"search page: {exc}")
                return
            params = None  # next_page already carries the query string
            items = payload.get("data") if isinstance(payload, dict) else None
            if not items:
                return
            for item in items:
                raw = self._to_raw(item)
                if raw is None or raw.source_product_id in seen:
                    continue
                seen.add(raw.source_product_id)
                yield raw
                emitted += 1
                if emitted >= limit:
                    return
            url = payload.get("next_page") if isinstance(payload, dict) else None
            if not payload.get("has_more", False):
                return

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        prices = item.get("prices") or {}
        price = prices.get("usd") if isinstance(prices, dict) else None
        if not name or price is None:
            return None
        card_id = item.get("id")
        images = item.get("image_uris") or {}
        rarity = item.get("rarity")
        return RawProduct(
            source_code=self.code,
            source_product_id=str(card_id or item.get("oracle_id") or name),
            name=str(name),
            category="Trading Cards",
            price_text=str(price),
            currency_hint=self.default_currency,
            list_price_text=str(prices.get("usd_foil")) if prices.get("usd_foil") else None,
            rating_text=None,
            availability_text="in_stock",  # listed with a retail price
            in_stock_flag=True,
            url=item.get("scryfall_uri"),
            image_url=images.get("small") if isinstance(images, dict) else None,
            brand=str(item.get("set_name") or ""),
            description=str(item.get("type_line") or "") or None,
            payload={
                "set": item.get("set"),
                "rarity": rarity,
                "usd_foil": prices.get("usd_foil"),
                "edhrec_rank": item.get("edhrec_rank"),
            },
        )
