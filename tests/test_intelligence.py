"""Tests for the intelligence briefing (v1.11).

The briefing is a composition of existing analytical services, so these tests
assert the contract the UI depends on: authentication, the headline shape, a
bounded action queue, and deep links that stay inside the app.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(clean_database):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def token() -> str:
    return create_access_token(1, role="admin", email="admin@example.com")


def test_briefing_requires_authentication(client):
    assert client.get("/api/v1/intelligence/briefing").status_code == 401


def test_briefing_returns_a_complete_contract(client, token):
    response = client.get(
        "/api/v1/intelligence/briefing?days=30&limit=4",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert set(payload) >= {
        "generated_at",
        "window_days",
        "headline",
        "opportunities",
        "risks",
        "category_signals",
        "freshness",
        "best_value",
        "actions",
    }
    assert payload["window_days"] == 30

    headline = payload["headline"]
    for key in (
        "observations",
        "canonical_products",
        "sources_reporting",
        "price_changes",
        "new_products",
        "removed_products",
        "opportunities",
        "risks",
    ):
        assert isinstance(headline[key], int)

    # Sections are bounded by the limit and every item can be acted on.
    assert len(payload["opportunities"]) <= 8
    assert len(payload["risks"]) <= 12
    assert len(payload["actions"]) <= 8
    for item in [*payload["opportunities"], *payload["risks"]]:
        assert item["title"] and item["detail"] and item["action"]
        assert item["link"].startswith("/")
        assert item["severity"] in {"critical", "high", "medium", "low"}

    freshness = payload["freshness"]
    assert freshness["sources"] >= 0
    assert isinstance(freshness["stale"], list)


def test_briefing_rejects_an_out_of_range_window(client, token):
    response = client.get(
        "/api/v1/intelligence/briefing?days=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
