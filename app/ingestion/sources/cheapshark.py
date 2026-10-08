"""CheapShark deals API source (free public game-deals API, no key required).

Endpoint: https://www.cheapshark.com/api/1.0/deals?storeID=1&pageSize=60&pageNumber=0
Terms:     https://www.cheapshark.com/api/1.0/ - free API explicitly published
           for deal trackers; paged with pageNumber/pageSize.

Every deal carries both the sale price and the normal (list) price, so the
cleaning stage derives genuine discount pairs, plus a Steam rating percent
that is converted to the ``X out of 5`` text the rating parser understands.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: CheapShark caps pageSize at 60.
PAGE_SIZE = 60

#: Steam holds the largest deal catalogue; one store keeps results deterministic.
STORE_ID = 1
STORE_NAME = "Steam"


@register_source
class CheapSharkDealsSource(ProductSource):
    """Discounted Steam game deals with sale/list prices and Steam ratings."""

    code: ClassVar[str] = "cheapshark_deals"
    name: ClassVar[str] = "CheapShark Deals API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://www.cheapshark.com/api/1.0/deals"
    terms_url: ClassVar[str] = "https://www.cheapshark.com/api/1.0/"
    license_note: ClassVar[str] = "Free public deals API, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Steam game deals ordered by savings: sale price, normal price, "
        "discount percent and Steam rating for each title."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 0
        seen: set[str] = set()

        while emitted < limit:
            self._count_request()
            try:
                items = self.client.get_json(
                    self.base_url,
                    params={
                        "storeID": STORE_ID,
                        "pageSize": min(PAGE_SIZE, limit - emitted),
                        "pageNumber": page,
                        "sortBy": "Savings",
                        "desc": 1,
                        "onSale": 1,
                    },
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            if not isinstance(items, list) or not items:
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
            if len(items) < PAGE_SIZE:
                return
            page += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        sale = item.get("salePrice")
        if not title or sale is None:
            return None
        rating_text = self._rating_text(item.get("steamRatingPercent"))
        deal_id = item.get("dealID")
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("gameID") or deal_id or title),
            name=str(title),
            category="Video Games",
            price_text=str(sale),
            currency_hint=self.default_currency,
            list_price_text=str(item.get("normalPrice")) if item.get("normalPrice") is not None else None,
            rating_text=rating_text,
            rating_count_text=str(item.get("steamRatingCount")) if item.get("steamRatingCount") else None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=f"https://www.cheapshark.com/redirect?dealID={deal_id}" if deal_id else None,
            image_url=item.get("thumb"),
            brand=STORE_NAME,
            description=(
                f"Save {item.get('savings', '?')}% off the normal price at {STORE_NAME}."
                if item.get("savings") is not None
                else None
            ),
            payload={"deal_id": deal_id, "store_id": item.get("storeID")},
        )

    @staticmethod
    def _rating_text(percent: Any) -> str | None:
        """Steam's 0-100 percent -> the ``X out of 5`` text the parser reads."""
        try:
            value = float(percent)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return f"{value / 20:.2f} out of 5"
