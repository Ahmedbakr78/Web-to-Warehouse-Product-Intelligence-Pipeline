"""Source contract, canonical record shapes and the source registry.

Every ingestion source implements :class:`ProductSource` and yields :class:`RawProduct`
objects that carry the *original* values exactly as published.  Cleaning happens later
in :func:`transform_product`, which keeps extraction and preparation independently
testable.
"""

from __future__ import annotations

import abc
import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.core.config import settings
from app.core.errors import SourceNotFoundError
from app.core.logging import get_logger
from app.ingestion.cleaning import (
    availability_slug,
    blocking_key,
    category_levels,
    category_slug,
    clean_brand,
    clean_product_name,
    content_hash,
    convert_to_usd,
    name_fingerprint,
    normalise_availability,
    normalise_category,
    normalise_name_key,
    parse_price,
    parse_rating,
    percent_change,
    truncate,
    validate_url,
)
from app.ingestion.http_client import CompliantHttpClient

log = get_logger(__name__)


# --------------------------------------------------------------------------------------
# Record shapes
# --------------------------------------------------------------------------------------
@dataclass
class RawProduct:
    """A product exactly as it appeared upstream (no cleaning applied yet)."""

    source_code: str
    source_product_id: str
    name: str
    category: str | None = None
    price_text: str | None = None
    currency_hint: str | None = None
    list_price_text: str | None = None
    rating_text: str | None = None
    rating_count_text: str | None = None
    star_elements: int | None = None
    availability_text: str | None = None
    in_stock_flag: bool | None = None
    url: str | None = None
    image_url: str | None = None
    brand: str | None = None
    description: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    http_status: int | None = 200
    fetched_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @property
    def content_hash(self) -> str:
        return content_hash(
            self.source_code, self.source_product_id, self.name, self.price_text, self.availability_text
        )


@dataclass
class NormalizedProduct:
    """A cleaned, enriched and validated product ready for the warehouse."""

    source_code: str
    source_product_id: str
    canonical_name: str
    normalized_name: str
    fingerprint: str
    blocking_key: str
    brand: str | None = None
    category: str = "Uncategorised"
    category_slug: str = "uncategorised"
    category_levels: int = 1
    raw_category: str | None = None
    price: float | None = None
    list_price: float | None = None
    currency: str = "USD"
    fx_rate_to_usd: float = 1.0
    price_usd: float | None = None
    list_price_usd: float | None = None
    discount_pct: float | None = None
    rating: float | None = None
    rating_count: int | None = None
    availability: str = "unknown"
    in_stock: bool = False
    product_url: str | None = None
    image_url: str | None = None
    description: str | None = None
    raw_name: str | None = None
    raw_price_text: str | None = None
    raw_category_text: str | None = None
    payload_hash: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)
    is_valid: bool = True
    reject_reason: str | None = None
    fetched_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def flag(self, code: str) -> None:
        if code not in self.quality_flags:
            self.quality_flags.append(code)


class ProductSource(abc.ABC):
    """Base class for every ingestion source (API or permitted website)."""

    code: ClassVar[str] = ""
    name: ClassVar[str] = ""
    kind: ClassVar[str] = "api"  # api | scrape
    base_url: ClassVar[str] = ""
    terms_url: ClassVar[str | None] = None
    license_note: ClassVar[str | None] = None
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 30
    min_delay_seconds: ClassVar[float] = 1.0
    enabled: ClassVar[bool] = True
    terms_allowed: ClassVar[bool] = True
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = ""

    def __init__(self, run_id: str | None = None, client: CompliantHttpClient | None = None) -> None:
        self.run_id = run_id
        self._client = client
        self.http_calls = 0
        self.errors: list[str] = []

    # ------------------------------------------------------------------ helpers
    @property
    def client(self) -> CompliantHttpClient:
        if self._client is None:
            self._client = CompliantHttpClient(
                source_code=self.code,
                run_id=self.run_id,
                requests_per_second=min(self.rate_limit_per_minute / 60.0, 5.0),
                requests_per_minute=self.rate_limit_per_minute,
                min_delay_seconds=self.min_delay_seconds,
            )
        return self._client

    def _count_request(self) -> None:
        self.http_calls += 1

    # ------------------------------------------------------------------ contract
    @abc.abstractmethod
    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        """Yield raw products. Implementations must be polite and page lazily."""

    def health_check(self) -> dict[str, Any]:
        """Lightweight availability probe used by the Sources screen."""
        return {
            "code": self.code,
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "enabled": self.enabled,
            "terms_allowed": self.terms_allowed,
            "terms_url": self.terms_url,
            "robots_respected": settings.respect_robots_txt,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "min_delay_seconds": self.min_delay_seconds,
            "supports_paging": self.supports_paging,
            "description": self.description,
        }

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


# --------------------------------------------------------------------------------------
# Transform stage
# --------------------------------------------------------------------------------------
REQUIRED_FIELDS_MIN_LENGTH = 2


def transform_product(raw: RawProduct, *, strict: bool = False) -> NormalizedProduct:
    """Clean, normalise, enrich and validate one raw record.

    The function never raises for bad data - it returns an invalid record carrying a
    ``reject_reason`` so the staging zone keeps a full audit trail.
    """
    flags: list[str] = []
    canonical_name = clean_product_name(raw.name)
    normalized_name = normalise_name_key(canonical_name or raw.name)
    brand = clean_brand(raw.brand)
    raw_category_text = raw.category
    category = normalise_category(raw.category)

    price_info = parse_price(raw.price_text, default_currency=raw.currency_hint or self_currency(raw))
    price = price_info.amount if price_info.is_valid else None
    list_info = parse_price(raw.list_price_text, default_currency=price_info.currency or self_currency(raw))
    list_price = list_info.amount if list_info.is_valid else None

    currency = (price_info.currency or raw.currency_hint or self_currency(raw) or "USD").upper()
    fx_rate = convert_to_usd(None, currency)[1]
    price_usd, fx_rate = convert_to_usd(price, currency)
    list_price_usd, _ = convert_to_usd(list_price, currency)

    rating_info = parse_rating(
        raw.rating_text,
        count_text=raw.rating_count_text,
        star_elements=raw.star_elements,
    )
    availability, in_stock = normalise_availability(raw.availability_text, in_stock_flag=raw.in_stock_flag)

    discount_pct = None
    if price is not None and list_price and list_price > 0:
        change = percent_change(list_price, price)
        discount_pct = round(abs(change), 4) if change is not None and change < 0 else None

    if price_info.raw and not price_info.is_valid:
        flags.append("unparseable_price")
    if not rating_info.value:
        flags.append("missing_rating")
    if availability == "unknown":
        flags.append("unknown_availability")
    if not validate_url(raw.url):
        flags.append("invalid_url")
    if canonical_name.lower() == normalise_category(category).lower():
        flags.append("name_equals_category")

    record = NormalizedProduct(
        source_code=raw.source_code,
        source_product_id=str(raw.source_product_id),
        canonical_name=canonical_name or "",
        normalized_name=normalized_name,
        fingerprint=name_fingerprint(canonical_name or raw.name, brand),
        blocking_key=blocking_key(canonical_name or raw.name, settings.dedupe_blocking_key_length),
        brand=brand,
        category=category,
        category_slug=category_slug(category),
        category_levels=category_levels(category),
        raw_category=raw_category_text,
        price=price,
        list_price=list_price,
        currency=currency,
        fx_rate_to_usd=fx_rate,
        price_usd=price_usd,
        list_price_usd=list_price_usd,
        discount_pct=discount_pct,
        rating=rating_info.value,
        rating_count=rating_info.count,
        availability=availability,
        in_stock=in_stock,
        product_url=raw.url,
        image_url=raw.image_url,
        description=truncate(clean_product_name(raw.description, max_length=600) or raw.description, 1000),
        raw_name=truncate(raw.name, 500),
        raw_price_text=truncate(raw.price_text, 64),
        raw_category_text=truncate(raw_category_text, 256),
        payload_hash=raw.content_hash,
        payload=raw.payload or {},
        fetched_at=raw.fetched_at,
    )
    record.quality_flags = flags

    # ---- validation gates (never raise: the staging zone records the rejection)
    if len(canonical_name) < REQUIRED_FIELDS_MIN_LENGTH:
        record.is_valid = False
        record.reject_reason = "missing_or_invalid_name"
    elif price is None and list_price is None:
        record.flag("missing_price")
        if strict:
            record.is_valid = False
            record.reject_reason = "missing_price"
    if not validate_url(raw.url):
        if strict:
            record.is_valid = False
            record.reject_reason = record.reject_reason or "invalid_url"
    return record


def self_currency(raw: RawProduct) -> str:
    """Currency hint carried by the source itself."""
    return raw.currency_hint or "USD"


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------
_REGISTRY: dict[str, type[ProductSource]] = {}


def register_source(cls: type[ProductSource]) -> type[ProductSource]:
    """Class decorator that adds a source to the global registry."""
    if not cls.code:
        raise ValueError(f"{cls.__name__} must define a non-empty `code`")
    _REGISTRY[cls.code] = cls
    return cls


def get_source_class(code: str) -> type[ProductSource]:
    load_builtin_sources()
    try:
        return _REGISTRY[code]
    except KeyError as exc:
        raise SourceNotFoundError(
            f"unknown source '{code}'",
            details={"available": sorted(_REGISTRY)},
        ) from exc


def get_source(
    code: str, run_id: str | None = None, client: CompliantHttpClient | None = None
) -> ProductSource:
    return get_source_class(code)(run_id=run_id, client=client)


def list_sources() -> list[dict[str, Any]]:
    load_builtin_sources()
    return [cls().health_check() for cls in sorted(_REGISTRY.values(), key=lambda c: c.code)]


def all_source_codes() -> list[str]:
    load_builtin_sources()
    return sorted(_REGISTRY)


_loaded = False


def load_builtin_sources() -> None:
    """Import the bundled source modules exactly once."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from app.ingestion.sources import (  # noqa: F401  (import for side effects)
        books_to_scrape,
        dummyjson,
        fakestore,
        local_fixture,
        openlibrary,
    )


__all__ = [
    "RawProduct",
    "NormalizedProduct",
    "ProductSource",
    "transform_product",
    "register_source",
    "get_source",
    "get_source_class",
    "list_sources",
    "all_source_codes",
    "load_builtin_sources",
    "availability_slug",
]
