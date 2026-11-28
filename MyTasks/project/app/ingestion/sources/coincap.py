"""CoinCap v2 assets source (free public crypto-market API, no key required).

Endpoint: https://api.coincap.io/v2/assets?limit=200&offset=0
Terms:     https://coincap.io/ - free market-data API; paged with limit/offset.

Assets carry live USD prices plus 24h change, market cap, volume and rank,
which feeds the volatility, movers and anomaly analytics with genuinely
moving prices.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 200


@register_source
class CoinCapAssetsSource(ProductSource):
    """Crypto assets with live USD prices, 24h change, market cap and rank."""

    code: ClassVar[str] = "coincap_assets"
    name: ClassVar[str] = "CoinCap Assets API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.coincap.io/v2/assets"
    terms_url: ClassVar[str] = "https://coincap.io/"
    license_note: ClassVar[str] = "Free public market-data API, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Crypto market ranked by market cap: live USD price, 24h change, "
        "volume and rank for each asset."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        offset = 0

        while emitted < limit:
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={"limit": min(PAGE_SIZE, limit - emitted), "offset": offset},
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"offset {offset}: {exc}")
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
            if len(items) < PAGE_SIZE:
                return
            offset += len(items)

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        price = item.get("priceUsd")
        if not name or price is None:
            return None
        symbol = str(item.get("symbol") or "").upper()
        rank = item.get("rank")
        change = item.get("changePercent24Hr")
        try:
            change_text = f"{float(change):.2f}% 24h" if change is not None else None
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
            url=f"https://coincap.io/assets/{item.get('id')}" if item.get("id") else None,
            image_url=None,
            brand=None,
            description=(
                f"Rank #{rank} by market cap."
                + (f" {change_text}." if change_text else "")
                if rank is not None
                else change_text
            ),
            payload={
                "symbol": symbol,
                "rank": rank,
                "market_cap_usd": item.get("marketCapUsd"),
                "volume_24h_usd": item.get("volumeUsd24Hr"),
                "change_24h_pct": change,
                "vwap_24h": item.get("vwap24Hr"),
            },
        )
