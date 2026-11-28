"""Market analytics: buckets, spread, movers, lifecycle, anomalies and risk."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client(database):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def admin_token():
    return create_access_token(1, role="admin", email="admin@example.com")


@pytest.fixture(scope="module")
def viewer_token():
    return create_access_token(3, role="viewer", email="viewer@example.com")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_price_buckets_cover_the_catalogue(client, viewer_token):
    rows = client.get("/api/v1/analytics/price-buckets", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    keys = {row["bucket"] for row in rows}
    assert keys <= {"under_10", "from_10_to_50", "from_50_to_200", "from_200_to_1000", "over_1000", "unknown"}
    assert sum(row["listings"] for row in rows) > 0
    for row in rows:
        assert set(row) >= {"bucket", "listings", "in_stock_count", "avg_rating"}


def test_source_spread_ranks_multi_source_products(client, viewer_token):
    rows = client.get("/api/v1/analytics/source-spread?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    for row in rows:
        assert row["sources"] > 1
        assert row["min_price_usd"] <= row["avg_price_usd"] <= row["max_price_usd"]
        assert row["spread_pct"] >= 0
        assert set(row) >= {"canonical_name", "sources", "min_price_usd", "max_price_usd", "spread_pct"}


def test_category_movers_rank_by_magnitude(client, viewer_token):
    rows = client.get("/api/v1/analytics/category-movers?days=120&limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    magnitudes = [row["avg_abs_change_pct"] for row in rows]
    assert magnitudes == sorted(magnitudes, reverse=True)
    for row in rows:
        assert row["increases"] + row["decreases"] <= row["changes"]
        assert set(row) >= {"category_name", "changes", "avg_abs_change_pct", "max_abs_change_pct"}


def test_event_timeline_merges_lifecycle_and_price_changes(client, viewer_token):
    rows = client.get("/api/v1/analytics/event-timeline?days=120", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    dates = [str(row["full_date"]) for row in rows]
    assert dates == sorted(dates)
    assert sum(row["price_changes"] for row in rows) > 0
    assert sum(row["total_events"] for row in rows) > 0
    for row in rows:
        assert set(row) >= {
            "full_date",
            "new_products",
            "removed_products",
            "recategorised",
            "total_events",
            "price_changes",
        }


def test_price_anomalies_are_ranked_by_z_score(client, viewer_token):
    rows = client.get("/api/v1/analytics/price-anomalies?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    scores = [abs(row["z_score"]) for row in rows]
    assert scores == sorted(scores, reverse=True)
    assert all(score >= 2.0 for score in scores)
    for row in rows:
        assert set(row) >= {
            "product_id",
            "canonical_name",
            "category_name",
            "source_code",
            "price_usd",
            "category_mean_usd",
            "z_score",
        }


def test_source_overlap_pairs_are_unique_and_ordered(client, viewer_token):
    rows = client.get("/api/v1/analytics/source-overlap", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    pairs = [(row["source_a"], row["source_b"]) for row in rows]
    assert len(pairs) == len(set(pairs))
    assert all(a < b for a, b in pairs)
    counts = [row["shared_products"] for row in rows]
    assert counts == sorted(counts, reverse=True)
    assert all(count > 0 for count in counts)


def test_data_freshness_covers_every_source(client, viewer_token):
    rows = client.get("/api/v1/analytics/data-freshness?stale_days=7", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    for row in rows:
        assert set(row) >= {
            "source_code",
            "products",
            "active_products",
            "last_seen_at",
            "stale_products",
            "stale_pct",
        }
        assert row["stale_products"] <= row["products"]
        assert 0 <= (row["stale_pct"] or 0) <= 100


def test_inventory_risk_orders_by_stock_pressure(client, viewer_token):
    rows = client.get("/api/v1/analytics/inventory-risk?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    counts = [row["out_of_stock_count"] for row in rows]
    assert counts == sorted(counts, reverse=True)
    for row in rows:
        assert set(row) >= {
            "category_name",
            "observations",
            "in_stock_pct",
            "out_of_stock_count",
            "price_increases",
        }


def test_currency_exposure_covers_active_listings(client, viewer_token):
    rows = client.get("/api/v1/analytics/currency-exposure", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    counts = [row["listings"] for row in rows]
    assert counts == sorted(counts, reverse=True)
    assert sum(counts) > 0
    for row in rows:
        assert set(row) >= {"currency", "listings", "sources", "in_stock_count", "avg_price_usd"}


def test_best_value_is_ranked_by_rating_per_dollar(client, viewer_token):
    rows = client.get("/api/v1/analytics/best-value?limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list)
    scores = [row["value_score"] for row in rows]
    assert scores == sorted(scores, reverse=True)
    for row in rows:
        assert row["rating"] >= 4.0
        assert (row["rating_count"] or 0) >= 10
        assert row["price_usd"] > 0
        assert set(row) >= {"product_id", "canonical_name", "price_usd", "rating", "value_score"}


def test_brand_momentum_ranks_winners_first(client, viewer_token):
    rows = client.get("/api/v1/analytics/brand-momentum?days=120&limit=20", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    avgs = [row["avg_change_pct"] for row in rows]
    assert avgs == sorted(avgs, reverse=True)
    for row in rows:
        assert row["increases"] + row["decreases"] <= row["changes"]
        assert row["brand"]
        assert set(row) >= {"brand", "changes", "avg_change_pct", "avg_abs_change_pct"}


def test_weekday_pattern_orders_monday_first(client, viewer_token):
    rows = client.get("/api/v1/analytics/weekday-pattern?days=120", headers=auth(viewer_token)).json()
    assert isinstance(rows, list) and rows
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    names = [row["day_name"] for row in rows]
    assert names == sorted(names, key=order.index)
    assert sum(row["changes"] for row in rows) > 0
    for row in rows:
        assert set(row) >= {"day_name", "is_weekend", "changes", "increases", "decreases", "avg_abs_change_pct"}


def test_market_endpoints_reject_anonymous_callers(client):
    for path in (
        "/api/v1/analytics/price-buckets",
        "/api/v1/analytics/source-spread",
        "/api/v1/analytics/category-movers",
        "/api/v1/analytics/event-timeline",
        "/api/v1/analytics/price-anomalies",
        "/api/v1/analytics/source-overlap",
        "/api/v1/analytics/data-freshness",
        "/api/v1/analytics/inventory-risk",
        "/api/v1/analytics/currency-exposure",
        "/api/v1/analytics/best-value",
        "/api/v1/analytics/brand-momentum",
        "/api/v1/analytics/weekday-pattern",
    ):
        response = client.get(path)
        assert response.status_code == 401
        # RFC 7235: the 401 names the scheme so clients can tell an expired
        # session from a forbidden role without parsing the body.
        assert response.headers.get("www-authenticate") == 'Bearer realm="pip"'


def test_expired_token_is_reported_as_expired(client):
    import jwt as pyjwt

    from app.core.config import settings

    expired = pyjwt.encode(
        {
            "sub": "1",
            "role": "admin",
            "type": "access",
            "iss": "product-intelligence-pipeline",
            "exp": 1,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get("/api/v1/analytics/price-buckets", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["details"].get("reason") == "expired"
