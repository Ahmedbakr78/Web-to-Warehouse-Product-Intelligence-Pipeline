"""Steam Store storefront API source (Valve, free and keyless).

Endpoints: https://store.steampowered.com/api/appdetails?appids=...
           https://store.steampowered.com/appreviews/{appid}?json=1
Terms:     https://partner.steamgames.com/doc/webapi#conditions - the public
           storefront endpoints are documented and keyless; we keep a
           conservative request budget anyway.

Compliance notes
----------------
* ``store.steampowered.com/robots.txt`` disallows ``/share/``,
  ``/news/externalpost/``, ``/account/…`` and ``/widget/`` - both endpoints
  used here (``/api/appdetails`` and ``/appreviews/``) are allowed.
* A curated list of well-known app IDs keeps the crawl tiny and deterministic;
  the source never enumerates the full Steam catalogue.

Prices arrive in cents (``price_overview.initial`` / ``final``) with an explicit
``discount_percent``, which exercises list-price and discount normalisation, and
the review summary provides ``total_positive`` / ``total_negative`` counts that
are mapped onto a 5-star scale.  Free-to-play titles carry no price block, which
exercises the completeness rules of the data-quality framework.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.base import ProductSource, RawProduct, register_source

log = get_logger(__name__)

#: Curated, stable app IDs (a mix of paid, discounted and free-to-play titles)
#: so a run stays small, deterministic and polite.
CURATED_APPIDS: tuple[int, ...] = (
    10,  # Counter-Strike
    220,  # Half-Life 2
    400,  # Portal
    440,  # Team Fortress 2 (free)
    550,  # Left 4 Dead 2
    570,  # Dota 2 (free)
    620,  # Portal 2
    730,  # Counter-Strike 2 (free)
    2270,  # Wolfenstein 3D
    48000,  # LIMBO
    105600,  # Terraria
    236390,  # War Thunder (free)
    289070,  # Sid Meier's Civilization VI
    359550,  # Tom Clancy's Rainbow Six Siege
    1172470,  # Apex Legends (free)
    1174180,  # Red Dead Redemption 2
    1245620,  # ELDEN RING
    1551360,  # Forza Horizon 5
)

DETAIL_FIELDS = "basic,price_overview,genres,release_date"


@register_source
class SteamStoreSource(ProductSource):
    """Games with cent-based prices, discount pairs, genres and review scores."""

    code: ClassVar[str] = "steam_store"
    name: ClassVar[str] = "Steam Store API"
    kind: ClassVar[str] = "api"
    base_url: ClassVar[str] = "https://store.steampowered.com/api/appdetails"
    reviews_url: ClassVar[str] = "https://store.steampowered.com/appreviews/{appid}"
    terms_url: ClassVar[str] = "https://partner.steamgames.com/doc/webapi#conditions"
    license_note: ClassVar[str] = "Steam storefront data © Valve - keyless public endpoints, conservative budget."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 20
    min_delay_seconds: ClassVar[float] = 1.5
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Storefront details plus review summaries for a curated list of games: "
        "prices in cents with discount pairs, genres, release dates and "
        "positive/negative review counts mapped to a 5-star rating."
    )

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or settings.max_products_per_source
        # Two requests per game (details + reviews): halve the budget.
        wanted = max(1, min(len(CURATED_APPIDS), limit // 2 or 1))
        emitted = 0

        for appid in CURATED_APPIDS:
            if emitted >= wanted:
                break
            data = self._details(appid)
            if data is None:
                continue
            summary = self._review_summary(appid)
            raw = self._to_raw(data, summary, appid)
            if raw is None:
                continue
            yield raw
            emitted += 1

    def _details(self, appid: int) -> dict[str, Any] | None:
        self._count_request()
        try:
            payload = self.client.get_json(
                self.base_url,
                params={"appids": appid, "cc": "us", "l": "en", "filters": DETAIL_FIELDS},
            )
        except Exception as exc:  # a failing appid must not kill the run
            self.errors.append(f"appid {appid}: {exc}")
            return None
        entry = payload.get(str(appid)) if isinstance(payload, dict) else None
        if not isinstance(entry, dict) or not entry.get("success"):
            self.errors.append(f"appid {appid}: unsuccessful appdetails response")
            return None
        data = entry.get("data")
        return data if isinstance(data, dict) else None

    def _review_summary(self, appid: int) -> dict[str, Any] | None:
        self._count_request()
        try:
            payload = self.client.get_json(
                self.reviews_url.format(appid=appid),
                params={"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0},
            )
        except Exception as exc:  # ratings are enrichment, never fatal
            self.errors.append(f"appid {appid} reviews: {exc}")
            return None
        summary = payload.get("query_summary") if isinstance(payload, dict) else None
        return summary if isinstance(summary, dict) else None

    def _to_raw(
        self,
        data: dict[str, Any],
        summary: dict[str, Any] | None,
        appid: int,
    ) -> RawProduct | None:
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        if not name:
            return None

        price_block = data.get("price_overview") or {}
        initial = price_block.get("initial")
        final = price_block.get("final")
        currency = price_block.get("currency") or self.default_currency
        is_free = bool(data.get("is_free"))
        release = data.get("release_date") or {}
        coming_soon = bool(release.get("coming_soon"))

        price_text = self._cents(final) if final is not None else ("0" if is_free else None)
        list_price_text = self._cents(initial) if initial is not None else None
        if is_free:
            availability_text, in_stock = "in_stock", True
        elif coming_soon:
            availability_text, in_stock = "preorder", False
        elif price_text is not None:
            availability_text, in_stock = "in_stock", True
        else:
            availability_text, in_stock = None, None

        rating_text = rating_count_text = None
        summary = summary or {}
        positive, negative = summary.get("total_positive"), summary.get("total_negative")
        total = summary.get("total_reviews")
        if isinstance(positive, int) and isinstance(negative, int) and positive + negative > 0:
            stars = round(positive / (positive + negative) * 5.0, 2)
            rating_text = f"{stars} out of 5"
            rating_count_text = str(total) if isinstance(total, int) else str(positive + negative)

        genres = data.get("genres") or []
        genre = genres[0].get("description") if isinstance(genres, list) and genres else None
        publishers = data.get("publishers") or data.get("developers") or []
        brand = publishers[0] if isinstance(publishers, list) and publishers else None

        return RawProduct(
            source_code=self.code,
            source_product_id=str(appid),
            name=str(name),
            category=str(genre or "Games").title(),
            price_text=price_text,
            currency_hint=str(currency),
            list_price_text=list_price_text,
            rating_text=rating_text,
            rating_count_text=rating_count_text,
            availability_text=availability_text,
            in_stock_flag=in_stock,
            url=f"https://store.steampowered.com/app/{appid}/",
            image_url=str(data.get("header_image") or data.get("capsule_image") or ""),
            brand=str(brand) if brand else None,
            description=str(data.get("short_description") or "") or None,
            payload={
                "appid": appid,
                "type": data.get("type"),
                "is_free": is_free,
                "discount_percent": price_block.get("discount_percent"),
                "review_score_desc": summary.get("review_score_desc"),
                "release_date": release.get("date"),
            },
        )

    @staticmethod
    def _cents(value: Any) -> str | None:
        """Steam publishes integer cents; convert to a decimal string."""
        try:
            return f"{int(value) / 100:.2f}"
        except (TypeError, ValueError):
            return None
