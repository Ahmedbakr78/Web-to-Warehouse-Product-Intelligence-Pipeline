"""Makeup API source (free demo catalogue, no key).

Endpoint: https://makeup-api.herokuapp.com/api/v1/products.json?brand=&product_type=
Terms:    https://makeup-api.herokuapp.com/ - free demo API for educational
          use; a handful of brand/type combinations keeps the crawl small.

Beauty products with string prices, brand names, product-type categories and
0-5 ratings, which exercises brand normalisation plus nullable price/rating
handling (unpriced and unrated items are common upstream).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

#: (brand, product_type) combinations; one polite request per combination.
COMBOS: tuple[tuple[str, str], ...] = (
    ("maybelline", "lipstick"),
    ("loreal", "mascara"),
    ("covergirl", "foundation"),
    ("revlon", "blush"),
    ("maybelline", "eyeliner"),
    ("nyx", "eyeshadow"),
)


@register_source
class MakeupProductsSource(ProductSource):
    """Beauty products with string prices, brands and 0-5 ratings."""

    code: ClassVar[str] = "makeup_products"
    name: ClassVar[str] = "Makeup API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://makeup-api.herokuapp.com/api/v1/products.json"
    terms_url: ClassVar[str] = "https://makeup-api.herokuapp.com/"
    license_note: ClassVar[str] = "Free demo catalogue API for educational use."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Beauty products across a few brand/type combinations: string prices, "
        "brand names, product-type categories and 0-5 ratings."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        for brand, product_type in COMBOS:
            if emitted >= limit:
                return
            self._count_request()
            try:
                items = self.client.get_json(
                    self.base_url,
                    params={"brand": brand, "product_type": product_type},
                )
            except Exception as exc:  # a failing combo must not kill the run
                self.errors.append(f"{brand}/{product_type}: {exc}")
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                raw = self._to_raw(item)
                if raw is None:
                    continue
                yield raw
                emitted += 1
                if emitted >= limit:
                    return

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        if not name:
            return None
        rating = self._rating(item.get("rating"))
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id")),
            name=str(name),
            category=str(item.get("product_type") or "Beauty").replace("_", " ").title(),
            price_text=self._price(item.get("price")),
            currency_hint=str(item.get("currency") or self.default_currency).upper(),
            rating_text=f"{rating} out of 5" if rating is not None else None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=str(item.get("product_link") or "") or None,
            image_url=str(item.get("image_link") or "") or None,
            brand=str(item.get("brand") or "").title() or None,
            description=str(item.get("description") or "") or None,
            payload={
                "price_sign": item.get("price_sign"),
                "category": item.get("category"),
                "tag_list": item.get("tag_list"),
            },
        )

    @staticmethod
    def _price(value: Any) -> str | None:
        """Upstream prices are strings; blanks and zeroes mean 'unpriced'."""
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        return f"{amount:.2f}" if amount > 0 else None

    @staticmethod
    def _rating(value: Any) -> float | None:
        """Upstream ratings are 0-5 floats; 0 and null mean 'unrated'."""
        try:
            rating = float(value)
        except (TypeError, ValueError):
            return None
        return round(rating, 2) if 0 < rating <= 5 else None
