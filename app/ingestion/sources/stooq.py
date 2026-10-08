"""Stooq equity-quotes source (currently BLOCKED - kept as a parser specification).

Endpoint: https://stooq.com/q/l/?s=aapl.us,msft.us&f=sd2t2ohlcv&h&e=csv
Terms:     https://stooq.com/db/ - free CSV quotes; one batched request covers
           the whole curated symbol list, so a run costs a single HTTP call.

BLOCKED as of 2026-10-08, verified three ways (see `terms_allowed = False`):

* ``/q/l/`` answers HTTP 404 for every symbol set tried, with and without a
  browser user agent - the live-quote endpoint is gone or gated;
* ``https://stooq.com/robots.txt`` says ``User-agent: *`` / ``Disallow: /``,
  so the compliant transport refuses both ``/q/l/`` and ``/db/``
  (``robots.txt:disallow`` through the app's own robots gate);
* ``/q/d/l/`` answers 200 but serves a JavaScript browser-verification wall
  instead of CSV, which a polite crawler must not attempt to defeat.

Compliance over coverage: the parser, the FX mapping and the offline tests
stay, so flipping one flag re-enables the source the day access is restored.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from typing import ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: Curated liquid US listings plus a few EU names; one batched request.
SYMBOLS: tuple[str, ...] = (
    "aapl.us",
    "msft.us",
    "nvda.us",
    "amzn.us",
    "goog.us",
    "meta.us",
    "tsla.us",
    "jpm.us",
    "jnj.us",
    "xom.us",
    "wmt.us",
    "pg.us",
    "ma.us",
    "dis.us",
    "nflx.us",
    "amd.us",
    "intc.us",
    "bac.us",
    "ko.us",
    "nep.us",
    "sap.de",
    "siemens.de",
    "nestle.ch",
    "asml.nl",
    "shell.uk",
)

COMPANY_NAMES: dict[str, str] = {
    "aapl.us": "Apple",
    "msft.us": "Microsoft",
    "nvda.us": "NVIDIA",
    "amzn.us": "Amazon",
    "goog.us": "Alphabet",
    "meta.us": "Meta Platforms",
    "tsla.us": "Tesla",
    "jpm.us": "JPMorgan Chase",
    "jnj.us": "Johnson & Johnson",
    "xom.us": "Exxon Mobil",
    "wmt.us": "Walmart",
    "pg.us": "Procter & Gamble",
    "ma.us": "Mastercard",
    "dis.us": "Disney",
    "nflx.us": "Netflix",
    "amd.us": "AMD",
    "intc.us": "Intel",
    "bac.us": "Bank of America",
    "ko.us": "Coca-Cola",
    "nep.us": "NextEra Energy",
    "sap.de": "SAP",
    "siemens.de": "Siemens",
    "nestle.ch": "Nestle",
    "asml.nl": "ASML",
    "shell.uk": "Shell",
}


@register_source
class StooqQuotesSource(ProductSource):
    """Listed equities with close/open/high/low session prices and volume."""

    code: ClassVar[str] = "stooq_quotes"
    name: ClassVar[str] = "Stooq Equity Quotes"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://stooq.com/q/l/"
    terms_url: ClassVar[str] = "https://stooq.com/db/"
    license_note: ClassVar[str] = (
        "BLOCKED 2026-10-08: /q/l/ 404s, robots.txt disallows all crawling, "
        "/q/d/l/ sits behind a JS verification wall. Parser kept as a spec."
    )
    #: False until Stooq restores anonymous CSV access - see the module docstring
    #: for the three verified reasons. The pipeline skips the source and the
    #: dashboard renders a "terms restricted" badge instead of an idle zero.
    terms_allowed: ClassVar[bool] = False
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 10
    min_delay_seconds: ClassVar[float] = 3.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Listed equities in one batched CSV request: session close/open/high/low "
        "prices and volume for US and EU names."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        symbols = list(SYMBOLS)[:limit]
        if not symbols:
            return
        self._count_request()
        try:
            response = self.client.get(
                self.base_url,
                params={"s": ",".join(symbols), "f": "sd2t2ohlcv", "h": "", "e": "csv"},
            )
            text = response.text if hasattr(response, "text") else ""
        except Exception as exc:  # without the batch there is nothing to do
            self.errors.append(f"batch quotes: {exc}")
            return
        emitted = 0
        for row in self._parse(text):
            if emitted >= limit:
                return
            raw = self._to_raw(row)
            if raw is None:
                continue
            yield raw
            emitted += 1

    @staticmethod
    def _parse(text: str) -> Iterator[dict[str, str]]:
        """Parse the Stooq CSV body (Symbol,Date,Time,Open,High,Low,Close,Volume)."""
        reader = csv.DictReader((text or "").splitlines())
        for row in reader or []:
            if isinstance(row, dict) and row.get("Symbol"):
                yield {key: (value or "").strip() for key, value in row.items() if key}

    def _to_raw(self, row: dict[str, str]) -> RawProduct | None:
        symbol = (row.get("Symbol") or "").lower()
        close = row.get("Close")
        if not symbol or not close or close.upper() == "N/D":
            return None
        company = COMPANY_NAMES.get(symbol, symbol.upper())
        exchange = symbol.split(".")[-1].upper() if "." in symbol else ""
        currency = {"DE": "EUR", "CH": "CHF", "NL": "EUR", "UK": "GBP"}.get(exchange, "USD")
        return RawProduct(
            source_code=self.code,
            source_product_id=symbol,
            name=f"{company} ({symbol.upper()})",
            category="Equities",
            price_text=close,
            currency_hint=currency,
            rating_text=None,
            availability_text="in_stock",  # a published quote implies a tradable listing
            in_stock_flag=True,
            url=None,
            image_url=None,
            brand=company,
            description=f"Session volume {row.get('Volume', '?')}.",
            payload={
                "exchange": exchange,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "volume": row.get("Volume"),
                "quote_date": row.get("Date"),
            },
        )
