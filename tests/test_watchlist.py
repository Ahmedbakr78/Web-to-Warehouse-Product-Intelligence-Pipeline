"""Personal product watchlist: toggle, isolation and validation."""

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


def test_watchlist_starts_empty(client, admin_token):
    payload = client.get("/api/v1/users/me/watchlist", headers=auth(admin_token)).json()
    assert payload["count"] == 0
    assert payload["products"] == []


def test_watch_add_is_idempotent_and_resolves_products(client, admin_token):
    first = client.post("/api/v1/users/me/watchlist/1", headers=auth(admin_token))
    assert first.status_code == 200, first.text
    assert first.json()["watched"] is True

    second = client.post("/api/v1/users/me/watchlist/1", headers=auth(admin_token))
    assert second.json()["count"] == 1

    listing = client.get("/api/v1/users/me/watchlist", headers=auth(admin_token)).json()
    assert listing["count"] == 1
    assert listing["product_ids"] == [1]
    assert listing["products"][0]["product_id"] == 1
    assert "canonical_name" in listing["products"][0]


def test_watch_rejects_unknown_products(client, admin_token):
    response = client.post("/api/v1/users/me/watchlist/999999999", headers=auth(admin_token))
    assert response.status_code == 404


def test_unwatch_is_idempotent(client, admin_token):
    assert client.delete("/api/v1/users/me/watchlist/1", headers=auth(admin_token)).status_code == 200
    again = client.delete("/api/v1/users/me/watchlist/1", headers=auth(admin_token)).json()
    assert again["watched"] is False
    assert client.get("/api/v1/users/me/watchlist", headers=auth(admin_token)).json()["count"] == 0


def test_viewers_can_keep_a_watchlist(client, viewer_token):
    assert client.post("/api/v1/users/me/watchlist/1", headers=auth(viewer_token)).status_code == 200
    assert client.get("/api/v1/users/me/watchlist", headers=auth(viewer_token)).json()["count"] == 1
    client.delete("/api/v1/users/me/watchlist/1", headers=auth(viewer_token))
