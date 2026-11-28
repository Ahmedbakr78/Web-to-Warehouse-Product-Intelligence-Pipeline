"""EscuelaJS (Platzi) Fake Store API source (free demo storefront, no key).

Endpoint: https://api.escuelajs.co/api/v1/products?offset=&limit=
Terms:    https://fakeapi.platzi.com/ - public demo storefront API for
          educational use; paged lazily with offset/limit.

Products carry numeric USD prices, a category object and an image list, which
exercises paged extraction plus category and image normalisation.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: Page size per request; the API honours ``offset`` + ``limit``.
PAGE_SIZE = 50


@register_source
class PlatziProductsSource(ProductSource):
    """Demo-store products with USD prices, categories and images (paged)."""

    code: ClassVar[str] = "platzi_products"
    name: ClassVar[str] = "Platzi Fake Store API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.escuelajs.co/api/v1/products"
    terms_url: ClassVar[str] = "https://fakeapi.platzi.com/"
    license_note: ClassVar[str] = "Public demo storefront API for educational use."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Demo-store catalogue with numeric USD prices, category objects and "
        "image lists, extracted lazily page by page."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        offset = 0
        emitted = 0
        while emitted < limit:
            page_size = min(PAGE_SIZE, limit - emitted)
            self._count_request()
            try:
                items = self.client.get_json(
                    self.base_url,
                    params={"offset": offset, "limit": page_size},
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"offset {offset}: {exc}")
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
            if len(items) < page_size:
                return
            offset += len(items)

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("title")
        if not name:
            return None
        category = item.get("category") or {}
        category_name = category.get("name") if isinstance(category, dict) else None
        images = item.get("images") or []
        image_url = images[0] if isinstance(images, list) and images else None
        price = item.get("price")

        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id")),
            name=str(name),
            category=str(category_name or "General").title(),
            price_text=str(price) if isinstance(price, (int, float)) else None,
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=f"https://api.escuelajs.co/api/v1/products/{item.get('id')}",
            image_url=str(image_url) if image_url else None,
            description=str(item.get("description") or "") or None,
            payload={"slug": item.get("slug"), "category_id": category.get("id") if isinstance(category, dict) else None},
        )
