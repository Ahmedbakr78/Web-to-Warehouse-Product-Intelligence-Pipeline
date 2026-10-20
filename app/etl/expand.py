"""Scale the demo warehouse without touching production ingest paths.

The standard seeder is intentionally small: it is fast enough for CI and every
screen has at least a handful of rows. A live demo wants a different trade-off -
hundreds of thousands of observations, thousands of catalog SKUs and enough
history for every chart to have a real shape.

``expand_demo`` appends a deterministic synthetic cohort under the reserved
``SYN-`` namespace (source code ``local_demo``). It never modifies existing
products or snapshots, so it is safe to run against a populated warehouse and
safe to skip on a rerun.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import random
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.etl.bootstrap import date_id, ensure_date_range
from app.etl.loader import SIGNIFICANT_CHANGE_PCT
from app.ingestion.cleaning import (
    category_slug,
    clean_brand,
    convert_to_usd,
    name_fingerprint,
    normalise_name_key,
    percent_change,
)
from app.models.catalog import CatalogProduct
from app.models.dimensions import DimCategory, DimProduct, DimSource
from app.models.facts import (
    AggCategoryDaily,
    ChgPriceChange,
    ChgProductEvent,
    FactCatalogSnapshot,
    FactPriceSnapshot,
)
from app.models.operations import EtlRun

log = get_logger(__name__)

SYNTHETIC_PREFIX = "SYN-"
SYNTHETIC_SOURCE = "local_demo"
SEED_SALT = 20261111

BRANDS = [
    "Aurora", "Northwind", "Globex", "Umbra", "Lumen", "Kestrel", "Verdant", "Atlas",
    "Nimbus", "Sable", "Orchid", "Pulse", "Harbor", "Cedar", "Mosaic", "Vertex",
    "Solstice", "Tidal", "Ember", "Fable", "Juniper", "Onyx", "Prism", "Quartz",
    "Raven", "Summit", "Terra", "Vista", "Willow", "Zephyr", "Halcyon", "Ion",
    "Jade", "Krypton", "Lattice", "Meridian", "Nova", "Opal", "Pinnacle", "Ridge",
    "Sterling", "Thrive", "Union", "Vantage", "Wren", "Zenith", "Basalt", "Cobalt",
    "Drift", "Echo", "Flint", "Grove", "Haven", "Indigo", "Joule", "Kite",
    "Loom", "Marble", "Nectar", "Orbit",
]

CATEGORIES: list[tuple[str, float, float, float]] = [
    ("Electronics > Audio", 25, 480, 1.4),
    ("Electronics > Computers", 180, 2400, 1.2),
    ("Electronics > Mobile", 90, 1400, 1.1),
    ("Electronics > Cameras", 120, 1900, 0.8),
    ("Electronics > Wearables", 45, 700, 0.9),
    ("Home & Kitchen > Cookware", 15, 320, 1.3),
    ("Home & Kitchen > Furniture", 60, 1500, 1.1),
    ("Home & Kitchen > Decor", 8, 240, 1.4),
    ("Home & Kitchen > Bedding", 20, 280, 1.1),
    ("Home & Kitchen > Appliances", 35, 890, 1.2),
    ("Sports & Outdoors > Fitness", 12, 620, 1.2),
    ("Sports & Outdoors > Cycling", 30, 1300, 0.9),
    ("Sports & Outdoors > Camping", 15, 540, 1.0),
    ("Sports & Outdoors > Water Sports", 18, 700, 0.7),
    ("Books > Fiction", 5, 45, 1.6),
    ("Books > Non-fiction", 8, 60, 1.4),
    ("Books > Technical", 15, 180, 1.0),
    ("Books > Children", 4, 35, 1.3),
    ("Beauty > Skincare", 6, 180, 1.5),
    ("Beauty > Fragrance", 20, 320, 0.9),
    ("Beauty > Haircare", 5, 120, 1.2),
    ("Toys & Games > Building", 12, 260, 1.1),
    ("Toys & Games > Board Games", 9, 140, 1.0),
    ("Toys & Games > Outdoor", 10, 300, 0.8),
    ("Grocery > Pantry", 2, 40, 1.8),
    ("Grocery > Beverages", 2, 55, 1.5),
    ("Grocery > Organic", 3, 48, 1.2),
    ("Fashion > Footwear", 25, 320, 1.2),
    ("Fashion > Bags", 18, 420, 1.0),
    ("Fashion > Accessories", 6, 180, 1.3),
    ("Automotive > Care", 7, 160, 0.9),
    ("Pet Supplies > Food", 6, 90, 1.2),
    ("Pet Supplies > Toys", 4, 45, 0.9),
    ("Office > Stationery", 3, 70, 1.1),
    ("Office > Printers", 55, 650, 0.7),
    ("Garden > Tools", 14, 380, 0.9),
    ("Garden > Outdoor Living", 25, 700, 0.8),
]

ADJECTIVES = [
    "Aero", "Alpine", "Arc", "Aura", "Bold", "Cedar", "Classic", "Cloud", "Core",
    "Craft", "Crystal", "Delta", "Eco", "Edge", "Element", "Elite", "Essential",
    "Flux", "Focus", "Forest", "Fusion", "Glide", "Grand", "Green", "Halo",
    "Heritage", "Horizon", "Icon", "Impact", "Infinity", "Ivory", "Journey",
    "Kinetic", "Legacy", "Lite", "Lunar", "Magnetic", "Metro", "Modern", "Motion",
    "Nova", "Oak", "Ocean", "Optic", "Origin", "Peak", "Pioneer", "Prime",
    "Pure", "Quantum", "Rapid", "Ridge", "Royal", "Sierra", "Signal", "Silver",
    "Smart", "Solar", "Sonic", "Sphere", "Sprint", "Steel", "Studio", "Swift",
    "Terra", "Titan", "Trail", "Urban", "Vivid", "Wave", "Zen",
]

NOUNS = [
    "Backpack", "Blender", "Bottle", "Bracelet", "Brush", "Camera", "Chair", "Charger",
    "Clock", "Coffee Maker", "Compass", "Controller", "Cookware", "Cushion", "Desk",
    "Dumbbell", "Earbuds", "Fan", "Flask", "Frame", "Grill", "Hammer", "Headphones",
    "Heater", "Helmet", "Jacket", "Keyboard", "Lamp", "Lantern", "Laptop", "Lens",
    "Luggage", "Mattress", "Microphone", "Monitor", "Mouse", "Mug", "Notebook",
    "Oven", "Pack", "Pan", "Pen", "Phone Case", "Plant Pot", "Printer", "Projector",
    "Racket", "Router", "Sandal", "Scarf", "Scooter", "Shelf", "Shoe", "Speaker",
    "Stand", "Stool", "Sunglasses", "Table", "Tablet", "Tent", "Toaster", "Toy",
    "Tracker", "Tripod", "Tumbler", "Vacuum", "Vase", "Watch", "Water Filter",
]

MODEL_TAGS = ["Pro", "Max", "Lite", "Plus", "Ultra", "Mini", "Air", "Studio", "Core", "Edge"]
AVAILABILITY = ["in_stock", "in_stock", "in_stock", "in_stock", "limited_stock", "out_of_stock", "preorder"]


def _price_series(base: float, days: int, rng: random.Random, *, shock: bool) -> list[float]:
    """A believable daily series: drift, regular promos and rare discontinuities."""
    price = base
    values: list[float] = []
    for offset in range(days):
        if offset and offset % 14 == 0:
            move = -rng.uniform(0.06, 0.18)
        elif shock and offset == days // 2:
            move = rng.uniform(0.18, 0.38)
        elif offset and offset % 9 == 0:
            move = rng.uniform(-0.05, 0.05)
        else:
            move = rng.uniform(-0.018, 0.018)
        price = max(0.35, price * (1 + move))
        values.append(round(price, 2))
    return values


def _build_catalog_lines(rng: random.Random, count: int) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for index in range(count):
        path, low, high, weight = rng.choices(CATEGORIES, weights=[c[3] for c in CATEGORIES], k=1)[0]
        # Log-uniform price inside the category band keeps cheap and expensive
        # categories populated without a long tail that dwarfs everything.
        price = math.exp(rng.uniform(math.log(low), math.log(high)))
        brand = rng.choice(BRANDS)
        adj = rng.choice(ADJECTIVES)
        noun = rng.choice(NOUNS)
        model = f"{rng.choice(MODEL_TAGS)} {index + 1:05d}"
        name = f"{brand} {adj} {noun} {model}"
        currency = rng.choices(["USD", "EUR", "GBP"], weights=[80, 12, 8], k=1)[0]
        lines.append(
            {
                "source_code": SYNTHETIC_SOURCE,
                "source_product_id": f"{SYNTHETIC_PREFIX}{index + 1:06d}",
                "name": name,
                "brand": clean_brand(brand) or brand,
                "category": path,
                "base_price": round(price, 2),
                "currency": currency,
                "rng": rng,
                "category_weight": weight,
            }
        )
    return lines


def _existing_synthetic(session: Session) -> tuple[int, int]:
    products = (
        session.execute(
            sa.select(sa.func.count())
            .select_from(DimProduct)
            .where(DimProduct.source_product_id.like(f"{SYNTHETIC_PREFIX}%"))
        ).scalar()
        or 0
    )
    snapshots = (
        session.execute(
            sa.select(sa.func.count())
            .select_from(FactPriceSnapshot)
            .join(DimProduct, DimProduct.product_id == FactPriceSnapshot.product_id)
            .where(DimProduct.source_product_id.like(f"{SYNTHETIC_PREFIX}%"))
        ).scalar()
        or 0
    )
    return int(products), int(snapshots)


def _bulk(session: Session, model: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    session.execute(sa.insert(model), rows)


def _stats(session: Session) -> dict[str, int]:
    def count(model: Any) -> int:
        return int(session.execute(sa.select(sa.func.count()).select_from(model)).scalar() or 0)

    return {
        "products": count(DimProduct),
        "snapshots": count(FactPriceSnapshot),
        "price_changes": count(ChgPriceChange),
        "events": count(ChgProductEvent),
        "catalog": count(CatalogProduct),
        "catalog_snapshots": count(FactCatalogSnapshot),
        "runs": count(EtlRun),
    }


def expand_demo(
    session: Session,
    *,
    products: int = 19_500,
    days: int = 26,
    seed: int = SEED_SALT,
    batch_size: int = 4_000,
) -> dict[str, Any]:
    """Append a large deterministic synthetic cohort and its full history.

    Returns live table totals plus the number of rows created in this call. The
    function is idempotent: a second call with the same or smaller ``products``
    finds the cohort already present and skips the expensive work.
    """
    products = max(0, min(products, 50_000))
    days = max(7, min(days, 365))
    existing_products, existing_snapshots = _existing_synthetic(session)
    if existing_products >= products and existing_snapshots > 0:
        log.info("synthetic cohort already present: %d products, %d snapshots", existing_products, existing_snapshots)
        return {**_stats(session), "created_products": 0, "created_snapshots": 0, "skipped": True}

    today = dt.date.today()
    ensure_date_range(session, days_back=days + 8, days_forward=2)

    # ---------------------------------------------------------------- dimensions
    source = session.get(DimSource, SYNTHETIC_SOURCE)
    if source is None:
        source = DimSource(
            source_code=SYNTHETIC_SOURCE,
            name="Local demo cohort",
            kind="api",
            base_url="https://demo.local",
            license_note="Synthetic demo data generated by app/etl/expand.py",
            rate_limit_per_minute=60,
            min_delay_seconds=0,
            enabled=True,
            terms_allowed=True,
        )
        session.add(source)
        session.flush()

    categories = {
        row.slug: row for row in session.execute(sa.select(DimCategory)).scalars()
    }
    for path, _low, _high, _weight in CATEGORIES:
        slug = category_slug(path)
        if slug in categories:
            continue
        last = path.split(" > ")[-1]
        row = DimCategory(
            name=last,
            slug=slug,
            path=path,
            level=path.count(">") + 1,
            source_category_raw=path,
        )
        session.add(row)
        session.flush()
        categories[slug] = row

    # ---------------------------------------------------------------- runs
    dates = [today - dt.timedelta(days=days - 1 - offset) for offset in range(days)]
    run_ids: list[str] = []
    for run_date in dates:
        run_id = hashlib.sha1(f"expand:{seed}:{run_date}".encode()).hexdigest()[:32]
        run_ids.append(run_id)
        if session.get(EtlRun, run_id) is not None:
            continue
        session.add(
            EtlRun(
                run_id=run_id,
                run_key=f"expand-{run_date:%Y%m%d}",
                pipeline="product_intelligence",
                target_database=settings.active_database,
                dag_id="product_intelligence_pipeline",
                task_id="load_warehouse",
                status="success",
                trigger="manual",
                started_at=dt.datetime.combine(run_date, dt.time(2, 45), tzinfo=dt.timezone.utc),
                finished_at=dt.datetime.combine(run_date, dt.time(3, 8), tzinfo=dt.timezone.utc),
                duration_ms=1_380_000,
                records_extracted=products,
                records_valid=products,
                records_inserted=0,
                records_updated=products,
                dq_score=94.0,
                params={"synthetic": True, "cohort": "SYN", "seed": seed},
                created_by="system",
            )
        )
    session.flush()

    # ---------------------------------------------------------------- products
    rng = random.Random(seed)
    lines = _build_catalog_lines(rng, products)
    start_index = existing_products
    created_products = 0
    product_rows: list[dict[str, Any]] = []

    for offset, line in enumerate(lines):
        index = start_index + offset
        source_id = f"{SYNTHETIC_PREFIX}{index + 1:06d}"
        category_slug_value = category_slug(line["category"])
        category = categories[category_slug_value]
        product_rng = random.Random(f"{seed}:{source_id}")
        first_seen = dt.datetime.combine(dates[0], dt.time(3, 8), tzinfo=dt.timezone.utc)
        last_seen = dt.datetime.combine(dates[-1], dt.time(3, 8), tzinfo=dt.timezone.utc)
        price_usd, fx = convert_to_usd(line["base_price"], line["currency"])
        product_rows.append(
            {
                "source_product_id": source_id,
                "source_code": SYNTHETIC_SOURCE,
                "canonical_name": line["name"],
                "normalized_name": normalise_name_key(line["name"]),
                "display_name": line["name"],
                "brand": line["brand"],
                "category_id": category.category_id,
                "product_url": f"https://demo.local/syn/{source_id.lower()}",
                "image_url": None,
                "description": None,
                "currency": line["currency"],
                "current_price": line["base_price"],
                "previous_price": round(line["base_price"] / 1.01, 2),
                "current_rating": round(product_rng.uniform(3.4, 4.9), 1),
                "rating_count": product_rng.randint(6, 4_200),
                "availability": product_rng.choices(AVAILABILITY, weights=[50, 18, 12, 8, 6, 4, 2], k=1)[0],
                "fingerprint": name_fingerprint(line["name"], line["brand"]),
                "match_strategy": "seed",
                "match_score": 1.0,
                "is_active": True,
                "version": 1,
                "observation_count": days,
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "extra": {
                    "seeded": True,
                    "synthetic": True,
                    "fx_rate_to_usd": fx,
                    "base_price": line["base_price"],
                    "category_path": line["category"],
                },
            }
        )
        created_products += 1
        if len(product_rows) >= batch_size:
            session.execute(sa.insert(DimProduct), product_rows)
            product_rows.clear()
    _bulk(session, DimProduct, product_rows)
    session.flush()

    product_records = (
        session.execute(
            sa.select(
                DimProduct.product_id,
                DimProduct.source_product_id,
                DimProduct.canonical_name,
                DimProduct.brand,
                DimProduct.category_id,
                DimProduct.currency,
                DimProduct.current_price,
            ).where(DimProduct.source_product_id.like(f"{SYNTHETIC_PREFIX}%"))
        )
        .mappings()
        .all()
    )
    by_source_id = {row["source_product_id"]: row for row in product_records}

    # ---------------------------------------------------------------- snapshots
    synthetic_rng = random.Random(f"{seed}:history")
    created_snapshots = 0
    created_changes = 0
    created_events = 0
    created_catalog = 0
    snapshot_batch: list[dict[str, Any]] = []
    change_batch: list[dict[str, Any]] = []
    event_batch: list[dict[str, Any]] = []
    catalog_batch: list[dict[str, Any]] = []
    catalog_snapshot_batch: list[dict[str, Any]] = []
    latest_run = run_ids[-1]
    latest_date_id = date_id(dates[-1])
    removed_products: set[int] = set()

    for line in lines:
        record = by_source_id.get(line["source_product_id"])
        if record is None:
            continue
        product_id = int(record["product_id"])
        product_rng = random.Random(f"{seed}:{line['source_product_id']}")
        series = _price_series(line["base_price"], days, product_rng, shock=product_rng.random() < 0.012)
        removed_at = days - product_rng.randint(1, 4) if product_rng.random() < 0.035 else None
        list_price = None
        if product_rng.random() < 0.34:
            list_price = round(line["base_price"] * product_rng.uniform(1.06, 1.32), 2)
        previous: float | None = None
        for offset, price in enumerate(series):
            if removed_at is not None and offset > removed_at:
                obsolete = True
            else:
                obsolete = False
            if obsolete:
                break
            run_date = dates[offset]
            price_usd, fx = convert_to_usd(price, line["currency"])
            availability = synthetic_rng.choices(AVAILABILITY, weights=[55, 16, 10, 7, 6, 4, 2], k=1)[0]
            rating = round(synthetic_rng.uniform(2.8, 4.9), 1)
            flags: list[str] = []
            if synthetic_rng.random() < 0.0025:
                rating = 9.9
                flags.append("out_of_range_rating")
            if synthetic_rng.random() < 0.0015:
                flags.append("missing_price")
            if synthetic_rng.random() < 0.002:
                availability = "unknown"
                flags.append("unknown_availability")
            change_abs = None if previous is None else round(price - previous, 2)
            change_pct = percent_change(previous, price) if previous is not None else None
            captured_at = dt.datetime.combine(run_date, dt.time(3, 8), tzinfo=dt.timezone.utc)
            snapshot_batch.append(
                {
                    "product_id": product_id,
                    "source_code": SYNTHETIC_SOURCE,
                    "run_id": run_ids[offset],
                    "date_id": date_id(run_date),
                    "captured_at": captured_at,
                    "price": price,
                    "list_price": list_price,
                    "currency": line["currency"],
                    "fx_rate_to_usd": fx,
                    "price_usd": price_usd if "missing_price" not in flags else None,
                    "discount_pct": round((1 - price / list_price) * 100, 2) if list_price else None,
                    "rating": rating,
                    "rating_count": synthetic_rng.randint(4, 2_800),
                    "availability": availability,
                    "in_stock": availability in {"in_stock", "limited_stock"},
                    "price_change_abs": change_abs,
                    "price_change_pct": change_pct,
                    "is_first_sighting": previous is None,
                    "product_url": f"https://demo.local/syn/{line['source_product_id'].lower()}",
                    "raw_price_text": f"{price}",
                    "quality_flags": flags or None,
                }
            )
            created_snapshots += 1

            if (
                previous is not None
                and change_pct is not None
                and (abs(change_pct) >= 0.75 or offset % 5 == 0)
            ):
                change_batch.append(
                    {
                        "product_id": product_id,
                        "source_code": SYNTHETIC_SOURCE,
                        "run_id": run_ids[offset],
                        "date_id": date_id(run_date),
                        "previous_price": previous,
                        "new_price": price,
                        "change_abs": change_abs,
                        "change_pct": change_pct,
                        "direction": "increase" if (change_abs or 0) > 0 else "decrease",
                        "currency": line["currency"],
                        "magnitude_band": "minor"
                        if abs(change_pct) < 1
                        else "small"
                        if abs(change_pct) < 5
                        else "moderate"
                        if abs(change_pct) < 15
                        else "large"
                        if abs(change_pct) < 30
                        else "major",
                        "is_significant": abs(change_pct) >= SIGNIFICANT_CHANGE_PCT,
                        "previous_price_usd": convert_to_usd(previous, line["currency"])[0],
                        "new_price_usd": price_usd,
                        "detected_at": captured_at,
                    }
                )
                created_changes += 1

            if previous is None:
                event_batch.append(
                    {
                        "product_id": product_id,
                        "source_code": SYNTHETIC_SOURCE,
                        "run_id": run_ids[offset],
                        "date_id": date_id(run_date),
                        "event_type": "new",
                        "severity": "info",
                        "new_value": line["name"],
                        "detected_at": captured_at,
                        "details": {"synthetic": True},
                    }
                )
                created_events += 1
            previous = price
            if len(snapshot_batch) >= batch_size:
                _bulk(session, FactPriceSnapshot, snapshot_batch)
                snapshot_batch.clear()
            if len(change_batch) >= batch_size:
                _bulk(session, ChgPriceChange, change_batch)
                change_batch.clear()
            if len(event_batch) >= batch_size:
                _bulk(session, ChgProductEvent, event_batch)
                event_batch.clear()

        if removed_at is not None:
            removed_products.add(product_id)
            event_batch.append(
                {
                    "product_id": product_id,
                    "source_code": SYNTHETIC_SOURCE,
                    "run_id": latest_run,
                    "date_id": latest_date_id,
                    "event_type": "removed",
                    "severity": "warning",
                    "old_value": line["name"],
                    "days_missing": 7,
                    "detected_at": dt.datetime.combine(dates[-1], dt.time(3, 9), tzinfo=dt.timezone.utc),
                    "details": {"synthetic": True},
                }
            )
            created_events += 1

        # ---------------------------------------------------------- internal catalog
        if product_rng.random() < 0.66:
            gap = product_rng.uniform(-0.22, 0.24)
            catalog_price = round(line["base_price"] * (1 + gap), 2)
            sku = line["source_product_id"]
            catalog_batch.append(
                {
                    "sku": sku,
                    "name": line["name"],
                    "normalized_name": normalise_name_key(line["name"]),
                    "brand": line["brand"],
                    "category": line["category"],
                    "supplier": product_rng.choice(
                        ["Acme Imports", "Globex Supply", "Initech Wholesale", "Umbrella Ltd", "Hooli Logistics"]
                    ),
                    "cost_price": round(catalog_price * product_rng.uniform(0.55, 0.72), 2),
                    "list_price": catalog_price,
                    "currency": "USD",
                    "qty_on_hand": product_rng.randint(0, 900),
                    "status": "active" if product_rng.random() > 0.06 else "discontinued",
                    "product_url": f"https://internal.local/products/{sku}",
                    "attributes": {"synthetic": True},
                }
            )
            created_catalog += 1
            catalog_snapshot_batch.append(
                {
                    "run_id": latest_run,
                    "catalog_sku": sku,
                    "product_id": product_id,
                    "source_code": SYNTHETIC_SOURCE,
                    "date_id": latest_date_id,
                    "match_status": "matched" if product_rng.random() > 0.05 else "unmatched",
                    "match_strategy": "normalized",
                    "similarity_score": round(product_rng.uniform(0.82, 0.99), 3),
                    "scraped_name": line["name"],
                    "catalog_name": line["name"],
                    "scraped_price": series[removed_at or days - 1],
                    "catalog_price": catalog_price,
                    "price_gap_abs": round(series[removed_at or days - 1] - catalog_price, 2),
                    "price_gap_pct": round((series[removed_at or days - 1] - catalog_price) / catalog_price * 100, 2)
                    if catalog_price
                    else None,
                    "category_match": True,
                    "brand_match": True,
                    "is_price_mismatch": abs(gap) >= 0.12,
                    "matched_at": dt.datetime.combine(dates[-1], dt.time(3, 8), tzinfo=dt.timezone.utc),
                    "details": {"synthetic": True},
                }
            )
            if len(catalog_batch) >= batch_size:
                _bulk(session, CatalogProduct, catalog_batch)
                catalog_batch.clear()
            if len(catalog_snapshot_batch) >= batch_size:
                _bulk(session, FactCatalogSnapshot, catalog_snapshot_batch)
                catalog_snapshot_batch.clear()

    _bulk(session, FactPriceSnapshot, snapshot_batch)
    _bulk(session, ChgPriceChange, change_batch)
    _bulk(session, ChgProductEvent, event_batch)
    _bulk(session, CatalogProduct, catalog_batch)
    _bulk(session, FactCatalogSnapshot, catalog_snapshot_batch)

    # Products that stopped being listed keep their history but leave the live view.
    if removed_products:
        session.execute(
            sa.update(DimProduct)
            .where(DimProduct.product_id.in_(removed_products))
            .values(is_active=False, last_seen_at=dt.datetime.combine(dates[-1], dt.time(3, 9), tzinfo=dt.timezone.utc))
        )

    # ---------------------------------------------------------------- aggregates
    # Rebuild the category rollup for the synthetic source over the generated
    # window. The SQL aggregates the fact table directly, so the numbers always
    # match the snapshots regardless of how they were generated.
    session.execute(
        sa.delete(AggCategoryDaily).where(
            AggCategoryDaily.source_code == SYNTHETIC_SOURCE,
            AggCategoryDaily.date_id >= date_id(dates[0]),
            AggCategoryDaily.date_id <= latest_date_id,
        )
    )
    session.execute(
        sa.text(
            """
            INSERT INTO agg_category_daily
                (date_id, category_id, source_code, product_count, new_product_count,
                 removed_product_count, avg_price, median_price, min_price, max_price,
                 avg_rating, price_change_count, avg_price_change_pct, computed_at)
            SELECT f.date_id,
                   p.category_id,
                   f.source_code,
                   COUNT(*),
                   SUM(CASE WHEN f.is_first_sighting THEN 1 ELSE 0 END),
                   0,
                   AVG(f.price_usd),
                   AVG(f.price_usd),
                   MIN(f.price_usd),
                   MAX(f.price_usd),
                   AVG(f.rating),
                   SUM(CASE WHEN f.price_change_pct IS NOT NULL AND f.price_change_pct <> 0 THEN 1 ELSE 0 END),
                   AVG(ABS(f.price_change_pct)),
                   CURRENT_TIMESTAMP
            FROM fact_price_snapshot f
            JOIN dim_product p ON p.product_id = f.product_id
            WHERE f.source_code = :source
              AND f.date_id >= :start
              AND f.date_id <= :end
              AND p.category_id IS NOT NULL
            GROUP BY f.date_id, p.category_id, f.source_code
            """
        ),
        {"source": SYNTHETIC_SOURCE, "start": date_id(dates[0]), "end": latest_date_id},
    )

    session.execute(
        sa.text(
            """
            UPDATE dim_category
            SET product_count = (
                SELECT COUNT(*) FROM dim_product
                WHERE dim_product.category_id = dim_category.category_id
            )
            """
        )
    )
    session.execute(
        sa.text(
            """
            UPDATE dim_source
            SET total_records = (
                    SELECT COUNT(*) FROM fact_price_snapshot
                    WHERE fact_price_snapshot.source_code = dim_source.source_code
                ),
                total_runs = (
                    SELECT COUNT(DISTINCT run_id) FROM fact_price_snapshot
                    WHERE fact_price_snapshot.source_code = dim_source.source_code
                ),
                last_run_id = :run_id,
                last_run_at = :run_at,
                robots_checked_at = CURRENT_TIMESTAMP,
                success_rate_pct = 100.0,
                avg_duration_seconds = 1380.0
            WHERE source_code = :source
            """
        ),
        {
            "source": SYNTHETIC_SOURCE,
            "run_id": latest_run,
            "run_at": dt.datetime.combine(dates[-1], dt.time(3, 8), tzinfo=dt.timezone.utc),
        },
    )
    session.flush()

    stats = _stats(session)
    log.info(
        "expanded demo cohort: +%d products, +%d snapshots, +%d changes, +%d events",
        created_products,
        created_snapshots,
        created_changes,
        created_events,
    )
    return {
        **stats,
        "created_products": created_products,
        "created_snapshots": created_snapshots,
        "created_changes": created_changes,
        "created_events": created_events,
        "created_catalog": created_catalog,
        "removed_products": len(removed_products),
        "skipped": False,
    }


__all__ = ["expand_demo", "SYNTHETIC_PREFIX", "SYNTHETIC_SOURCE"]
