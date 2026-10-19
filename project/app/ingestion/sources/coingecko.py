"""CoinGecko markets source (free public crypto-market API, no key required).

Endpoint: https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=250
Terms:     https://www.coingecko.com/en/api_terms - free tier needs no key
           (roughly 10-30 calls/minute); paged with ``per_page``/``page``.

Complements the CoinCap source with 24h high/low ranges, all-time high/low
reference points and total volume, which feeds range and drawdown analysis
with real market data.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 250


@register_source
class CoinGeckoMarketsSource(ProductSource):
    """Crypto markets with price, 24h range, 24h change and ATH/ATL reference."""

    code: ClassVar[str] = "coingecko_markets"
    name: ClassVar[str] = "CoinGecko Markets API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.coingecko.com/api/v3/coins/markets"
    terms_url: ClassVar[str] = "https://www.coingecko.com/en/api_terms"
    license_note: ClassVar[str] = "Free tier needs no key; tiny paged budget."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 10
    min_delay_seconds: ClassVar[float] = 3.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Crypto markets by market cap: live USD price, 24h high/low, 24h "
        "change, volume and all-time high/low reference points."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 1

        while emitted < limit:
            self._count_request()
            try:
                items = self.client.get_json(
                    self.base_url,
                    params={
                        "vs_currency": "usd",
                        "order": "market_cap_desc",
                        "per_page": min(PAGE_SIZE, limit - emitted),
                        "page": page,
                        "price_change_percentage": "24h",
                    },
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            if not isinstance(items, list) or not items:
                return
            for item in items:
                raw = self._to_raw(item)
                if raw is None:
                    continue
                yield raw
                emitted += 1
                if emitted >= limit:
                    return
            if len(items) < PAGE_SIZE:
                return
            page += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        price = item.get("current_price")
        if not name or price is None:
            return None
        symbol = str(item.get("symbol") or "").upper()
        change = item.get("price_change_percentage_24h")
        try:
            change_text = f"{float(change):+.2f}% 24h" if change is not None else None
        except (TypeError, ValueError):
            change_text = None
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or symbol or name),
            name=f"{name} ({symbol})" if symbol else str(name),
            category="Cryptocurrency",
            price_text=str(price),
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=f"https://www.coingecko.com/en/coins/{item.get('id')}" if item.get("id") else None,
            image_url=item.get("image"),
            brand=None,
            description=change_text,
            payload={
                "symbol": symbol,
                "market_cap": item.get("market_cap"),
                "total_volume": item.get("total_volume"),
                "high_24h": item.get("high_24h"),
                "low_24h": item.get("low_24h"),
                "change_24h_pct": change,
                "ath": item.get("ath"),
                "atl": item.get("atl"),
            },
        )
