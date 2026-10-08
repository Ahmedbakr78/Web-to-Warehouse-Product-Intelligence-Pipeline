"""Second-wave ingestion sources: registration, mapping and failure tolerance.

All network access is stubbed: these tests pin the parsing and contract
behaviour, never the live endpoints (compliance and liveness were verified by
hand before the code was written - see each module docstring).
"""

from __future__ import annotations

import pytest

from app.ingestion.base import list_sources

pytestmark = pytest.mark.integration

CODES = {
    "freeapi_products",
    "predic8_grocery",
    "sampleapis_coffee",
    "sampleapis_switch",
    "mealdb_meals",
    "cocktaildb_drinks",
}


class StubClient:
    """Records calls and serves canned payloads per URL fragment."""

    def __init__(self, routes: dict[str, object], fail_on: tuple[str, ...] = ()):
        self.routes = routes
        self.fail_on = fail_on
        self.calls = 0

    def get_json(self, url: str, params: dict | None = None):
        self.calls += 1
        if any(marker in url for marker in self.fail_on):
            raise ConnectionError(f"stub failure for {url}")
        # Longest fragment first: a detail URL also contains its listing prefix.
        for fragment in sorted(self.routes, key=len, reverse=True):
            if fragment in url:
                return self.routes[fragment]
        raise AssertionError(f"unexpected URL: {url}")


def test_new_sources_are_registered_with_compliance_metadata():
    codes = {source["code"] for source in list_sources()}
    assert codes >= CODES
    for source in list_sources():
        if source["code"] not in CODES:
            continue
        assert source["name"]
        assert source["kind"] == "api"
        assert source["base_url"].startswith("https://")
        assert source["rate_limit_per_minute"] > 0
        assert source["min_delay_seconds"] >= 0


def test_freeapi_maps_price_brand_and_was_now():
    from app.ingestion.sources.freeapi import FreeApiProductsSource

    page = {
        "data": {
            "data": [
                {
                    "id": 7,
                    "title": "Stub Phone",
                    "description": "A phone",
                    "price": 549,
                    "discountPercentage": 10,
                    "rating": 4.5,
                    "stock": 12,
                    "brand": "StubCo",
                    "category": "smartphones",
                    "thumbnail": "https://example.com/t.png",
                    "images": [],
                }
            ],
            "nextPage": False,
        }
    }
    source = FreeApiProductsSource(client=StubClient({"randomproducts": page}))
    rows = list(source.fetch(limit=10))
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "Stub Phone"
    assert row.price_text == "549.0"
    assert row.list_price_text == "610.00"
    assert row.brand == "StubCo"
    assert row.rating_text == "4.5"
    assert row.in_stock_flag is True


def test_freeapi_paginates_until_exhausted():
    from app.ingestion.sources.freeapi import FreeApiProductsSource

    def item(index: int) -> dict:
        return {"id": index, "title": f"Item {index}", "price": 10 + index}

    first = {"data": {"data": [item(1), item(2)], "nextPage": True}}
    second = {"data": {"data": [item(1), item(3)], "nextPage": False}}

    class PagedStub(StubClient):
        def get_json(self, url: str, params: dict | None = None):
            self.calls += 1
            return second if (params or {}).get("page") == 2 else first

    source = FreeApiProductsSource(client=PagedStub({}))
    rows = list(source.fetch(limit=10))
    assert [row.source_product_id for row in rows] == ["1", "2", "3"]


def test_predic8_resolves_euro_detail():
    from app.ingestion.sources.predic8 import Predic8GrocerySource

    listing = {"products": [{"id": 1, "name": "Banana", "self_link": "/shop/v2/products/1"}]}
    detail = {
        "price": 0.99,
        "vendors": [{"name": "Exotics Fruit Lair Ltd."}],
        "image_link": "/shop/v2/products/1/image",
    }
    routes = {"/shop/v2/products/": listing, "/shop/v2/products/1": detail}
    source = Predic8GrocerySource(client=StubClient(routes))
    rows = list(source.fetch(limit=10))
    assert len(rows) == 1
    row = rows[0]
    assert row.price_text == "0.99"
    assert row.currency_hint == "EUR"
    assert row.category == "Grocery"
    assert "Exotics" in (row.description or "")


def test_predic8_survives_detail_failure():
    from app.ingestion.sources.predic8 import Predic8GrocerySource

    listing = {"products": [{"id": 1, "name": "Banana", "self_link": "/shop/v2/products/1"}]}
    source = Predic8GrocerySource(
        client=StubClient({"/shop/v2/products/": listing}, fail_on=("/shop/v2/products/1",))
    )
    rows = list(source.fetch(limit=10))
    assert len(rows) == 1
    assert rows[0].price_text is None
    assert source.errors


def test_coffee_merges_hot_and_iced():
    from app.ingestion.sources.sampleapis_coffee import SampleApisCoffeeSource

    hot = [{"id": 1, "title": "Latte", "description": "Milky", "ingredients": ["espresso", "milk"]}]
    iced = [{"id": 1, "title": "Iced Latte", "description": "Cold", "ingredients": ["espresso", "ice"]}]
    source = SampleApisCoffeeSource(client=StubClient({"/coffee/hot": hot, "/coffee/iced": iced}))
    rows = list(source.fetch(limit=10))
    assert [row.name for row in rows] == ["Latte", "Iced Latte"]
    assert rows[0].category == "Coffee & Tea"
    assert "espresso" in (rows[0].description or "")


def test_switch_maps_studios_and_genres():
    from app.ingestion.sources.sampleapis_switch import SampleApisSwitchSource

    catalogue = [
        {
            "id": 9,
            "name": "Stub Quest",
            "genre": ["RPG"],
            "developers": ["Stub Studio"],
            "publishers": ["Stub Pub"],
            "releaseDates": {"NorthAmerica": "2020-01-01"},
        }
    ]
    source = SampleApisSwitchSource(client=StubClient({"/switch/games": catalogue}))
    rows = list(source.fetch(limit=10))
    assert len(rows) == 1
    row = rows[0]
    assert row.brand == "Stub Studio"
    assert row.category == "Video Games"
    assert "RPG" in (row.description or "")


def test_mealdb_discovers_categories_then_meals():
    from app.ingestion.sources.mealdb import MealDbMealsSource

    categories = {"meals": [{"strCategory": "Seafood"}, {"strCategory": "Vegan"}]}
    meals = {"meals": [{"idMeal": "1", "strMeal": "Grilled Fish", "strMealThumb": "https://e.com/1.png"}]}
    client = StubClient({"list.php": categories, "filter.php": meals})
    source = MealDbMealsSource(client=client)
    rows = list(source.fetch(limit=10))
    # Both categories are queried (1 list + 2 filter calls); the identical
    # meal id dedupes to a single row.
    assert client.calls == 3
    assert len(rows) == 1
    assert all(row.category == "Food" for row in rows)
    assert rows[0].image_url == "https://e.com/1.png"


def test_cocktaildb_covers_all_three_options():
    from app.ingestion.sources.cocktaildb import CocktailDbDrinksSource

    menu = {"drinks": [{"idDrink": "1", "strDrink": "Margarita", "strDrinkThumb": "https://e.com/m.png"}]}
    client = StubClient({"filter.php": menu})
    source = CocktailDbDrinksSource(client=client)
    rows = list(source.fetch(limit=10))
    # All three alcohol options are queried; the identical drink id dedupes.
    assert client.calls == 3
    assert len(rows) == 1
    assert all(row.category == "Beverages" for row in rows)
