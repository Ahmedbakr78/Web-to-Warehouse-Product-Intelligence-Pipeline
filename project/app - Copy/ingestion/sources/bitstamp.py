"""Bitstamp public ticker source (free keyless spot-market data).

Endpoints: https://www.bitstamp.net/api/v2/trading-pairs-info/
           https://www.bitstamp.net/api/v2/ticker/{pair}/
Terms:     https://www.bitstamp.net/api/ - public market data needs no key.
           One call enumerates the book, then tickers are pulled per pair.

Each ticker carries last, high, low, open, vwap and volume, which feeds the
volatility and movers analytics with real 24h ranges. Pairs are sorted for
determinism and only USD-quoted spot pairs become products.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAIRS_URL = "https://www.bitstamp.net/api/v2/trading-pairs-info/"
TICKER_URL = "https://www.bitstamp.net/api/v2/ticker/{pair}/"


@register_source
class BitstampTickersSource(ProductSource):
    """USD spot tickers with last/high/low/open, vwap and volume."""

    code: ClassVar[str] = "bitstamp_tickers"
    name: ClassVar[str] = "Bitstamp Tickers API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://www.bitstamp.net/api/v2/ticker/"
    terms_url: ClassVar[str] = "https://www.bitstamp.net/api/"
    license_note: ClassVar[str] = "Public market data, keyless; small per-pair budget."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "USD spot tickers: last trade with 24h high/low/open, vwap and volume."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        pairs = self._usd_pairs()
        if not pairs:
            return
        emitted = 0
        for symbol, display in pairs:
            if emitted >= limit:
                return
            self._count_request()
            try:
                ticker = self.client.get_json(TICKER_URL.format(pair=symbol))
            except Exception as exc:  # one bad pair must not kill the run
                self.errors.append(f"ticker {symbol}: {exc}")
                continue
            raw = self._to_raw(symbol, display, ticker)
            if raw is None:
                continue
            yield raw
            emitted += 1

    def _usd_pairs(self) -> list[tuple[str, str]]:
        """Enabled USD-quoted pairs, sorted for determinism."""
        self._count_request()
        try:
            items = self.client.get_json(PAIRS_URL)
        except Exception as exc:  # no pair list, no tickers
            self.errors.append(f"trading pairs: {exc}")
            return []
        if not isinstance(items, list):
            self.errors.append("trading pairs: unexpected response shape")
            return []
        pairs = sorted(
            (entry.get("url_symbol"), entry.get("name"))
            for entry in items
            if isinstance(entry, dict)
            and entry.get("url_symbol")
            and entry.get("name")
            and str(entry.get("name")).upper().endswith("/USD")
            and str(entry.get("trading", "Enabled")).lower() == "enabled"
        )
        return [(symbol, name) for symbol, name in pairs if symbol and name]

    def _to_raw(self, symbol: str, display: str, ticker: Any) -> RawProduct | None:
        if not isinstance(ticker, dict):
            self.errors.append(f"ticker {symbol}: unexpected response shape")
            return None
        last = ticker.get("last")
        if last is None:
            return None
        base = display.split("/")[0].upper()
        return RawProduct(
            source_code=self.code,
            source_product_id=symbol,
            name=f"{base} / USD",
            category="Cryptocurrency",
            price_text=str(last),
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=f"https://www.bitstamp.net/markets/{symbol}/",
            image_url=None,
            brand=None,
            description=None,
            payload={
                "pair": display,
                "high_24h": ticker.get("high"),
                "low_24h": ticker.get("low"),
                "open_24h": ticker.get("open"),
                "vwap": ticker.get("vwap"),
                "volume_24h": ticker.get("volume"),
            },
        )
