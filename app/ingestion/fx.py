"""Live foreign-exchange rates.

Every ``price_usd`` in the warehouse is the result of a conversion, so the
conversion rate is part of the fact. Deriving it from a frozen table that was
hand-written once makes the whole USD column wrong by the same margin for
ever - a 5 % move in EUR would never show up in a price comparison.

This module fetches the current rates from a free, key-less provider and keeps
them fresh:

* ``https://open.er-api.com/v6/latest/USD`` - daily, no key, broad coverage.
* ``https://api.frankfurter.dev/v1/latest?base=USD`` - fallback, ECB reference
  rates.

The rates are cached in memory for a short window and mirrored into
``dim_currency`` so a run records where its numbers came from and when
(``rate_source`` / ``as_of``). If the providers are unreachable the module
falls back to the last known table, and says so - it never silently invents a
rate.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any

from app.core.logging import get_logger
from app.ingestion.cleaning import STATIC_FX_RATES

log = get_logger(__name__)

#: How long a fetched rate set stays fresh before the next fetch is attempted.
RATE_TTL_SECONDS = 6 * 60 * 60

#: Providers in preference order. Each entry is (name, url, parser name).
PROVIDERS: tuple[tuple[str, str, str], ...] = (
    ("exchangerate-api.com", "https://open.er-api.com/v6/latest/USD", "er_api"),
    ("frankfurter.dev", "https://api.frankfurter.dev/v1/latest?base=USD", "frankfurter"),
)

_lock = threading.Lock()
_cache: dict[str, float] = {}
_cache_meta: dict[str, Any] = {"source": "static_reference_table", "as_of": None, "fetched_at": 0.0}


def _parse_er_api(payload: dict[str, Any]) -> dict[str, float]:
    """``{"base_code": "USD", "rates": {"EUR": 0.89, ...}}`` -> rate *to* USD."""
    rates = payload.get("rates") or {}
    parsed: dict[str, float] = {}
    for code, value in rates.items():
        try:
            per_usd = float(value)
        except (TypeError, ValueError):
            continue
        if per_usd <= 0:
            continue
        parsed[str(code).upper()] = 1.0 / per_usd
    return parsed


def _parse_frankfurter(payload: dict[str, Any]) -> dict[str, float]:
    """``{"base": "USD", "rates": {"EUR": 0.89, ...}}`` -> rate *to* USD."""
    rates = payload.get("rates") or {}
    parsed: dict[str, float] = {}
    for code, value in rates.items():
        try:
            per_usd = float(value)
        except (TypeError, ValueError):
            continue
        if per_usd <= 0:
            continue
        parsed[str(code).upper()] = 1.0 / per_usd
    return parsed


_PARSERS = {"er_api": _parse_er_api, "frankfurter": _parse_frankfurter}


def fetch_rates(*, timeout: float = 10.0) -> tuple[dict[str, float], str, dt.date | None]:
    """Fetch the current rates. Returns ``(rates, provider, as_of)``.

    Raises the last error if every provider fails, so the caller can decide
    whether to fall back to the cached table.
    """
    import httpx

    last_error: Exception | None = None
    for name, url, parser in PROVIDERS:
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - any provider failure falls through
            last_error = exc
            log.debug("fx provider %s failed: %s", name, exc)
            continue
        rates = _PARSERS[parser](payload)
        if not rates:
            last_error = ValueError(f"provider {name} returned no usable rates")
            continue
        as_of: dt.date | None = None
        raw_date = payload.get("date") or payload.get("time_last_update_utc")
        if isinstance(raw_date, str):
            try:
                as_of = dt.date.fromisoformat(raw_date[:10])
            except ValueError:
                as_of = None
        if as_of is None:
            as_of = dt.date.today()
        rates["USD"] = 1.0
        return rates, name, as_of
    raise RuntimeError(f"no FX provider reachable: {last_error}")


def refresh(*, force: bool = False) -> dict[str, Any]:
    """Refresh the in-memory rate table from a live provider.

    Returns metadata about the table now in use. On failure the previous table
    is kept and ``source`` reports where those numbers came from.
    """
    global _cache, _cache_meta
    with _lock:
        fresh = time.time() - float(_cache_meta.get("fetched_at") or 0.0)
        if not force and _cache and fresh < RATE_TTL_SECONDS:
            return dict(_cache_meta)
        try:
            rates, provider, as_of = fetch_rates()
        except Exception as exc:  # noqa: BLE001 - the pipeline must not die on FX
            log.warning("live FX refresh failed (%s); keeping the previous rate table", exc)
            meta = dict(_cache_meta)
            meta["stale"] = True
            meta["error"] = str(exc)
            return meta
        _cache = rates
        _cache_meta = {
            "source": provider,
            "as_of": as_of.isoformat() if as_of else None,
            "fetched_at": time.time(),
            "stale": False,
        }
        log.info("FX rates refreshed from %s (%d currencies)", provider, len(rates))
        return dict(_cache_meta)


def current_rates() -> dict[str, float]:
    """The rate table to use right now: live when reachable, else the fallback."""
    if not _cache:
        refresh()
    if _cache:
        return _cache
    return dict(STATIC_FX_RATES)


def rate_metadata() -> dict[str, Any]:
    """Where the rate table came from and how old it is."""
    meta = dict(_cache_meta)
    if not _cache:
        meta.setdefault("source", "static_reference_table")
        meta.setdefault("stale", True)
    return meta


def rate_to_usd(currency: str | None) -> tuple[float, str]:
    """The USD rate for one currency, plus the source of that rate."""
    code = (currency or "USD").upper()
    rates = current_rates()
    rate = rates.get(code)
    if rate is None:
        rate = STATIC_FX_RATES.get(code)
        if rate is None:
            return 1.0, "identity"
        return rate, "static_reference_table"
    return rate, str(_cache_meta.get("source") or "live")


__all__ = [
    "RATE_TTL_SECONDS",
    "PROVIDERS",
    "current_rates",
    "fetch_rates",
    "rate_metadata",
    "rate_to_usd",
    "refresh",
]
