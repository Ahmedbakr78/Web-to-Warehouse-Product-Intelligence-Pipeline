"""Market analytics: price buckets, cross-source spread, movers and lifecycle timeline."""

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


def test_market_endpoints_reject_anonymous_callers(client):
    for path in (
        "/api/v1/analytics/price-buckets",
        "/api/v1/analytics/source-spread",
        "/api/v1/analytics/category-movers",
        "/api/v1/analytics/event-timeline",
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
