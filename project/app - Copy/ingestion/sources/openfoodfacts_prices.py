"""Open Food Facts "Open Prices" source (crowdsourced grocery prices, ODbl).

Endpoint: https://prices.openfoodfacts.org/api/v1/prices?size=100&order_by=-created
Terms:     https://prices.openfoodfacts.org/api/docs - open API, no key required,
           data under the Open Database License (ODbL, attribution respected).

Compliance notes
----------------
* ``prices.openfoodfacts.org`` is an API-first service: its ``/robots.txt``
  serves the SPA HTML shell with no parsable rules, i.e. an empty rule set
  (allow) per RFC 9309 semantics.
* ``world.openfoodfacts.org/robots.txt`` disallows ``/api`` on *that host*,
  so this source only ever calls the prices host and merely uses
  world.openfoodfacts.org product URLs as human-facing links (never fetched).
* A conservative budget is used anyway: ≤10 requests/minute, 2s minimum delay.

Each price row already joins the product (name, brand, image, categories) and
the store location. Only the newest observation per product is kept, so a run
yields distinct products with real multi-currency prices (EUR, USD, AUD, …)
that exercise FX normalisation; ``price_without_discount`` feeds the
list-price logic and the observed store goes into the raw payload.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 100
#: Hard cap on pages so one run never walks the whole 300k+ price history.
MAX_PAGES = 10


@register_source
class OpenFoodFactsPricesSource(ProductSource):
    """Crowdsourced grocery price observations with product and store joins."""

    code: ClassVar[str] = "openfoodfacts_prices"
    name: ClassVar[str] = "Open Food Facts Prices"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://prices.openfoodfacts.org/api/v1/prices"
    terms_url: ClassVar[str] = "https://prices.openfoodfacts.org/api/docs"
    license_note: ClassVar[str] = "Open Food Facts Open Prices - ODbL, attribution respected."
    default_currency: ClassVar[str] = "EUR"
    rate_limit_per_minute: ClassVar[int] = 10
    min_delay_seconds: ClassVar[float] = 2.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = (
        "Newest crowd-observed grocery prices: product name, brand, categories, "
        "image, discount pairs, currencies and the store/country of observation."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        seen: set[str] = set()
        emitted = 0
        page = 1

        while emitted < limit and page <= MAX_PAGES:
            self._count_request()
            try:
                payload = self.client.get_json(
                    self.base_url,
                    params={"size": PAGE_SIZE, "page": page, "order_by": "-created"},
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"page {page}: {exc}")
                return
            items = payload.get("items") if isinstance(payload, dict) else None
            if not items:
                return
            for item in items:
                if emitted >= limit:
                    return
                raw = self._to_raw(item)
                if raw is None or raw.source_product_id in seen:
                    continue
                seen.add(raw.source_product_id)
                yield raw
                emitted += 1
            page += 1

    def _to_raw(self, item: dict[str, Any]) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        product = item.get("product") or {}
        if not isinstance(product, dict):
            return None
        name = product.get("product_name")
        price = item.get("price")
        if not name or price is None:
            return None

        code = str(product.get("code") or item.get("product_id") or name)
        location = item.get("location") or {}
        categories = product.get("categories_tags") or []
        category = self._clean_tag(categories[0]) if isinstance(categories, list) and categories else None
        brands = str(product.get("brands") or "")
        brand = brands.split(",")[0].strip() if brands else None
        quantity = product.get("quantity")

        discounted = bool(item.get("price_is_discounted"))
        list_price = item.get("price_without_discount")
        description = self._describe(item, location, quantity)

        return RawProduct(
            source_code=self.code,
            source_product_id=code,
            name=str(name),
            category=category or "Groceries",
            price_text=str(price),
            currency_hint=str(item.get("currency") or self.default_currency),
            list_price_text=str(list_price) if discounted and list_price is not None else None,
            rating_text=None,
            rating_count_text=None,
            availability_text="in_stock",  # an observed shelf price implies stock
            in_stock_flag=True,
            url=f"https://world.openfoodfacts.org/product/{code}" if code.isdigit() else None,
            image_url=str(product.get("image_url") or ""),
            brand=brand or None,
            description=description,
            payload={
                "date": item.get("date"),
                "price_id": item.get("id"),
                "store": location.get("osm_name") if isinstance(location, dict) else None,
                "city": location.get("osm_address_city") if isinstance(location, dict) else None,
                "country": location.get("osm_address_country") if isinstance(location, dict) else None,
                "nutriscore": product.get("nutriscore_grade"),
            },
        )

    @staticmethod
    def _clean_tag(tag: Any) -> str:
        """``en:whole-milk`` / ``whole-milk`` -> ``Whole Milk``."""
        text = str(tag).split(":", 1)[-1].replace("-", " ").strip()
        return text.title() or "Groceries"

    @staticmethod
    def _describe(item: dict[str, Any], location: Any, quantity: Any) -> str | None:
        location = location if isinstance(location, dict) else {}
        store = location.get("osm_name")
        city = location.get("osm_address_city")
        country = location.get("osm_address_country")
        parts = [str(quantity)] if quantity else []
        observed = f"Observed {item.get('date')}" if item.get("date") else "Observed"
        where = ", ".join(part for part in (store, city, country) if part)
        text = f"{observed} at {where}" if where else observed
        return f"{' '.join(parts)} - {text}" if parts else text
