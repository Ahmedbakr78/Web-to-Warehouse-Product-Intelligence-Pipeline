"""Query-lab hardening: history, snippets, secret tables and server-side limits."""

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


def test_execute_records_history(client, admin_token):
    before = client.get("/api/v1/queries/history?limit=200", headers=auth(admin_token)).json()
    response = client.post(
        "/api/v1/queries/execute",
        headers=auth(admin_token),
        json={"sql": "SELECT canonical_name FROM vw_product_current LIMIT 3", "limit": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json()["row_count"] >= 1
    after = client.get("/api/v1/queries/history?limit=200", headers=auth(admin_token)).json()
    assert len(after) == len(before) + 1
    latest = after[0]
    assert "vw_product_current" in latest["sql"]
    assert latest["row_count"] >= 1
    assert latest["is_saved"] is False


def test_secret_tables_are_forbidden(client, admin_token):
    for sql in [
        "SELECT email, hashed_password FROM app_user LIMIT 1",
        "SELECT * FROM app_api_key",
        "WITH s AS (SELECT * FROM app_session) SELECT * FROM s",
        "select secret from app_webhook",
    ]:
        response = client.post("/api/v1/queries/execute", headers=auth(admin_token), json={"sql": sql})
        assert response.status_code == 422, sql
        assert "not allowed" in response.text


def test_similar_names_are_not_blocked(client, admin_token):
    """The guard matches whole table names, not substrings of view names."""
    response = client.post(
        "/api/v1/queries/execute",
        headers=auth(admin_token),
        json={"sql": "SELECT COUNT(*) AS n FROM vw_product_current"},
    )
    assert response.status_code == 200, response.text


def test_snippet_lifecycle(client, admin_token):
    headers = auth(admin_token)
    client.post("/api/v1/queries/execute", headers=headers, json={"sql": "SELECT 1 AS one"})
    history = client.get("/api/v1/queries/history?limit=5", headers=headers).json()
    entry_id = history[0]["history_id"]

    saved = client.post(f"/api/v1/queries/history/{entry_id}/save", headers=headers, json={"name": "pytest one"})
    assert saved.status_code == 200
    assert saved.json()["is_saved"] is True
    assert saved.json()["name"] == "pytest one"

    snippets = client.get("/api/v1/queries/history?saved_only=true", headers=headers).json()
    assert any(item["history_id"] == entry_id for item in snippets)

    # Clearing history keeps pinned snippets.
    cleared = client.delete("/api/v1/queries/history", headers=headers)
    assert cleared.status_code == 200
    remaining = client.get("/api/v1/queries/history?limit=200", headers=headers).json()
    assert all(item["is_saved"] for item in remaining)
    assert any(item["history_id"] == entry_id for item in remaining)

    assert client.delete(f"/api/v1/queries/history/{entry_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/queries/history/{entry_id}", headers=headers).status_code == 404


def test_history_is_per_user(client, admin_token, viewer_token):
    admin_headers, viewer_headers = auth(admin_token), auth(viewer_token)
    client.post("/api/v1/queries/execute", headers=admin_headers, json={"sql": "SELECT 2 AS two"})
    viewer_history = client.get("/api/v1/queries/history?limit=200", headers=viewer_headers).json()
    admin_history = client.get("/api/v1/queries/history?limit=200", headers=admin_headers).json()
    admin_ids = {item["history_id"] for item in admin_history}
    assert all(item["history_id"] not in admin_ids for item in viewer_history)
    # A viewer cannot touch an admin entry.
    if admin_history:
        target = admin_history[0]["history_id"]
        assert client.delete(f"/api/v1/queries/history/{target}", headers=viewer_headers).status_code == 404
