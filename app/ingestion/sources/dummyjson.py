"""DummyJSON Products API source (free, no API key, public documentation).

Endpoint: https://dummyjson.com/products?limit=100&skip=0
Terms:     https://dummyjson.com/ - free public test API intended for prototyping.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 100


@register_source
class DummyJsonProductsSource(ProductSource):
    """Structured JSON product feed with price, category, rating, stock and brand."""

    code: ClassVar[str] = "dummyjson_products"
    name: ClassVar[str] = "DummyJSON Products API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://dummyjson.com/products"
    terms_url: ClassVar[str] = "https://dummyjson.com/"
    license_note: ClassVar[str] = "Public test API, no key required, attribution appreciated."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 60
    min_delay_seconds: ClassVar[float] = 0.4
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "30 products per page with price, discount, rating, stock level, brand and "
        "thumbnail. Ideal for validating the pipeline end to end."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        skip = 0
        total = None

        while emitted < limit:
            page = min(PAGE_SIZE, limit - emitted)
            self._count_request()
            payload = self.client.get_json(self.base_url, params={"limit": page, "skip": skip})
            products: list[dict[str, Any]] = payload.get("products") or []
            if total is None:
                total = int(payload.get("total") or 0)
            if not products:
                break
            for item in products:
                yield self._to_raw(item)
                emitted += 1
                if emitted >= limit:
                    break
            skip += len(products)
            if total and skip >= total:
                break

    def _to_raw(self, item: dict[str, Any]) -> RawProduct:
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or item.get("sku") or item.get("title")),
            name=item.get("title") or item.get("name") or "",
            category=(item.get("category") or "").replace("-", " ").title(),
            price_text=str(item.get("price")) if item.get("price") is not None else None,
            currency_hint=self.default_currency,
            list_price_text=(str(item.get("discountPrice")) if item.get("discountPrice") else None),
            rating_text=str(item.get("rating")) if item.get("rating") is not None else None,
            rating_count_text=str(item.get("stock")) if item.get("stock") is not None else None,
            availability_text="in_stock" if item.get("stock", 0) else "out_of_stock",
            in_stock_flag=bool(item.get("stock", 0)),
            url=item.get("url") or item.get("images", [None])[0],
            image_url=item.get("thumbnail"),
            brand=item.get("brand"),
            description=item.get("description"),
            payload=item,
        )
