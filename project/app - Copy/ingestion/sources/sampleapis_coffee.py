"""SampleAPIs coffee source (free sample-data API, no key required).

Endpoint: https://api.sampleapis.com/coffee/hot (+ /coffee/iced)
Terms:     https://sampleapis.com/ - sample data published for learning use;
           each menu is a single JSON array, so a run costs two HTTP calls.

Cafe drinks with descriptions, ingredient lists and images. No prices are
published, so rows land as assortment depth (category and brand coverage)
rather than price observations.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

MENUS = ("hot", "iced")


@register_source
class SampleApisCoffeeSource(ProductSource):
    """Cafe hot and iced drinks with ingredients and images."""

    code: ClassVar[str] = "sampleapis_coffee"
    name: ClassVar[str] = "SampleAPIs Coffee Menu"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.sampleapis.com/coffee/hot"
    terms_url: ClassVar[str] = "https://sampleapis.com/"
    license_note: ClassVar[str] = "Free sample data for learning use, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = "Cafe drinks: names, descriptions, ingredient lists and images."

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        seen: set[str] = set()

        for menu in MENUS:
            if emitted >= limit:
                return
            self._count_request()
            try:
                items = self.client.get_json(f"https://api.sampleapis.com/coffee/{menu}")
            except Exception as exc:  # a failing menu must not kill the run
                self.errors.append(f"menu {menu}: {exc}")
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                raw = self._to_raw(item, menu)
                if raw is None or raw.source_product_id in seen:
                    continue
                seen.add(raw.source_product_id)
                yield raw
                emitted += 1
                if emitted >= limit:
                    return

    def _to_raw(self, item: Any, menu: str) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        if not title:
            return None
        ingredients = item.get("ingredients") or []
        return RawProduct(
            source_code=self.code,
            source_product_id=f"{menu}-{item.get('id') or title}",
            name=str(title),
            category="Coffee & Tea",
            price_text=None,
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock",
            in_stock_flag=True,
            url=None,
            image_url=str(item.get("image") or "") or None,
            description=(
                f"{item.get('description', '')} Ingredients: {', '.join(map(str, ingredients))}."
                if ingredients
                else (str(item.get("description") or "") or None)
            ),
        )
