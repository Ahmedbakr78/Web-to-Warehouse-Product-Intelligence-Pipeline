"""Pokemon TCG API source (free, keyless within generous rate limits).

Endpoint: https://api.pokemontcg.io/v2/cards?page=1&pageSize=250
Terms:     https://pokemontcg.io/ - free tier needs no key (1k requests/day);
           paged with ``page``/``pageSize`` and ``totalCount``.

Cards carry TCGplayer market/low/mid/high prices (holofoil preferred, reverse
holofoil fallback) plus Cardmarket trend prices, the set name, rarity and
types — real retail collectible prices for the spread analysis.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 250


@register_source
class PokemonTcgCardsSource(ProductSource):
    """Pokemon cards with TCGplayer/Cardmarket prices, set, rarity and types."""

    code: ClassVar[str] = "pokemontcg_cards"
    name: ClassVar[str] = "Pokemon TCG Cards API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.pokemontcg.io/v2/cards"
    terms_url: ClassVar[str] = "https://pokemontcg.io/"
    license_note: ClassVar[str] = "Free tier needs no key; polite paging well inside the daily budget."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Pokemon cards with TCGplayer market prices, Cardmarket trends, "
        "set name, rarity and types."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 1

        while emitted < limit:
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={"page": page, "pageSize": min(PAGE_SIZE, limit - emitted)},
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            items = payload.get("data") if isinstance(payload, dict) else None
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
            total = payload.get("totalCount") if isinstance(payload, dict) else None
            try:
                if total is not None and page * PAGE_SIZE >= int(total):
                    return
            except (TypeError, ValueError):
                pass
            if len(items) < PAGE_SIZE:
                return
            page += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        if not name:
            return None
        price, list_price, price_kind = self._prices(item)
        card_set = item.get("set") or {}
        set_name = card_set.get("name") if isinstance(card_set, dict) else None
        types = item.get("types") or []
        category = f"Trading Cards - {types[0]}" if types else "Trading Cards"
        images = item.get("images") or {}
        tcgplayer = item.get("tcgplayer") or {}
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or name),
            name=str(name),
            category=str(category)[:64],
            price_text=str(price) if price is not None else None,
            currency_hint=self.default_currency,
            list_price_text=str(list_price) if list_price is not None else None,
            rating_text=None,
            availability_text="in_stock" if price is not None else None,
            in_stock_flag=True if price is not None else None,
            url=tcgplayer.get("url") if isinstance(tcgplayer, dict) else None,
            image_url=images.get("small") if isinstance(images, dict) else None,
            brand=str(set_name) if set_name else None,
            description=str(item.get("rarity") or "") or None,
            payload={
                "set_id": card_set.get("id") if isinstance(card_set, dict) else None,
                "rarity": item.get("rarity"),
                "price_kind": price_kind,
                "cardmarket_trend": ((item.get("cardmarket") or {}).get("prices") or {}).get("trendPrice"),
            },
        )

    @staticmethod
    def _prices(item: dict[str, Any]) -> tuple[Any | None, Any | None, str | None]:
        """(market price, high reference, kind). Prefers holofoil market."""
        tcg = item.get("tcgplayer") or {}
        groups = tcg.get("prices") or {}
        for kind in ("holofoil", "reverseHolofoil", "1stEditionHolofoil", "unlimitedHolofoil", "normal"):
            band = groups.get(kind) if isinstance(groups, dict) else None
            if not isinstance(band, dict):
                continue
            market = band.get("market")
            if market is None:
                continue
            return market, band.get("high"), kind
        cardmarket = ((item.get("cardmarket") or {}).get("prices") or {}).get("trendPrice")
        if cardmarket is not None:
            return cardmarket, None, "cardmarket_trend"
        return None, None, None
