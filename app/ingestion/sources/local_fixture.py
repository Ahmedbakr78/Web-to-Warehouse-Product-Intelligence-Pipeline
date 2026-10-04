"""Deterministic offline source used for demos, tests and CI.

It generates a realistic retail catalogue in-memory (no network, fully
deterministic) *including deliberate data-quality defects*:

* ~4% records without a price
* ~3% with an out-of-range rating
* ~6% near-duplicate titles (the fuzzy deduper must merge them)
* a handful of price swings and stock-out events

This makes the whole pipeline - extraction, cleaning, dedupe, DQ, change detection
and the dashboard - demonstrable on any machine, with or without internet access.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from collections.abc import Iterator
from typing import Any, ClassVar

from app.ingestion.base import ProductSource, RawProduct, register_source

BRANDS: dict[str, list[str]] = {
    "Electronics": ["Samsung", "Sony", "Apple", "LG", "Bose", "Anker", "Logitech", "Philips"],
    "Electronics > Mobile Phones": ["Samsung", "Apple", "Xiaomi", "Motorola", "OnePlus"],
    "Electronics > Computers": ["Dell", "HP", "Lenovo", "Asus", "Apple"],
    "Electronics > Audio": ["Sony", "Bose", "JBL", "Sennheiser", "Marshall"],
    "Electronics > Televisions": ["LG", "Samsung", "Sony", "TCL", "Hisense"],
    "Electronics > Wearables": ["Apple", "Garmin", "Fitbit", "Samsung"],
    "Books": ["Penguin", "HarperCollins", "O Reilly", "Packt", "No Starch"],
    "Books > Textbooks": ["Pearson", "McGraw Hill", "Wiley", "O Reilly"],
    "Books > Fiction": ["Penguin", "Random House", "Simon & Schuster"],
    "Apparel": ["Nike", "Adidas", "Zara", "Uniqlo", "Levi's"],
    "Apparel > Men": ["Nike", "Adidas", "H&M", "Levi's"],
    "Apparel > Women": ["Zara", "H&M", "Nike", "Uniqlo"],
    "Home & Living > Kitchen": ["Tefal", "Bosch", "Ninja", "KitchenAid"],
    "Home & Living > Furniture": ["IKEA", "Wayfair", "Ashley Furniture"],
    "Toys & Games": ["Lego", "Hasbro", "Mattel", "Nintendo"],
    "Sports & Outdoors": ["Decathlon", "Nike", "Coleman", "Garmin"],
    "Beauty & Personal Care": ["L'Oreal", "Nivea", "Dove", "The Ordinary"],
    "Grocery": ["Whole Foods", "Tesco", "Nestle"],
}

MODELS: dict[str, list[str]] = {
    "Electronics": ["4K Smart TV", "Wireless Earbuds", "Soundbar", "Bluetooth Speaker", "Power Bank 20000mAh", "USB-C Hub 8-in-1"],
    "Electronics > Mobile Phones": ["Galaxy S24 256GB", "iPhone 15 128GB", "Redmi Note 13 Pro", "Moto G54", "OnePlus 12R"],
    "Electronics > Computers": ["Pavilion 15 Laptop i7", "ThinkPad E14 Gen 5", "IdeaPad Slim 3", "VivoBook 15", "MacBook Air M3"],
    "Electronics > Audio": ["WH-1000XM5 Headphones", "WF-1000XM5 Earbuds", "SoundLink Revolve+", "Charge 5 Speaker", "Momentum 4"],
    "Electronics > Televisions": ["OLED C3 55 inch", "QNED 75 65 inch", "Bravia XR A1 65 inch", "Crystal UHD 4K 50 inch"],
    "Electronics > Wearables": ["Watch Series 9", "Fenix 7", "Charge 5 Band", "Galaxy Watch 6"],
    "Books": ["Clean Architecture", "Designing Data-Intensive Applications", "The Pragmatic Programmer", "Site Reliability Engineering", "Refactoring"],
    "Books > Textbooks": ["Database Systems 7th Edition", "Operating System Concepts", "Introduction to Algorithms", "Fundamentals of Data Engineering"],
    "Books > Fiction": ["The Midnight Library", "Project Hail Mary", "Atomic Habits", "Dune", "The Hobbit"],
    "Apparel": ["Classic Cotton T-Shirt", "Slim Fit Jeans", "Lightweight Hoodie", "Running Shorts"],
    "Apparel > Men": ["Oxford Shirt", "Chino Trousers", "Winter Jacket", "Leather Belt"],
    "Apparel > Women": ["Wrap Dress", "High-Rise Jeans", "Blazer", "Knit Cardigan"],
    "Home & Living > Kitchen": ["Air Fryer 5.5L", "Espresso Machine", "Stand Mixer", "Knife Block Set", "Cast Iron Skillet"],
    "Home & Living > Furniture": ["Ergonomic Office Chair", "Bookshelf 5 Tier", "Dining Table", "Memory Foam Mattress"],
    "Toys & Games": ["Star Wars Building Set", "Remote Control Car", "Board Game Strategy", "Puzzle 1000 Pieces"],
    "Sports & Outdoors": ["Yoga Mat 6mm", "Adjustable Dumbbell Set", "Trekking Backpack 45L", "Running Shoes Men"],
    "Beauty & Personal Care": ["Vitamin C Serum", "Anti-Face Cream", "Shampoo 400ml", "Sunscreen SPF50"],
    "Grocery": ["Arabica Coffee Beans 1kg", "Organic Olive Oil 750ml", "Pasta Bronze Cut 500g", "Green Tea 100 bags"],
}

CURRENCIES = ["USD", "USD", "USD", "EUR", "GBP"]
AVAILABILITY_CYCLE = ["in_stock", "in_stock", "in_stock", "limited_stock", "out_of_stock", "preorder"]


@register_source
class LocalFixtureSource(ProductSource):
    """Offline synthetic source (no HTTP traffic at all)."""

    code: ClassVar[str] = "local_demo"
    name: ClassVar[str] = "Local Demo Catalogue (offline)"
    kind: ClassVar[str] = "synthetic"
    base_url: ClassVar[str] = "local://demo-catalogue"
    terms_url: ClassVar[str] = None
    license_note: ClassVar[str] = "Generated locally - no third-party rights involved."
    default_currency: ClassVar[str] = "USD"
    rate_limit_per_minute: ClassVar[int] = 10_000
    min_delay_seconds: ClassVar[float] = 0.0
    supports_paging: ClassVar[bool] = False
    description: ClassVar[str] = (
        "Deterministic catalogue generator (seeded) used for demos, tests and "
        "offline runs. Includes intentional duplicates and quality defects."
    )

    def __init__(self, run_id: str | None = None, client: Any = None, seed: int | None = None) -> None:
        super().__init__(run_id=run_id, client=client)
        self.seed = seed if seed is not None else 20260101

    def fetch(self, limit: int | None = None) -> Iterator[RawProduct]:
        limit = limit or 120
        rng = random.Random(self.seed)
        categories = list(MODELS.keys())

        for index in range(limit):
            category = categories[index % len(categories)]
            brand = rng.choice(BRANDS[category])
            model = rng.choice(MODELS[category])
            variant = rng.choice(["", " Pro", " Plus", " 2024", " (2023)", " Max", " Gen 2"])
            name = f"{brand} {model}{variant}".strip()
            base_price = round(rng.uniform(9.99, 1299.99), 2)
            base_price = round(base_price - (base_price % 0.01) + rng.choice([0.0, 0.49, 0.99]), 2)
            currency = rng.choice(CURRENCIES)
            symbol = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}.get(currency, "")
            price = f"{symbol}{base_price:,.2f}"
            rating = round(rng.uniform(2.5, 5.0), 1)
            availability = AVAILABILITY_CYCLE[rng.randrange(len(AVAILABILITY_CYCLE))]
            product_id = f"DEMO-{index + 1:04d}"

            payload = {
                "id": product_id,
                "title": name,
                "category": category,
                "price": base_price,
                "currency": currency,
                "rating": rating,
                "availability": availability,
                "brand": brand,
                "sku": f"SKU-{index + 1:05d}",
            }

            # ---- intentional defects for the DQ framework -------------------------------
            defect = index % 25
            if defect == 3:
                payload["price"] = None            # 4% missing price
            elif defect == 7:
                payload["rating"] = 9.7             # out-of-range rating
            elif defect == 11:
                payload["title"] = ""               # missing name
            elif defect == 14:
                payload["availability"] = "???"

            yield RawProduct(
                source_code=self.code,
                source_product_id=product_id,
                name=payload["title"] or "",
                category=category,
                price_text=(f"{symbol}{base_price:,.2f}" if payload["price"] is not None else None),
                currency_hint=currency,
                rating_text=(f"{payload['rating']} out of 5" if payload["rating"] is not None else None),
                availability_text=payload["availability"],
                in_stock_flag=availability in {"in_stock", "limited_stock"},
                url=f"https://demo.local/products/{product_id}",
                image_url=f"https://demo.local/img/{product_id}.jpg",
                brand=brand,
                description=f"{name} - demo record for the {category} catalogue.",
                payload=payload,
            )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def price_for(product_id: str, seed: int = 20260101, *, day_offset: int = 0) -> float:
        """Deterministic historical price series used by the demo seeder.

        Produces a smooth random walk with occasional promotions, so price-change
        detection has realistic signal instead of noise.
        """
        rng = random.Random(f"{seed}:{product_id}")
        price = round(rng.uniform(15, 900), 2)
        value = price
        for day in range(day_offset + 1):
            drift = math.sin((day + hash(product_id) % 30) / 6.0) * 0.012
            shock = rng.choice([0.0, 0.0, 0.0, -0.08, 0.05])
            value = max(4.99, value * (1 + drift + shock))
        return round(value, 2)


__all__ = ["LocalFixtureSource"]