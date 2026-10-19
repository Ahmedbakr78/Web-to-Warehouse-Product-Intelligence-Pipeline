"""Predic8 fruit-shop source (public demo shop API, no key required).

Endpoint: https://api.predic8.de/shop/v2/products/?start=1&limit=10
Terms:     https://www.predic8.de/ - demo shop for API training; the listing
           carries id/name links and each detail adds the euro price, vendors
           and an image link. No robots.txt is published (allowed by default).

A listing -> detail crawl over ~36 grocery lines: the euro price exercises
the FX normalisation path with a non-USD currency on every observation.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct, register_source

PAGE_SIZE = 10


@register_source
class Predic8GrocerySource(ProductSource):
    """Demo fruit-shop lines with euro prices, vendors and images."""

    code: ClassVar[str] = "predic8_grocery"
    name: ClassVar[str] = "Predic8 Fruit Shop"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://api.predic8.de/shop/v2/products/"
    terms_url: ClassVar[str] = "https://www.predic8.de/"
    license_note: ClassVar[str] = "Public demo shop API for training use, no key required."
    default_currency: ClassVar[str] = "EUR"
    rate_limit_per_minute: ClassVar[int] = 15
    min_delay_seconds: ClassVar[float] = 2.0
    supports_paging: ClassVar[bool] = True
    description: ClassVar[str] = "Demo grocery lines: euro price, unit, vendor list and image per product."

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        emitted = 0
        start = 1
        seen: set[str] = set()

        while emitted < limit:
            self._count_request()
            try:
                page = self.client.get_json(
                    self.base_url,
                    params={"start": start, "limit": min(PAGE_SIZE, limit - emitted)},
                )
            except Exception as exc:  # a failing page must not kill the run
                self.errors.append(f"start {start}: {exc}")
                return
            products = page.get("products") if isinstance(page, dict) else None
            if not isinstance(products, list) or not products:
                return
            for entry in products:
                raw = self._to_raw(entry)
                if raw is None or raw.source_product_id in seen:
                    continue
                seen.add(raw.source_product_id)
                yield raw
                emitted += 1
                if emitted >= limit:
                    return
            meta = page.get("meta", {}) if isinstance(page, dict) else {}
            if not meta.get("next_link"):
                return
            start += len(products)

    def _to_raw(self, entry: Any) -> RawProduct | None:
        if not isinstance(entry, dict):
            return None
        link = entry.get("self_link") or ""
        identifier = str(entry.get("id") or link.rsplit("/", 1)[-1] or "")
        name = entry.get("name")
        if not identifier or not name:
            return None
        detail = self._detail(link) if link.startswith("/") else {}
        price = detail.get("price")
        try:
            price_text = str(float(price)) if price is not None else None
        except (TypeError, ValueError):
            price_text = None
        vendors = detail.get("vendors") if isinstance(detail, dict) else None
        vendor_names = [str(vendor.get("name")) for vendor in vendors or [] if isinstance(vendor, dict)]
        image = (detail.get("image_link") or "") if isinstance(detail, dict) else ""
        return RawProduct(
            source_code=self.code,
            source_product_id=identifier,
            name=str(name),
            category="Grocery",
            price_text=price_text,
            currency_hint=self.default_currency,
            rating_text=None,
            availability_text="in_stock" if price_text else "unknown",
            in_stock_flag=bool(price_text),
            url=f"https://api.predic8.de{link}" if link.startswith("/") else None,
            image_url=f"https://api.predic8.de{image}" if image.startswith("/") else None,
            description=f"Vendors: {', '.join(vendor_names)}." if vendor_names else None,
        )

    def _detail(self, link: str) -> dict[str, Any]:
        """One detail call per listing row; failure keeps the row, not the run."""
        self._count_request()
        try:
            detail = self.client.get_json(f"https://api.predic8.de{link}")
        except Exception as exc:
            self.errors.append(f"detail {link}: {exc}")
            return {}
        return detail if isinstance(detail, dict) else {}
