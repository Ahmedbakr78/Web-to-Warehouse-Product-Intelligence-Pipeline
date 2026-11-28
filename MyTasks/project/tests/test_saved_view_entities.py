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


@pytest.fixture(scope="module")
def viewer_token():
    return create_access_token(3, role="viewer", email="viewer@example.com")


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


def _make_view(client, headers, name="pytest-crud", **overrides):
    payload = {"name": name, "entity": "products", "filters": {"category": "Books"}, **overrides}
    created = client.post("/api/v1/saved-views", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    return created.json()


def test_get_update_duplicate_default_lifecycle(client, admin_token):
    headers = auth(admin_token)
    view = _make_view(client, headers)
    view_id = view["view_id"]
    assert view["is_default"] is False
    assert "created_at" in view

    fetched = client.get(f"/api/v1/saved-views/{view_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "pytest-crud"

    updated = client.patch(
        f"/api/v1/saved-views/{view_id}",
        headers=headers,
        json={"description": "edited", "is_favorite": True, "visible_columns": ["name", "price"]},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["description"] == "edited"
    assert body["is_favorite"] is True
    assert body["visible_columns"] == ["name", "price"]
    # Untouched fields survive a partial update.
    assert body["filters"] == {"category": "Books"}

    clone = client.post(f"/api/v1/saved-views/{view_id}/duplicate", headers=headers)
    assert clone.status_code == 201
    clone_body = clone.json()
    assert clone_body["name"].startswith("pytest-crud (copy)")
    assert clone_body["filters"] == {"category": "Books"}
    assert clone_body["is_favorite"] is False
    clone_id = clone_body["view_id"]

    defaulted = client.post(f"/api/v1/saved-views/{view_id}/default", headers=headers)
    assert defaulted.status_code == 200
    assert defaulted.json()["is_default"] is True
    # The default sorts first in the list.
    listed = client.get("/api/v1/saved-views?entity=products", headers=headers).json()
    assert listed[0]["view_id"] == view_id

    assert client.delete(f"/api/v1/saved-views/{view_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/saved-views/{clone_id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/saved-views/{view_id}", headers=headers).status_code == 404


def test_update_rejects_name_clash(client, admin_token):
    headers = auth(admin_token)
    first = _make_view(client, headers, name="pytest-clash-a")
    second = _make_view(client, headers, name="pytest-clash-b")
    clash = client.patch(
        f"/api/v1/saved-views/{second['view_id']}", headers=headers, json={"name": "pytest-clash-a"}
    )
    assert clash.status_code == 409
    assert client.delete(f"/api/v1/saved-views/{first['view_id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/saved-views/{second['view_id']}", headers=headers).status_code == 200


def test_private_views_are_invisible_to_other_users(client, admin_token, viewer_token):
    admin_headers, viewer_headers = auth(admin_token), auth(viewer_token)
    view = _make_view(client, admin_headers, name="pytest-private")
    view_id = view["view_id"]

    assert client.get(f"/api/v1/saved-views/{view_id}", headers=viewer_headers).status_code == 404
    assert client.post(f"/api/v1/saved-views/{view_id}/use", headers=viewer_headers).status_code == 404
    assert client.post(f"/api/v1/saved-views/{view_id}/favorite", headers=viewer_headers).status_code == 404
    assert client.patch(f"/api/v1/saved-views/{view_id}", headers=viewer_headers, json={"name": "x"}).status_code in (403, 404)
    assert client.delete(f"/api/v1/saved-views/{view_id}", headers=viewer_headers).status_code in (403, 404)

    # Sharing opens read + use, but never mutation.
    assert client.patch(f"/api/v1/saved-views/{view_id}", headers=admin_headers, json={"is_shared": True}).status_code == 200
    assert client.get(f"/api/v1/saved-views/{view_id}", headers=viewer_headers).status_code == 200
    used = client.post(f"/api/v1/saved-views/{view_id}/use", headers=viewer_headers)
    assert used.status_code == 200
    assert used.json()["use_count"] >= 1
    assert client.patch(f"/api/v1/saved-views/{view_id}", headers=viewer_headers, json={"name": "x"}).status_code == 403

    assert client.delete(f"/api/v1/saved-views/{view_id}", headers=admin_headers).status_code == 200


def test_saved_view_mutations_are_audited(client, admin_token):
    headers = auth(admin_token)
    view = _make_view(client, headers, name="pytest-audit")
    view_id = view["view_id"]
    client.patch(f"/api/v1/saved-views/{view_id}", headers=headers, json={"description": "audit me"})
    trail = client.get("/api/v1/audit?days=1&page_size=50", headers=headers).json()
    actions = {item["action"] for item in trail["items"] if item["entity_type"] == "saved_view"}
    assert "saved_view.created" in actions
    assert "saved_view.updated" in actions
    assert client.delete(f"/api/v1/saved-views/{view_id}", headers=headers).status_code == 200
