"""TheCocktailDB drinks source (free drinks API, no key required).

Endpoint: https://www.thecocktaildb.com/api/json/v1/1/filter.php?a=Alcoholic
Terms:     https://www.thecocktaildb.com/ - free API for development use;
           three filter calls (alcoholic, non-alcoholic, optional alcohol)
           cover the whole menu without per-drink lookups.

Drinks with photos across the three alcohol options. No prices are published,
so rows land as beverage-vertical depth next to the coffee feed.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

ALCOHOL_OPTIONS = ("Alcoholic", "Non_Alcoholic", "Optional_Alcohol")


@register_source
class CocktailDbDrinksSource(ProductSource):
    """Drinks by alcohol option with photos."""

    code: ClassVar[str] = "cocktaildb_drinks"
    name: ClassVar[str] = "TheCocktailDB Drinks"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://www.thecocktaildb.com/api/json/v1/1/filter.php"
    terms_url: ClassVar[str] = "https://www.thecocktaildb.com/"
    license_note: ClassVar[str] = "Free API for development use, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 15
    min_delay_seconds: ClassVar[float] = 2.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = "Drinks across alcohol options: names and photos per drink."

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        seen: set[str] = set()
        for option in ALCOHOL_OPTIONS:
            if emitted >= limit:
                return
            self._count_request()
            try:
                payload = self.client.get_json(self.base_url, params={"a": option})
            except Exception as exc:  # a failing option must not kill the run
                self.errors.append(f"option {option}: {exc}")
                continue
            drinks = payload.get("drinks") if isinstance(payload, dict) else None
            if not isinstance(drinks, list):
                continue
            for drink in drinks:
                raw = self._to_raw(drink, option)
                if raw is None or raw.source_product_id in seen:
                    continue
                seen.add(raw.source_product_id)
                yield raw
                emitted += 1
                if emitted >= limit:
                    return

    def _to_raw(self, drink: Any, option: str) -> RawProduct | None:
        if not isinstance(drink, dict):
            return None
        name = drink.get("strDrink")
        if not name:
            return None
        return RawProduct(
            source_code=self.code,
            source_product_id=str(drink.get("idDrink") or name),
            name=str(name),
            category="Beverages",
            price_text=None,
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=None,
            image_url=str(drink.get("strDrinkThumb") or "") or None,
            description=f"CocktailDB {option.replace('_', ' ').lower()} drink.",
        )
