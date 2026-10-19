"""FreeAPI public products source (free demo e-commerce API, no key required).

Endpoint: https://api.freeapi.app/api/v1/public/randomproducts?page=1&limit=10
Terms:     https://api.freeapi.app/ - public demo endpoints for learning use;
           paged with page/limit over a 100-item catalogue.

Every product carries a numeric price, brand, category, rating, stock and a
discount percentage, so the cleaning stage derives genuine was/now pairs.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 25


@register_source
class FreeApiProductsSource(ProductSource):
    """Demo-store products with price, brand, category, rating and stock."""

    code: ClassVar[str] = "freeapi_products"
    name: ClassVar[str] = "FreeAPI Public Products"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.freeapi.app/api/v1/public/randomproducts"
    terms_url: ClassVar[str] = "https://api.freeapi.app/"
    license_note: ClassVar[str] = "Free public demo API, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Demo e-commerce catalogue: price, brand, category, rating, stock and discount percent per product."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 1
        seen: set[str] = set()

        while emitted < limit:
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={"page": page, "limit": min(PAGE_SIZE, limit - emitted)},
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            items = data.get("data") if isinstance(data, dict) else None
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
            if not data.get("nextPage"):
                return
            page += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        price = item.get("price")
        if not title or price is None:
            return None
        try:
            price_text = str(float(price))
        except (TypeError, ValueError):
            return None
        rating = item.get("rating")
        rating_text = str(float(rating)) if isinstance(rating, (int, float)) else None
        stock = item.get("stock")
        availability = "in_stock" if isinstance(stock, (int, float)) and stock > 0 else "unknown"
        images = item.get("images") or []
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or title),
            name=str(title),
            category=str(item.get("category") or "General"),
            brand=str(item.get("brand")) if item.get("brand") else None,
            price_text=price_text,
            currency_hint=self.default_currency,
            list_price_text=self._list_price(price, item.get("discountPercentage")),
            rating_text=rating_text,
            availability_text=availability,
            in_stock_flag=availability == "in_stock",
            url=None,
            image_url=str(item.get("thumbnail") or (images[0] if images else "") or "") or None,
            description=str(item.get("description") or "") or None,
        )

    @staticmethod
    def _list_price(price: Any, discount: Any) -> str | None:
        """Recover the pre-discount price so was/now pairs survive cleaning."""
        try:
            value = float(price)
            pct = float(discount)
        except (TypeError, ValueError):
            return None
        if not 0 < pct < 100:
            return None
        return f"{value / (1 - pct / 100):.2f}"
