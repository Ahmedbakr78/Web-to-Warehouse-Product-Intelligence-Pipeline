"""FakeStore API source (free demo API, no key, documented terms of use).

Endpoint: https://fakestoreapi.com/products
Notes:    Public *demo* API published for learning purposes; no personal data is
          processed and only product metadata is collected.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source


@register_source
class FakeStoreProductsSource(ProductSource):
    """Second JSON feed used to prove cross-source deduplication (same catalogue shape)."""

    code: ClassVar[str] = "fakestore_products"
    name: ClassVar[str] = "FakeStore Products API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://fakestoreapi.com/products"
    terms_url: ClassVar[str] = "https://fakestoreapi.com/"
    license_note: ClassVar[str] = "Public demo API for educational use."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "20 demo products with title, price, category, rating and description. "
        "Availability is not published, which exercises the completeness DQ rules."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        self._count_request()
        items = self.client.get_json(self.base_url)
        emitted = 0
        for item in items or []:
            if emitted >= limit:
                break
            yield self._to_raw(item)
            emitted += 1

    def _to_raw(self, item: dict[str, Any]) -> RawProduct:
        rating = item.get("rating")
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id")),
            name=item.get("title") or "",
            category=(item.get("category") or "").replace("-", " ").title(),
            price_text=str(item.get("price")) if item.get("price") is not None else None,
            currency_hint=self.default_currency,
            rating_text=f"{rating} out of 5" if rating is not None else None,
            availability_text=None,  # genuinely absent upstream -> DQ flag
            image_url=item.get("image"),
            description=item.get("description"),
            payload=item,
        )