"""Saved views accept every entity the dashboard Builder can compose."""

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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


ENTITIES = [
    "products",
    "changes",
    "runs",
    "quality",
    "catalog",
    "sources",
    "new",
    "removed",
    "movers",
    "categories",
    "brands",
    "availability",
]


def test_every_builder_entity_saves(client, admin_token):
    headers = auth(admin_token)
    for entity in ENTITIES:
        created = client.post(
            "/api/v1/saved-views",
            headers=headers,
            json={"name": f"pytest-{entity}", "entity": entity, "filters": {}},
        )
        assert created.status_code == 201, (entity, created.text)
        view_id = created.json()["view_id"]
        assert client.delete(f"/api/v1/saved-views/{view_id}", headers=headers).status_code == 200


def test_unknown_entity_is_still_rejected(client, admin_token):
    response = client.post(
        "/api/v1/saved-views",
        headers=auth(admin_token),
        json={"name": "pytest-bogus", "entity": "nope", "filters": {}},
    )
    assert response.status_code == 422
