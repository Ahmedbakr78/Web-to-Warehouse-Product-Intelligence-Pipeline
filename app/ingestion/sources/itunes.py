"""Apple iTunes Search API source for apps (free, no key, documented terms).

Endpoint: https://itunes.apple.com/search?term=<q>&media=software&entity=software
Terms:     https://performance-partners.apple.com/search-api - free catalog
           search API; one request per search term, up to 200 results each.

Apps carry real store prices with ISO currencies, genre categories, seller
brands and user ratings, which exercises price parsing, FX normalisation and
the rating leaderboard. A small set of everyday search terms keeps the
catalogue broad without hammering the endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: Everyday terms; each yields up to PAGE_SIZE apps in one request.
SEARCH_TERMS: tuple[str, ...] = (
    "photo editor",
    "fitness tracker",
    "password manager",
    "meditation",
    "budget planner",
)

PAGE_SIZE = 200


@register_source
class ITunesAppsSource(ProductSource):
    """App Store apps with real prices, genres, sellers and user ratings."""

    code: ClassVar[str] = "itunes_apps"
    name: ClassVar[str] = "iTunes Search Apps API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://itunes.apple.com/search"
    terms_url: ClassVar[str] = "https://performance-partners.apple.com/search-api"
    license_note: ClassVar[str] = "Free catalog search API, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "App Store apps across everyday search terms: store price and currency, "
        "genre, seller, user rating and artwork."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        seen: set[str] = set()

        for term in SEARCH_TERMS:
            if emitted >= limit:
                return
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={
                        "term": term,
                        "media": "software",
                        "entity": "software",
                        "country": "US",
                        "limit": min(PAGE_SIZE, limit - emitted),
                    },
                )
            except Exception as exc:  # a failing term must not kill the run
                self.errors.append(f"term {term!r}: {exc}")
                continue
            items = payload.get("results") if isinstance(payload, dict) else None
            if not items:
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
        name = item.get("trackName")
        if not name:
            return None
        price = item.get("price")
        rating = item.get("averageUserRating")
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("trackId") or item.get("bundleId") or name),
            name=str(name),
            category=str(item.get("primaryGenreName") or "Apps").title(),
            price_text=str(price) if isinstance(price, (int, float)) else None,
            currency_hint=str(item.get("currency") or self.default_currency),
            rating_text=f"{rating} out of 5" if isinstance(rating, (int, float)) else None,
            rating_count_text=str(item.get("userRatingCount")) if item.get("userRatingCount") else None,
            availability_text="in_stock",  # listed in the store catalogue
            in_stock_flag=True,
            url=item.get("trackViewUrl"),
            image_url=item.get("artworkUrl100") or item.get("artworkUrl60"),
            brand=str(item.get("sellerName") or item.get("artistName") or ""),
            description=str(item.get("description") or "")[:600] or None,
            payload={"bundle_id": item.get("bundleId"), "content_rating": item.get("contentAdvisoryRating")},
        )
