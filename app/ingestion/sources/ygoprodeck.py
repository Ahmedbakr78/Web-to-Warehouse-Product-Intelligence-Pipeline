"""YGOPRODeck card-info source (free community API, no key).

Endpoint: https://db.ygoprodeck.com/api/v7/cardinfo.php?fname=&num=&offset=
Terms:    https://ygoprodeck.com/api-guide - free for small projects; we use
          fuzzy-name queries capped at 20 cards each with a polite budget.

Trading cards with TCGplayer market prices, monster-type categories and
archetype brands, which exercises market-price mapping plus archetype/brand
normalisation.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: Fuzzy-name queries; a small deterministic slice of each keeps the run tiny.
QUERIES: tuple[str, ...] = (
    "dragon",
    "spellcaster",
    "warrior",
    "zombie",
    "spell",
    "trap",
)

#: Cards per query.
PER_QUERY = 20


@register_source
class YGOProDeckCardsSource(ProductSource):
    """Trading cards with market prices, monster-type categories, archetypes."""

    code: ClassVar[str] = "ygoprodeck_cards"
    name: ClassVar[str] = "YGOPRODeck Cards API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
    terms_url: ClassVar[str] = "https://ygoprodeck.com/api-guide"
    license_note: ClassVar[str] = "Free community API; responses cached, polite budget."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Trading cards across a few fuzzy-name queries: TCGplayer market "
        "prices, monster-type categories and archetype brands."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        seen: set[str] = set()
        for query in QUERIES:
            if emitted >= limit:
                return
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={"fname": query, "num": PER_QUERY, "offset": 0},
                )
            except Exception as exc:  # a failing query must not kill the run
                self.errors.append(f"query {query!r}: {exc}")
                continue
            items = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                continue
            for item in items:
                raw = self._to_raw(item)
                if raw is None or raw.source_product_id in seen:
                    continue
                seen.add(raw.source_product_id)
                yield raw
                emitted += 1
                if emitted >= limit:
                    return

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        if not name:
            return None
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id")),
            name=str(name),
            category=str(item.get("race") or item.get("type") or "Card Game").title(),
            price_text=self._market_price(item),
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=str(item.get("ygoprodeck_url") or "") or None,
            image_url=self._image(item),
            brand=str(item.get("archetype") or "Yu-Gi-Oh!"),
            description=str(item.get("desc") or "") or None,
            payload={
                "type": item.get("type"),
                "attribute": item.get("attribute"),
                "level": item.get("level"),
                "atk": item.get("atk"),
                "def": item.get("def"),
            },
        )

    @staticmethod
    def _market_price(item: dict[str, Any]) -> str | None:
        """Prefer the TCGplayer market price, fall back to a set price."""
        prices = item.get("card_prices") or []
        if isinstance(prices, list) and prices:
            first = prices[0] if isinstance(prices[0], dict) else {}
            for key in ("tcgplayer_price", "cardmarket_price", "ebay_price"):
                try:
                    amount = float(first.get(key))
                except (TypeError, ValueError):
                    continue
                if amount > 0:
                    return f"{amount:.2f}"
        for card_set in item.get("card_sets") or []:
            if not isinstance(card_set, dict):
                continue
            try:
                amount = float(card_set.get("set_price"))
            except (TypeError, ValueError):
                continue
            if amount > 0:
                return f"{amount:.2f}"
        return None

    @staticmethod
    def _image(item: dict[str, Any]) -> str | None:
        images = item.get("card_images") or []
        if isinstance(images, list) and images and isinstance(images[0], dict):
            return str(images[0].get("image_url") or "") or None
        return None
