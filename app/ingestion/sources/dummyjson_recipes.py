"""DummyJSON recipes source (free, no key, same permitted host as products).

Endpoint: https://dummyjson.com/recipes?limit=N&skip=M (paged with skip)
Terms:     https://dummyjson.com/ - free test API for development.

Grocery-shelf depth: recipe names, images, ratings, review counts, tags and
meal types. Recipes carry no price, so they flow through as catalogue depth
while the completeness DQ rules record the missing prices honestly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 30

#: One run never walks the whole menu.
MAX_PAGES = 8


@register_source
class DummyJsonRecipesSource(ProductSource):
    """Recipes with images, ratings, tags and meal types."""

    code: ClassVar[str] = "dummyjson_recipes"
    name: ClassVar[str] = "DummyJSON Recipes API"
    kind: ClassVar[str] = "api"
    data_trust: ClassVar[str] = "synthetic"
    base_url: ClassVar[str] = "https://dummyjson.com/recipes"
    terms_url: ClassVar[str] = "https://dummyjson.com/"
    license_note: ClassVar[str] = "DummyJSON - free test API, same permitted host as products."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 0.5
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Recipes: name, image, rating, review counts, ingredients, tags and "
        "meal types, paged with skip/limit."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        page = 0

        while emitted < limit and page < MAX_PAGES:
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={"limit": min(PAGE_SIZE, limit - emitted), "skip": page * PAGE_SIZE},
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            items = payload.get("recipes") if isinstance(payload, dict) else None
            if not items:
                return
            for item in items:
                raw = self._to_raw(item)
                if raw is None:
                    continue
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
        name = item.get("name")
        if not name:
            return None
        meal_types = [m for m in (item.get("mealType") or []) if isinstance(m, str)]
        tags = [t for t in (item.get("tags") or []) if isinstance(t, str)]
        category = meal_types[0] if meal_types else "Grocery"
        ingredients = item.get("ingredients") or []
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or name),
            name=str(name),
            category=str(category).title(),
            price_text=None,  # recipes publish no price
            currency_hint=self.default_currency,
            rating_text=str(item.get("rating")) if item.get("rating") is not None else None,
            rating_count_text=str(item.get("reviewCount")) if item.get("reviewCount") is not None else None,
            availability_text=None,
            in_stock_flag=None,
            url=item.get("image") if isinstance(item.get("image"), str) else None,
            image_url=item.get("image") if isinstance(item.get("image"), str) else None,
            brand=None,
            description=(", ".join(str(i) for i in ingredients[:12]) if ingredients else None),
            payload={"tags": tags, "meal_types": meal_types, "cook_time": item.get("cookTimeMinutes")},
        )
