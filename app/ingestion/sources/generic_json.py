"""Generic JSON product source, defined at runtime instead of in code.

This is what powers *Add source* in the dashboard: a ``dim_source`` row whose
``config`` carries ``adapter: "generic_json"`` materialises as this class, so a
new JSON API or a Shopify ``products.json`` endpoint can be onboarded without a
deploy. Code-defined sources (DummyJSON, FakeStore, ...) stay exactly as they
are; this adapter only handles rows created through ``POST /sources``.

Configuration schema (stored in ``dim_source.config``)::

    {
        "adapter": "generic_json",
        "items_path": "products",      # dot path to the list; "" = the root itself
        "id_field": "id",              # dot path to a stable identifier
        "fields": {                    # dot paths; "const:X" pins a literal
            "name": "title",
            "price": "price",
            "category": "category",
            ...
        },
        "pagination": {
            "style": "none" | "skip_limit" | "page_number",
            "page_size": 100,
            "limit_param": "limit", "offset_param": "skip",
            "page_param": "page", "per_page_param": "per_page",
            "total_path": "total", "max_pages": 20,
        },
        "params": {"q": "shoes"},       # extra query parameters per request
        "url_template": "{origin}/products/{handle}",
        "currency": "USD",
    }

Paths support ``[N]`` indices (``variants.0.price``). Values travel as text;
the cleaning stage parses prices, ratings and availability exactly as it does
for code-defined sources.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, ClassVar
from urllib.parse import urlparse

from app.core.config import settings
from app.ingestion.base import ProductSource, RawProduct

#: Marker stored in ``dim_source.config`` distinguishing GUI-created rows.
ADAPTER_NAME = "generic_json"

#: Pagination styles the adapter understands.
PAGINATION_STYLES = ("none", "skip_limit", "page_number")

_MISSING: Any = object()

_SEGMENT = re.compile(r"^([^\[\]]+)(?:\[(\d+)\])?$")


def get_path(data: Any, path: str | None) -> Any:
    """Resolve ``a.b.0.c`` against nested dicts/lists; ``_MISSING`` when absent.

    An empty path returns the document itself, which is how root-array feeds
    (FakeStore, Shopify) are addressed. ``const:X`` pins the literal ``X``.
    """
    if path is None:
        return _MISSING
    if isinstance(path, str) and path.startswith("const:"):
        return path[len("const:") :]
    if path == "":
        return data
    current = data
    for segment in str(path).split("."):
        match = _SEGMENT.match(segment)
        if not match:
            return _MISSING
        key, index = match.group(1), match.group(2)
        if isinstance(current, dict):
            if key not in current:
                return _MISSING
            current = current[key]
        elif isinstance(current, (list, tuple)) and key.isdigit() and int(key) < len(current):
            # Bare numeric segments index into lists, so both "variants.0.price"
            # and "variants[0].price" address the first variant.
            current = current[int(key)]
        else:
            return _MISSING
        if index is not None:
            if not isinstance(current, (list, tuple)) or int(index) >= len(current):
                return _MISSING
            current = current[int(index)]
    return current


def _flatten(item: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten one item so ``{variants.0.price}`` works in URL templates."""
    flat: dict[str, Any] = {}
    if isinstance(item, dict):
        for key, value in item.items():
            flat[f"{prefix}{key}" if prefix else str(key)] = (
                value if not isinstance(value, (dict, list)) else value
            )
            if isinstance(value, dict):
                flat.update(_flatten(value, f"{prefix}{key}." if prefix else f"{key}."))
            elif isinstance(value, list):
                for pos, entry in enumerate(value):
                    base = f"{prefix}{key}.{pos}" if prefix else f"{key}.{pos}"
                    flat[base] = entry
                    if isinstance(entry, dict):
                        flat.update(_flatten(entry, f"{base}."))
    return flat


def _origin(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else base_url.rstrip("/")


def _coerce_availability(value: Any) -> tuple[str | None, bool | None]:
    """Normalise booleans and stock counts before the text cleaners see them."""
    if isinstance(value, bool):
        return ("in_stock" if value else "out_of_stock", value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ("in_stock" if value > 0 else "out_of_stock", bool(value > 0))
    if value is None:
        return None, None
    return str(value), None


#: Ready-made mappings for well-known free endpoints, served to the dashboard
#: as ``GET /sources/presets`` so the form is one click for common cases.
PRESETS: dict[str, dict[str, Any]] = {
    "dummyjson": {
        "label": "DummyJSON Products",
        "base_url": "https://dummyjson.com/products",
        "terms_url": "https://dummyjson.com/",
        "license_note": "Public test API, no key required.",
        "items_path": "products",
        "id_field": "id",
        "fields": {
            "name": "title",
            "price": "price",
            "category": "category",
            "rating": "rating",
            "rating_count": "stock",
            "availability": "stock",
            "brand": "brand",
            "description": "description",
            "image": "thumbnail",
        },
        "pagination": {
            "style": "skip_limit",
            "page_size": 100,
            "limit_param": "limit",
            "offset_param": "skip",
            "total_path": "total",
        },
    },
    "fakestore": {
        "label": "FakeStore API",
        "base_url": "https://fakestoreapi.com/products",
        "terms_url": "https://fakestoreapi.com/",
        "license_note": "Free mock e-commerce API.",
        "items_path": "",
        "id_field": "id",
        "fields": {
            "name": "title",
            "price": "price",
            "category": "category",
            "rating": "rating.rate",
            "rating_count": "rating.count",
            "description": "description",
            "image": "image",
        },
        "pagination": {"style": "none"},
    },
    "shopify": {
        "label": "Shopify store (products.json)",
        "base_url": "https://<store>.myshopify.com/products.json",
        "terms_url": None,
        "license_note": "Public storefront endpoint; verify the store's robots.txt and terms first.",
        "items_path": "products",
        "id_field": "id",
        "fields": {
            "name": "title",
            "price": "variants.0.price",
            "category": "product_type",
            "brand": "vendor",
            "description": "body_html",
            "image": "images.0.src",
            "availability": "const:in_stock",
        },
        "url_template": "{origin}/products/{handle}",
        "pagination": {"style": "none"},
    },
    "openfoodfacts": {
        "label": "Open Food Facts",
        "base_url": "https://world.openfoodfacts.org/cgi/search.pl",
        "terms_url": "https://world.openfoodfacts.org/terms-of-use",
        "license_note": "Open data (ODbL); attribution required.",
        "items_path": "products",
        "id_field": "code",
        "fields": {
            "name": "product_name",
            "category": "categories",
            "brand": "brands",
            "image": "image_url",
            "availability": "const:in_stock",
        },
        "pagination": {
            "style": "page_number",
            "page_size": 100,
            "page_param": "page",
            "per_page_param": "page_size",
            "total_path": "count",
        },
        "params": {"search_terms": "", "json": "1"},
    },
    "openlibrary": {
        "label": "Open Library shelf",
        "base_url": "https://openlibrary.org/subjects/bestsellers.json",
        "terms_url": "https://openlibrary.org/terms-of-use",
        "license_note": "Free public API; be polite (≤100 req/5min). Note: /search.json is robots-blocked, shelves are allowed.",
        "items_path": "works",
        "id_field": "key",
        "fields": {
            "name": "title",
            "brand": "authors.0.name",
        },
        "pagination": {"style": "none"},
        "params": {"limit": "100"},
    },
}


class GenericJsonSource(ProductSource):
    """A JSON feed whose shape is described by data, not by a subclass."""

    kind: ClassVar[str] = "api"
    supports_paging: ClassVar[bool] = True

    def __init__(
        self,
        definition: dict[str, Any],
        run_id: str | None = None,
        client: Any | None = None,
    ) -> None:
        super().__init__(run_id=run_id, client=client)
        config = dict(definition.get("config") or {})
        # Base declares these as ClassVar (registry sources set them on the
        # class); a runtime-defined source sets them per instance instead. A
        # single setattr loop keeps mypy's ClassVar rules satisfied without a
        # dozen ignores, and reads still type-check against the base declares.
        values: dict[str, Any] = {
            "code": str(definition.get("code") or definition.get("source_code") or ""),
            "name": str(definition.get("name") or ""),
            "base_url": str(definition.get("base_url") or ""),
            "terms_url": definition.get("terms_url"),
            "license_note": definition.get("license_note"),
            "description": str(definition.get("description") or ""),
            "default_currency": str(definition.get("currency") or config.get("currency") or "USD"),
            "rate_limit_per_minute": int(definition.get("rate_limit_per_minute") or 30),
            "min_delay_seconds": float(definition.get("min_delay_seconds") or 1.0),
            "enabled": bool(definition.get("enabled", True)),
            "terms_allowed": bool(definition.get("terms_allowed", False)),
        }
        if not values["name"]:
            values["name"] = values["code"]
        if not values["description"]:
            values["description"] = f"Dashboard-defined JSON feed ({values['code']})."
        for key, value in values.items():
            setattr(self, key, value)
        self.items_path = str(config.get("items_path", "products"))
        self.id_field = str(config.get("id_field", "id"))
        self.fields: dict[str, str] = dict(config.get("fields") or {"name": "title"})
        pagination = dict(config.get("pagination") or {"style": "none"})
        if pagination.get("style") not in PAGINATION_STYLES:
            pagination["style"] = "none"
        self.pagination = pagination
        self.extra_params: dict[str, Any] = dict(config.get("params") or {})
        self.url_template: str | None = config.get("url_template")

    @classmethod
    def from_row(cls, row: Any, run_id: str | None = None, client: Any | None = None) -> GenericJsonSource:
        """Materialise a ``dim_source`` row (columns + ``config`` JSON)."""
        return cls(
            {
                "code": row.source_code,
                "name": row.name,
                "base_url": row.base_url,
                "terms_url": row.terms_url,
                "license_note": row.license_note,
                "currency": (row.config or {}).get("currency", "USD"),
                "rate_limit_per_minute": row.rate_limit_per_minute,
                "min_delay_seconds": row.min_delay_seconds,
                "enabled": row.enabled,
                "terms_allowed": row.terms_allowed,
                "description": f"Dashboard-defined JSON feed ({row.source_code}).",
                "config": row.config or {},
            },
            run_id=run_id,
            client=client,
        )

    def definition(self) -> dict[str, Any]:
        """Round-trip back to the ``dim_source.config`` shape the UI edits."""
        return {
            "adapter": ADAPTER_NAME,
            "items_path": self.items_path,
            "id_field": self.id_field,
            "fields": dict(self.fields),
            "pagination": dict(self.pagination),
            "params": dict(self.extra_params),
            **({"url_template": self.url_template} if self.url_template else {}),
            "currency": self.default_currency,
        }

    # ------------------------------------------------------------------ fetch
    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        style = self.pagination.get("style", "none")
        if style == "none":
            yield from self._fetch_page(limit, params=dict(self.extra_params))
        elif style == "skip_limit":
            yield from self._fetch_skip_limit(limit)
        else:
            yield from self._fetch_pages(limit)

    def _fetch_page(self, limit: int, params: dict[str, Any]) -> Iterator[RawProduct]:
        self._count_request()
        payload = self.client.get_json(self.base_url, params=params or None)
        items = get_path(payload, self.items_path)
        if items is _MISSING:
            self.errors.append(f"items_path '{self.items_path}' not found in response")
            return
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            self.errors.append(f"items_path '{self.items_path}' did not resolve to a list")
            return
        for item in items[:limit]:
            if isinstance(item, dict):
                yield self._to_raw(item)

    def _fetch_skip_limit(self, limit: int) -> Iterator[RawProduct]:
        pagination = self.pagination
        page_size = min(int(pagination.get("page_size") or 100), 500)
        limit_param = pagination.get("limit_param") or "limit"
        offset_param = pagination.get("offset_param") or "skip"
        total_path = pagination.get("total_path")
        max_pages = int(pagination.get("max_pages") or 20)
        emitted = skip = 0
        total: int | None = None
        for _ in range(max_pages):
            if emitted >= limit:
                break
            self._count_request()
            params = {**self.extra_params, limit_param: min(page_size, limit - emitted), offset_param: skip}
            payload = self.client.get_json(self.base_url, params=params)
            if total is None and total_path:
                try:
                    total = int(get_path(payload, total_path) or 0)
                except (TypeError, ValueError):
                    total = None
            items = get_path(payload, self.items_path)
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                yield self._to_raw(item)
                emitted += 1
                if emitted >= limit:
                    break
            skip += len(items)
            if total and skip >= total:
                break

    def _fetch_pages(self, limit: int) -> Iterator[RawProduct]:
        pagination = self.pagination
        page_size = min(int(pagination.get("page_size") or 100), 500)
        page_param = pagination.get("page_param") or "page"
        per_page_param = pagination.get("per_page_param") or "per_page"
        total_path = pagination.get("total_path")
        max_pages = int(pagination.get("max_pages") or 20)
        emitted = 0
        total: int | None = None
        for page in range(1, max_pages + 1):
            if emitted >= limit:
                break
            self._count_request()
            params = {**self.extra_params, page_param: page, per_page_param: min(page_size, limit - emitted)}
            payload = self.client.get_json(self.base_url, params=params)
            if total is None and total_path:
                try:
                    total = int(get_path(payload, total_path) or 0)
                except (TypeError, ValueError):
                    total = None
            items = get_path(payload, self.items_path)
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                yield self._to_raw(item)
                emitted += 1
                if emitted >= limit:
                    break
            if total and page * page_size >= total:
                break

    # ------------------------------------------------------------------ mapping
    def _field(self, item: dict[str, Any], key: str) -> Any:
        value = get_path(item, self.fields.get(key))
        return None if value is _MISSING else value

    def _to_raw(self, item: dict[str, Any]) -> RawProduct:
        raw_id = get_path(item, self.id_field)
        name = self._field(item, "name") or ""
        availability, in_stock = _coerce_availability(self._field(item, "availability"))
        price = self._field(item, "price")
        list_price = self._field(item, "list_price")
        rating = self._field(item, "rating")
        rating_count = self._field(item, "rating_count")
        url = self._field(item, "url") or self._render_url(item)
        return RawProduct(
            source_code=self.code,
            source_product_id=str(raw_id if raw_id not in (None, "") else name),
            name=str(name),
            category=self._optional_text(self._field(item, "category")),
            price_text=str(price) if price is not None else None,
            currency_hint=self.default_currency,
            list_price_text=str(list_price) if list_price is not None else None,
            rating_text=str(rating) if rating is not None else None,
            rating_count_text=str(rating_count) if rating_count is not None else None,
            availability_text=availability,
            in_stock_flag=in_stock,
            url=url,
            image_url=self._optional_text(self._field(item, "image")),
            brand=self._optional_text(self._field(item, "brand")),
            description=self._optional_text(self._field(item, "description")),
            payload=item,
        )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _render_url(self, item: dict[str, Any]) -> str | None:
        if not self.url_template:
            return None
        try:
            return self.url_template.format(origin=_origin(self.base_url), **_flatten(item))
        except (KeyError, IndexError, ValueError):
            return None


__all__ = ["ADAPTER_NAME", "PAGINATION_STYLES", "PRESETS", "GenericJsonSource", "get_path"]
