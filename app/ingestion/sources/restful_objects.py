"""RESTful-API.dev objects source (free mock store API, no key required).

Endpoint: https://api.restful-api.dev/objects
Terms:     https://restful-api.dev/ - free mock API for testing; the whole
           catalogue arrives in one response, so a run costs a single request.

Objects are mostly consumer electronics with string or numeric detail fields.
Prices are sparse by design, which exercises the missing-price DQ path while
the priced rows contribute a further electronics vertical.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source


@register_source
class RestfulObjectsSource(ProductSource):
    """Mock-store electronics with sparse prices, colors and capacities."""

    code: ClassVar[str] = "restful_objects"
    name: ClassVar[str] = "RESTful API Objects"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.restful-api.dev/objects"
    terms_url: ClassVar[str] = "https://restful-api.dev/"
    license_note: ClassVar[str] = "Free mock API for testing, no key required."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Mock-store electronics in a single response: names with detail "
        "fields and sparse prices for the missing-price DQ path."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        self._count_request()
        try:
            items = self.client.get_json(self.base_url)
        except Exception as exc:  # without the catalogue there is nothing to do
            self.errors.append(f"catalogue: {exc}")
            return
        if not isinstance(items, list):
            self.errors.append("catalogue: unexpected response shape")
            return
        emitted = 0
        for item in items:
            if emitted >= limit:
                return
            raw = self._to_raw(item)
            if raw is None:
                continue
            yield raw
            emitted += 1

    def _to_raw(self, item: Any) -> RawProduct | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        if not name:
            return None
        details = item.get("data") if isinstance(item.get("data"), dict) else {}
        price = self._price(details.get("price"))
        color = details.get("color") or details.get("Color")
        capacity = details.get("capacity") or details.get("Capacity")
        brand = details.get("brand")
        blurb = ", ".join(
            part for part in (str(color) if color else "", str(capacity) if capacity else "") if part
        )
        return RawProduct(
            source_code=self.code,
            source_product_id=str(item.get("id") or name),
            name=str(name),
            category="Electronics",
            price_text=str(price) if price is not None else None,
            currency_hint=self.default_currency,
            rating_text=None,
            rating_count_text=None,
            availability_text=None,  # genuinely absent upstream -> DQ flag
            in_stock_flag=None,
            url=None,
            image_url=None,
            brand=str(brand) if brand else None,
            description=blurb or None,
            payload={"details": details},
        )

    @staticmethod
    def _price(value: Any) -> float | None:
        """Accept numerics and numeric strings; anything else means no price."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value) if value > 0 else None
        if isinstance(value, str):
            cleaned = "".join(ch for ch in value if ch.isdigit() or ch in ".,").replace(",", "")
            try:
                amount = float(cleaned) if cleaned else 0.0
            except ValueError:
                return None
            return amount if amount > 0 else None
        return None
