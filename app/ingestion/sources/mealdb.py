"""TheMealDB meals source (free recipe API, no key required).

Endpoint: https://www.themealdb.com/api/json/v1/1/filter.php?c=Seafood
Terms:     https://www.themealdb.com/ - free API for development use;
           robots.txt explicitly allows crawling. Categories come from
           list.php?c=list, then one filter call per category.

Meals with photos across ~14 food categories. No prices are published, so
rows land as food-vertical depth next to the priced grocery feeds.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source


@register_source
class MealDbMealsSource(ProductSource):
    """Meals by food category with photos."""

    code: ClassVar[str] = "mealdb_meals"
    name: ClassVar[str] = "TheMealDB Meals"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://www.themealdb.com/api/json/v1/1/filter.php"
    terms_url: ClassVar[str] = "https://www.themealdb.com/"
    license_note: ClassVar[str] = "Free API for development use, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 15
    min_delay_seconds: ClassVar[float] = 2.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = "Meals across food categories: names and photos per dish."

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        categories = self._categories()
        if not categories:
            return
        emitted = 0
        seen: set[str] = set()
        for category in categories:
            if emitted >= limit:
                return
            self._count_request()
            try:
                payload = self.client.get_json(self.base_url, params={"c": category})
            except Exception as exc:  # a failing category must not kill the run
                self.errors.append(f"category {category}: {exc}")
                continue
            meals = payload.get("meals") if isinstance(payload, dict) else None
            if not isinstance(meals, list):
                continue
            for meal in meals:
                raw = self._to_raw(meal, category)
                if raw is None or raw.source_product_id in seen:
                    continue
                seen.add(raw.source_product_id)
                yield raw
                emitted += 1
                if emitted >= limit:
                    return

    def _categories(self) -> list[str]:
        """Category list first, so new food categories are picked up for free."""
        self._count_request()
        try:
            payload = self.client.get_json(
                "https://www.themealdb.com/api/json/v1/1/list.php", params={"c": "list"}
            )
        except Exception as exc:
            self.errors.append(f"categories: {exc}")
            return []
        meals = payload.get("meals") if isinstance(payload, dict) else None
        if not isinstance(meals, list):
            return []
        return [
            str(meal.get("strCategory"))
            for meal in meals
            if isinstance(meal, dict) and meal.get("strCategory")
        ]

    def _to_raw(self, meal: Any, category: str) -> RawProduct | None:
        if not isinstance(meal, dict):
            return None
        name = meal.get("strMeal")
        if not name:
            return None
        return RawProduct(
            source_code=self.code,
            source_product_id=str(meal.get("idMeal") or name),
            name=str(name),
            category="Food",
            price_text=None,
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=None,
            image_url=str(meal.get("strMealThumb") or "") or None,
            description=f"MealDB {category} dish." if category else None,
        )
