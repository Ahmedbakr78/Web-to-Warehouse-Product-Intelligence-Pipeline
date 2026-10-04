"""Seed data: users, permissions, settings, internal catalog and historical snapshots.

The seeder produces a *coherent* demo warehouse: every product has a multi-week price
history, price changes, lifecycle events, an internal catalog twin and matching
quality defects - which means every screen of the dashboard and every SQL analysis in
``db/analysis`` returns meaningful results immediately after ``make bootstrap``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.ingestion.cleaning import (
    category_slug,
    clean_brand,
    convert_to_usd,
    name_fingerprint,
    normalise_category,
    normalise_name_key,
    percent_change,
)

log = get_logger(__name__)

SEED_SALT = 20260101


# --------------------------------------------------------------------------------------
# Application users / settings
# --------------------------------------------------------------------------------------
def seed_users(session: Session) -> int:
    """Create the demo accounts documented in the README (idempotent)."""
    from app.api.security import hash_password
    from app.models.app_users import AppSetting, AppUser

    accounts = [
        (
            settings.seed_admin_email,
            settings.seed_admin_password,
            "Ahmed Abobakr",
            "admin",
            "Data Engineering Lead",
            "Data Platform",
            "#6366f1",
        ),
        (
            settings.seed_analyst_email,
            settings.seed_analyst_password,
            "Sara Mahmoud",
            "analyst",
            "Pricing Analyst",
            "Merchandising",
            "#0ea5e9",
        ),
        (
            settings.seed_viewer_email,
            settings.seed_viewer_password,
            "Karim Nabil",
            "viewer",
            "Category Manager",
            "Buying",
            "#10b981",
        ),
    ]
    created = 0
    for email, password, full_name, role, job_title, department, color in accounts:
        existing = session.execute(sa.select(AppUser).where(AppUser.email == email)).scalars().first()
        if existing is not None:
            continue
        session.add(
            AppUser(
                email=email,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=role,
                job_title=job_title,
                department=department,
                avatar_color=color,
                is_active=True,
                is_verified=True,
                login_count=0,
                password_changed_at=dt.datetime.now(dt.timezone.utc),
                preferences={
                    "notifications": {"price_drop": True, "dq_failure": True, "new_product": False},
                    "dashboard": {"default_range": "30d", "chart_type": "area"},
                },
            )
        )
        created += 1

    defaults = {
        (
            "pipeline.schedule_cron",
            "0 3 * * *",
            "string",
            "pipeline",
            "Cron expression for the daily Airflow DAG",
        ),
        (
            "pipeline.default_sources",
            "local_demo,dummyjson_products,fakestore_products,books_to_scrape",
            "string",
            "pipeline",
            "Sources enabled for scheduled runs",
        ),
        ("dq.min_quality_score", "80", "number", "quality", "Fail the run below this weighted DQ score"),
        (
            "ingest.rate_limit_per_minute",
            str(settings.requests_per_minute),
            "number",
            "ingestion",
            "Global request ceiling per host",
        ),
        ("ui.default_theme", "system", "string", "ui", "Default colour theme for new accounts"),
        ("retention.snapshot_days", "730", "number", "retention", "Days of price history to keep"),
    }
    for key, value, value_type, category, description in defaults:
        if session.get(AppSetting, key) is None:
            session.add(
                AppSetting(
                    key=key,
                    value=value,
                    value_type=value_type,
                    category=category,
                    description=description,
                    is_public=key.startswith("ui."),
                )
            )
    session.flush()
    if created:
        log.info("seeded %d users", created)
    return created


def seed_saved_views_and_alerts(session: Session) -> int:
    """Saved views + alert rules attached to the seeded accounts."""
    from app.models.app_users import AppAlertRule, AppSavedView, AppUser

    admin = (
        session.execute(sa.select(AppUser).where(AppUser.email == settings.seed_admin_email))
        .scalars()
        .first()
    )
    analyst = (
        session.execute(sa.select(AppUser).where(AppUser.email == settings.seed_analyst_email))
        .scalars()
        .first()
    )
    if admin is None or analyst is None:
        return 0
    if session.execute(sa.select(AppSavedView).limit(1)).scalars().first() is not None:
        return 0

    views = [
        (
            admin.user_id,
            "Big price drops",
            "products",
            {"min_change_pct": -5, "in_stock": True},
            "price_change_pct",
            "asc",
            ["name", "price", "change"],
        ),
        (
            admin.user_id,
            "Out of stock",
            "products",
            {"availability": "out_of_stock"},
            "last_seen_at",
            "desc",
            ["name", "category", "availability"],
        ),
        (
            analyst.user_id,
            "Electronics movers",
            "products",
            {"category": "Electronics", "window": "7d"},
            "change_pct",
            "asc",
            ["name", "brand", "price", "change"],
        ),
        (
            analyst.user_id,
            "New arrivals",
            "changes",
            {"event_type": "new", "window": "7d"},
            "detected_at",
            "desc",
            ["name", "category", "price"],
        ),
    ]
    for user_id, name, entity, filters, sort_by, sort_dir, columns in views:
        session.add(
            AppSavedView(
                user_id=user_id,
                name=name,
                entity=entity,
                filters=filters,
                sort_by=sort_by,
                sort_dir=sort_dir,
                visible_columns=columns,
                is_shared=True,
                is_favorite=True,
            )
        )

    alerts = [
        (analyst.user_id, "Price drop > 10%", "price_change_pct", "lt", -10.0, None),
        (analyst.user_id, "New product in Electronics", "new_product", "eq", 0.0, "Electronics"),
        (admin.user_id, "DQ failure", "dq_failure", "eq", 1.0, None),
        (admin.user_id, "Rating below 2.5", "rating", "lt", 2.5, None),
    ]
    for user_id, name, metric, operator, threshold, category in alerts:
        session.add(
            AppAlertRule(
                user_id=user_id,
                name=name,
                metric=metric,
                operator=operator,
                threshold=threshold,
                category=category,
                channel="in_app",
                is_active=True,
            )
        )
    session.flush()
    return len(views) + len(alerts)


# --------------------------------------------------------------------------------------
# Product catalogue used by the demo
# --------------------------------------------------------------------------------------
@dataclass
class SeedProduct:
    source_code: str
    source_product_id: str
    name: str
    brand: str | None
    category: str
    currency: str
    base_price: float


def build_seed_products(count: int = 60, seed: int = SEED_SALT) -> list[SeedProduct]:
    """Deterministic catalogue derived from the offline fixture source."""
    from app.ingestion.sources.local_fixture import LocalFixtureSource

    products: list[SeedProduct] = []
    for raw in LocalFixtureSource(seed=seed).fetch(limit=count):
        name = (raw.name or "").strip() or f"Demo Product {raw.source_product_id}"
        currency = raw.currency_hint or "USD"
        price_text = raw.price_text or ""
        digits = "".join(ch for ch in price_text if ch.isdigit() or ch in ".,")
        try:
            base_price = float(digits.replace(",", "")) if digits else 50.0
        except ValueError:
            base_price = 50.0
        products.append(
            SeedProduct(
                source_code=raw.source_code,
                source_product_id=raw.source_product_id,
                name=name,
                brand=raw.brand,
                category=normalise_category(raw.category),
                currency=currency,
                base_price=round(base_price, 2),
            )
        )
    return products


def seed_catalog(session: Session, products: Iterable[SeedProduct], *, match_ratio: float = 0.7) -> int:
    """Create the retailer's internal catalog: mostly matching, some delisted SKUs."""
    from app.models.catalog import CatalogProduct

    if session.execute(sa.select(CatalogProduct).limit(1)).scalars().first() is not None:
        return 0

    rng = random.Random(SEED_SALT)
    created = 0
    for index, product in enumerate(products):
        should_match = index < int(len(list(products)) * match_ratio)
        if not should_match:
            # Internal-only SKU (something the market does not list).
            session.add(
                CatalogProduct(
                    sku=f"INT-{index + 1:05d}",
                    name=f"{product.brand or 'House Brand'} Private Label Item {index + 1}",
                    normalized_name=normalise_name_key(
                        f"{product.brand or ''} private label item {index + 1}"
                    ),
                    brand=clean_brand(product.brand) or "House Brand",
                    category=product.category,
                    supplier=rng.choice(
                        ["Acme Imports", "Globex Supply", "Initech Wholesale", "Umbrella Ltd"]
                    ),
                    cost_price=round(product.base_price * 0.62, 2),
                    list_price=round(product.base_price * rng.uniform(1.02, 1.35), 2),
                    currency="USD",
                    qty_on_hand=rng.randint(0, 400),
                    status="active",
                    product_url=f"https://internal.local/products/INT-{index + 1:05d}",
                )
            )
            created += 1
            continue

        # Matching SKU with a slightly different list price -> price-gap analysis.
        gap = rng.uniform(-0.12, 0.18)
        session.add(
            CatalogProduct(
                sku=product.source_product_id,
                name=product.name,
                normalized_name=normalise_name_key(product.name),
                brand=clean_brand(product.brand),
                category=product.category,
                supplier=rng.choice(["Acme Imports", "Globex Supply", "Initech Wholesale", "Umbrella Ltd"]),
                cost_price=round(product.base_price * 0.6, 2),
                list_price=round(product.base_price * (1 + gap), 2),
                currency="USD",
                qty_on_hand=rng.randint(0, 400),
                status="active" if rng.random() > 0.08 else "discontinued",
            )
        )
        created += 1
    session.flush()
    log.info("seeded %d internal catalog rows", created)
    return created


# --------------------------------------------------------------------------------------
# Historical snapshots
# --------------------------------------------------------------------------------------
def _price_series(product: SeedProduct, days: int, seed: int) -> list[float]:
    """Random-walk price series with a promo cycle and rare clearance shocks.

    Daily moves stay small (0-2%) most of the time, promotions land in the -8%..-18%
    band every few weeks and a small number of products get an extreme clearance price.
    This produces a realistic distribution of ``magnitude_band`` values so the change
    analysis and alerting screens have genuine signal.
    """
    rng = random.Random(f"{seed}:{product.source_product_id}")
    value = product.base_price
    drift = rng.uniform(-0.006, 0.006)
    promo_bias = rng.choice([-0.12, -0.08, -0.05, 0.04, 0.06, 0.0])
    volatility = rng.choice([0.004, 0.008, 0.015, 0.025])
    series: list[float] = []
    for _day in range(days):
        roll = rng.random()
        if roll < 0.06:  # flash sale
            shock = rng.uniform(-0.18, -0.08)
        elif roll < 0.16:  # promotion window
            shock = promo_bias
        elif roll < 0.20:  # promotion ends
            shock = -promo_bias * 0.8
        else:
            shock = rng.gauss(0, volatility)
        value = max(1.0, value * (1 + drift + shock))
        series.append(round(value, 2))
    return series


def _lifecycle(index: int, days: int) -> tuple[int, int | None]:
    """Return ``(first_day, last_day | None)`` so arrivals and delistings occur."""
    rng = random.Random(f"life:{index}:{SEED_SALT}")
    first = rng.choice([0, 0, 0, 0, rng.randint(0, max(1, days // 2))])
    last: int | None = None
    roll = rng.random()
    if roll < 0.12:
        last = rng.randint(first + max(2, days // 3), days - 1)
    return first, last


def seed_history(
    session: Session, days: int = 120, *, source_code: str = "local_demo", batch: int = 500
) -> dict[str, int]:
    """Backfill ``days`` of snapshots, price changes and lifecycle events."""
    from app.etl.bootstrap import date_id, ensure_date_range
    from app.models.dimensions import DimCategory, DimProduct, DimSource
    from app.models.facts import ChgPriceChange, ChgProductEvent, FactPriceSnapshot
    from app.models.operations import EtlRun

    if session.execute(sa.select(FactPriceSnapshot).limit(1)).scalars().first() is not None:
        log.info("history already seeded - skipping")
        return {}

    ensure_date_range(session, days_back=days + 10, days_forward=2)
    products = build_seed_products()
    today = dt.date.today()

    # ---- dimensions -------------------------------------------------------------
    source = session.get(DimSource, source_code)
    if source is None:
        from app.etl.bootstrap import sync_dim_source
        from app.ingestion.base import get_source_class

        source = sync_dim_source(session, get_source_class(source_code)())

    category_cache: dict[str, int] = {
        row.slug: row.category_id for row in session.execute(sa.select(DimCategory)).scalars()
    }
    product_cache: dict[str, int] = {}

    # ---- products ---------------------------------------------------------------
    dim_rows: list[dict[str, Any]] = []
    for product in products:
        slug = category_slug(product.category)
        category_id = category_cache.get(slug)
        if category_id is None:
            category = DimCategory(
                name=product.category.split(" > ")[-1],
                slug=slug,
                path=product.category,
                level=product.category.count(">") + 1,
            )
            session.add(category)
            session.flush()
            category_cache[slug] = category.category_id
            category_id = category.category_id
        price_usd, fx = convert_to_usd(product.base_price, product.currency)
        row = DimProduct(
            source_code=product.source_code,
            source_product_id=product.source_product_id,
            canonical_name=product.name,
            normalized_name=normalise_name_key(product.name),
            display_name=product.name,
            brand=product.brand,
            category_id=category_id,
            currency=product.currency,
            current_price=product.base_price,
            fingerprint=name_fingerprint(product.name, product.brand),
            match_strategy="seed",
            match_score=1.0,
            is_active=True,
            observation_count=days,
            extra={"fx_rate_to_usd": fx, "seeded": True},
        )
        session.add(row)
        dim_rows.append(row)
    session.flush()
    product_cache = {row.source_product_id: row.product_id for row in dim_rows}

    # ---- runs (one per day) -----------------------------------------------------
    run_ids: list[str] = []
    for offset in range(days):
        run_date = today - dt.timedelta(days=days - 1 - offset)
        run_id = hashlib.sha1(f"seed:{run_date}".encode()).hexdigest()[:32]
        run_ids.append(run_id)
        session.add(
            EtlRun(
                run_id=run_id,
                run_key=f"seed-{run_date:%Y%m%d}",
                pipeline="product_intelligence",
                target_database=settings.active_database,
                dag_id="product_intelligence_pipeline",
                task_id="load_warehouse",
                status="success" if offset % 17 else "partial",
                trigger="schedule" if offset % 3 else "manual",
                started_at=dt.datetime.combine(run_date, dt.time(3, 5), tzinfo=dt.timezone.utc),
                finished_at=dt.datetime.combine(run_date, dt.time(3, 12), tzinfo=dt.timezone.utc),
                duration_ms=420_000 + (offset % 11) * 12_000,
                records_extracted=len(products),
                records_valid=len(products) - 2,
                records_rejected=2,
                records_inserted=len(products) if offset == 0 else 0,
                records_updated=0 if offset == 0 else len(products) - 2,
                duplicates_merged=1 if offset % 7 == 0 else 0,
                new_products=0,
                price_changes=0,
                removed_products=0,
                catalog_matched=0,
                dq_score=round(88 + (offset % 9), 2),
                params={"seeded": True},
                created_by="system",
            )
        )
    session.flush()

    # ---- snapshots + changes + events -------------------------------------------
    snapshot_rows: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    rng = random.Random(SEED_SALT)
    total_changes = total_new = total_removed = total_recategorised = 0

    for index, product in enumerate(products):
        first_day, last_day = _lifecycle(index, days)
        series = _price_series(product, days, SEED_SALT)
        product_id = product_cache[product.source_product_id]
        previous_price: float | None = None

        for offset in range(days):
            if offset < first_day or (last_day is not None and offset > last_day):
                previous_price = None
                continue
            run_date = today - dt.timedelta(days=days - 1 - offset)
            price = series[offset]
            price_usd, fx = convert_to_usd(price, product.currency)
            rating = round(rng.uniform(2.8, 4.9), 1)
            flags: list[str] = []
            # Deterministic quality defects so the DQ framework has real findings.
            if (index * 37 + offset * 11) % 211 == 5:
                rating = 9.9  # out-of-range rating
                flags.append("out_of_range_rating")
            if (index * 53 + offset * 7) % 431 == 11:
                price = None  # unparseable price upstream
                price_usd, fx = convert_to_usd(product.base_price, product.currency)
                flags.append("missing_price")
            if (index * 29 + offset * 13) % 617 == 3:
                availability = "unknown"
                flags.append("unknown_availability")
            availability = rng.choices(
                ["in_stock", "in_stock", "in_stock", "limited_stock", "out_of_stock", "preorder"],
                weights=[40, 22, 14, 8, 11, 5],
            )[0]
            captured_at = dt.datetime.combine(run_date, dt.time(3, 8), tzinfo=dt.timezone.utc)
            change_abs = (
                None if (previous_price is None or price is None) else round(price - previous_price, 2)
            )
            change_pct = percent_change(previous_price, price) if price is not None else None

            snapshot_rows.append(
                {
                    "product_id": product_id,
                    "source_code": product.source_code,
                    "run_id": run_ids[offset],
                    "date_id": date_id(run_date),
                    "captured_at": captured_at,
                    "price": price,
                    "list_price": None,
                    "currency": product.currency,
                    "fx_rate_to_usd": fx,
                    "price_usd": price_usd,
                    "discount_pct": None,
                    "rating": rating,
                    "rating_count": rng.randint(3, 2400),
                    "availability": availability,
                    "in_stock": availability in {"in_stock", "limited_stock"},
                    "price_change_abs": change_abs,
                    "price_change_pct": change_pct,
                    "is_first_sighting": previous_price is None,
                    "product_url": f"https://demo.local/products/{product.source_product_id}",
                    "raw_price_text": f"{price}",
                    "quality_flags": flags or None,
                }
            )

            if previous_price is not None and change_pct not in (None, 0.0):
                change_rows.append(
                    {
                        "product_id": product_id,
                        "source_code": product.source_code,
                        "run_id": run_ids[offset],
                        "date_id": date_id(run_date),
                        "previous_price": previous_price,
                        "new_price": price,
                        "change_abs": change_abs,
                        "change_pct": change_pct,
                        "direction": "increase" if (change_abs or 0) > 0 else "decrease",
                        "currency": product.currency,
                        "magnitude_band": "minor"
                        if abs(change_pct) < 1
                        else (
                            "small"
                            if abs(change_pct) < 5
                            else (
                                "moderate"
                                if abs(change_pct) < 15
                                else ("large" if abs(change_pct) < 30 else "major")
                            )
                        ),
                        "is_significant": abs(change_pct) >= 2.0,
                        "previous_price_usd": convert_to_usd(previous_price, product.currency)[0],
                        "new_price_usd": price_usd,
                        "detected_at": captured_at,
                    }
                )
                total_changes += 1

            if previous_price is None:
                event_rows.append(
                    {
                        "product_id": product_id,
                        "source_code": product.source_code,
                        "run_id": run_ids[offset],
                        "date_id": date_id(run_date),
                        "event_type": "new",
                        "severity": "info",
                        "new_value": product.name,
                        "detected_at": captured_at,
                        "details": {"seeded": True},
                    }
                )
                total_new += 1
            else:
                event_rows.append(
                    {
                        "product_id": product_id,
                        "source_code": product.source_code,
                        "run_id": run_ids[offset],
                        "date_id": date_id(run_date),
                        "event_type": "recurring",
                        "severity": "info",
                        "old_value": str(previous_price),
                        "new_value": str(price),
                        "detected_at": captured_at,
                        "details": None,
                    }
                )
            previous_price = price

        # ---- delisting event
        if last_day is not None:
            run_date = today - dt.timedelta(days=days - 1 - last_day)
            session.execute(
                sa.update(DimProduct)
                .where(DimProduct.product_id == product_id)
                .values(is_active=False, updated_at=dt.datetime.now(dt.timezone.utc))
            )
            event_rows.append(
                {
                    "product_id": product_id,
                    "source_code": product.source_code,
                    "run_id": run_ids[last_day],
                    "date_id": date_id(run_date),
                    "event_type": "removed",
                    "severity": "warning",
                    "old_value": product.name,
                    "days_missing": 7,
                    "detected_at": dt.datetime.combine(run_date, dt.time(3, 9), tzinfo=dt.timezone.utc),
                    "details": {"reason": "not listed in source after staleness window"},
                }
            )
            total_removed += 1

        # ---- occasional recategorisation
        if index % 7 == 3:
            alt = "Electronics" if product.category != "Electronics" else "Home & Living"
            alt_slug = category_slug(alt)
            alt_id = category_cache.get(alt_slug)
            if alt_id is None:
                category = DimCategory(name=alt, slug=alt_slug, path=alt, level=1)
                session.add(category)
                session.flush()
                category_cache[alt_slug] = category.category_id
                alt_id = category.category_id
            old_id = category_cache.get(category_slug(product.category))
            event_rows.append(
                {
                    "product_id": product_id,
                    "source_code": product.source_code,
                    "run_id": run_ids[days // 2],
                    "date_id": date_id(today - dt.timedelta(days=days // 2)),
                    "event_type": "category_changed",
                    "severity": "warning",
                    "old_value": product.category,
                    "new_value": alt,
                    "old_category_id": old_id,
                    "new_category_id": alt_id,
                    "detected_at": dt.datetime.combine(
                        today - dt.timedelta(days=days // 2), dt.time(3, 11), tzinfo=dt.timezone.utc
                    ),
                    "details": None,
                }
            )
            session.execute(
                sa.update(DimProduct).where(DimProduct.product_id == product_id).values(category_id=alt_id)
            )
            total_recategorised += 1

        if len(snapshot_rows) >= batch * 4:
            _bulk_insert(session, FactPriceSnapshot, snapshot_rows)
            _bulk_insert(session, ChgPriceChange, change_rows)
            _bulk_insert(session, ChgProductEvent, event_rows)
            snapshot_rows.clear()
            change_rows.clear()
            event_rows.clear()

    _bulk_insert(session, FactPriceSnapshot, snapshot_rows)
    _bulk_insert(session, ChgPriceChange, change_rows)
    _bulk_insert(session, ChgProductEvent, event_rows)

    # ---- category counters ------------------------------------------------------
    session.execute(
        sa.text(
            """
            UPDATE dim_category c
            SET product_count = (
                SELECT COUNT(*) FROM dim_product p
                WHERE p.category_id = c.category_id
            )
            """
        )
    )

    stats = {
        "products": len(products),
        "snapshots": sum(1 for _ in products) and _count(session, FactPriceSnapshot),
        "price_changes": _count(session, ChgPriceChange),
        "events": _count(session, ChgProductEvent),
        "runs": days,
    }
    session.flush()
    log.info(
        "seeded history: %d products, %d snapshots, %d price changes, %d events (%d new / %d removed / %d recategorised)",
        stats["products"],
        stats["snapshots"],
        stats["price_changes"],
        stats["events"],
        total_new,
        total_removed,
        total_recategorised,
    )
    return stats


def _bulk_insert(session: Session, model: Any, rows: list[dict[str, Any]]) -> None:
    """Insert many rows in one executemany call, ignoring unknown keys."""
    if not rows:
        return
    valid = {column.name for column in model.__table__.columns}
    keys: set[str] | None = None
    payload: list[dict[str, Any]] = []
    for row in rows:
        item = {key: value for key, value in row.items() if key in valid}
        keys = set(item) if keys is None else (keys & set(item))
        payload.append(item)
    if not payload or not keys:
        return
    session.execute(sa.insert(model), [{key: item[key] for key in keys} for item in payload])


def _count(session: Session, model: Any) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar() or 0


def run_full_seed(
    database: str | None = None, *, days: int = 120, with_history: bool = True
) -> dict[str, Any]:
    """Seed users, catalog and history into one target database."""
    with session_scope(database) as session:
        users = seed_users(session)
        products = build_seed_products()
        catalog = seed_catalog(session, products)
        extras = seed_saved_views_and_alerts(session)
    history: dict[str, Any] = {}
    if with_history:
        with session_scope(database) as session:
            history = seed_history(session, days=days)
    return {"users": users, "catalog": catalog, "saved": extras, "history": history}


__all__ = [
    "build_seed_products",
    "seed_users",
    "seed_catalog",
    "seed_history",
    "run_full_seed",
    "seed_saved_views_and_alerts",
]
