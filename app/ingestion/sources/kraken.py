"""Kraken public market-data source (keyless public endpoints).

Endpoints: https://api.kraken.com/0/public/AssetPairs
           https://api.kraken.com/0/public/Ticker?pair=...
Terms:    https://www.kraken.com/legal - public market data is free and
          keyless; api.kraken.com serves no robots.txt. One AssetPairs call
          enumerates the book, then tickers are pulled in small batches.

USD spot pairs behave like volatile products with live prices plus 24h
high/low/open reference points, which exercises the price-movement and
volatility analytics far more than the flat demo catalogues do.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: Pairs per Ticker call; keeps URLs short and the budget predictable.
TICKER_BATCH = 30

#: Only USD-quoted spot pairs become products.
USD_QUOTES = {"ZUSD"}


@register_source
class KrakenTickersSource(ProductSource):
    """USD spot tickers as volatile products with live prices and 24h ranges."""

    code: ClassVar[str] = "kraken_tickers"
    name: ClassVar[str] = "Kraken Tickers API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.kraken.com/0/public/Ticker"
    pairs_url: ClassVar[str] = "https://api.kraken.com/0/public/AssetPairs"
    terms_url: ClassVar[str] = "https://www.kraken.com/legal"
    license_note: ClassVar[str] = "Public market data, keyless; small batched budget."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "USD spot tickers as volatile products: live last-trade prices with "
        "24h high/low/open reference points."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        pairs = self._usd_pairs()
        if pairs is None:
            return
        emitted = 0
        for chunk in self._chunks(pairs[:limit], TICKER_BATCH):
            tickers = self._tickers(chunk)
            if tickers is None:
                continue
            for pair in chunk:
                raw = self._to_raw(pair, tickers.get(pair))
                if raw is None:
                    continue
                yield raw
                emitted += 1
                if emitted >= limit:
                    return

    def _usd_pairs(self) -> list[str] | None:
        """All online USD-quoted pairs, sorted for determinism."""
        self._count_request()
        try:
            payload = self.client.get_json(self.pairs_url)
        except Exception as exc:  # no pair list, no tickers
            self.errors.append(f"asset pairs: {exc}")
            return None
        result = self._result(payload, "asset pairs")
        if not isinstance(result, dict):
            return None
        pairs = sorted(
            name
            for name, meta in result.items()
            if isinstance(meta, dict)
            and meta.get("quote") in USD_QUOTES
            and meta.get("status") == "online"
        )
        return pairs or None

    def _tickers(self, pairs: list[str]) -> dict[str, Any] | None:
        self._count_request()
        try:
            payload = self.client.get_json(self.base_url, params={"pair": ",".join(pairs)})
        except Exception as exc:  # a failing batch must not kill the run
            self.errors.append(f"ticker batch: {exc}")
            return None
        result = self._result(payload, "ticker batch")
        return result if isinstance(result, dict) else None

    def _result(self, payload: Any, what: str) -> Any | None:
        if not isinstance(payload, dict):
            self.errors.append(f"{what}: unexpected response shape")
            return None
        errors = payload.get("error") or []
        if errors:
            self.errors.append(f"{what}: {errors[0] if errors else 'unknown error'}")
            return None
        return payload.get("result")

    def _to_raw(self, pair: str, ticker: Any) -> RawProduct | None:
        if not isinstance(ticker, dict):
            return None
        last = ticker.get("c") or []
        price = last[0] if isinstance(last, list) and last else None
        if price is None:
            return None
        name = pair.replace("XXBT", "XBT").replace("ZUSD", "/USD")
        high = (ticker.get("h") or [None, None])[1]
        low = (ticker.get("l") or [None, None])[1]
        opened = ticker.get("o")

        return RawProduct(
            source_code=self.code,
            source_product_id=pair,
            name=name,
            category="Cryptocurrency",
            price_text=str(price),
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=None,
            image_url=None,
            brand=None,
            description=None,
            payload={
                "pair": pair,
                "high_24h": high,
                "low_24h": low,
                "open_24h": opened,
            },
        )

    @staticmethod
    def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
        for at in range(0, len(items), size):
            yield items[at : at + size]
