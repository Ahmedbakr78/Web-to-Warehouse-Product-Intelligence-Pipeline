"""Tests for the v1.3 platform features: feature catalogue, account self-service, builder API."""

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


# --------------------------------------------------------------------------------------
# Feature catalogue
# --------------------------------------------------------------------------------------
def test_meta_features_catalogue(client):
    payload = client.get("/api/v1/meta/features").json()
    assert payload["total_groups"] >= 10
    assert payload["total_features"] >= 60
    keys = {group["key"] for group in payload["groups"]}
    assert {"ingestion", "cleaning", "dedupe", "warehouse", "security", "dashboard"} <= keys
    for group in payload["groups"]:
        assert group["title"] and group["icon"] and group["summary"]
        assert group["feature_count"] == len(group["features"])
        for feature in group["features"]:
            assert feature["name"]


def test_meta_includes_generated_feature_list(client):
    meta = client.get("/api/v1/meta").json()
    assert len(meta["features"]) >= 60
    assert meta["feature_groups"] >= 10


# --------------------------------------------------------------------------------------
# Own-activity feed
# --------------------------------------------------------------------------------------
def test_audit_me_requires_authentication(client):
    assert client.get("/api/v1/audit/me").status_code == 401


def test_audit_me_returns_own_activity_only(client, admin_token):
    # A fresh user generates its own, private audit trail.
    _disposable_user(client, admin_token, "audit-me@example.com")
    login = client.post(
        "/api/v1/auth/login", json={"email": "audit-me@example.com", "password": "Disposable@12345"}
    ).json()
    token = {"Authorization": f"Bearer {login['access_token']}"}
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=token,
        json={"current_password": "Disposable@12345", "new_password": "Disposable@67890"},
    )
    assert changed.status_code == 200
    feed = client.get("/api/v1/audit/me", headers=token).json()
    assert feed["total"] >= 1
    actions = {item["action"] for item in feed["items"]}
    assert "auth.change_password" in actions
    # The admin's feed is a different, independent stream: it must not contain the
    # other account's entries. (Totals are unrelated, so compare identities, not counts.)
    admin_feed = client.get("/api/v1/audit/me", headers=auth(admin_token)).json()
    assert all(item["user_email"] != "audit-me@example.com" for item in admin_feed["items"])


def test_audit_me_pagination_and_window(client, admin_token):
    response = client.get("/api/v1/audit/me?page=1&page_size=2&days=3650", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["page_size"] == 2
    assert len(payload["items"]) <= 2
    assert payload["window_days"] == 3650


# --------------------------------------------------------------------------------------
# Account data export + deletion
# --------------------------------------------------------------------------------------
def test_export_my_account_data(client, admin_token):
    response = client.get("/api/v1/users/me/export", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["email"] == "admin@example.com"
    for section in ("api_keys", "saved_views", "alert_rules", "notifications", "recent_activity"):
        assert isinstance(payload[section], list)
    assert payload["exported_at"]


def test_export_requires_authentication(client):
    assert client.get("/api/v1/users/me/export").status_code == 401


def _disposable_user(client, admin_token, email: str) -> None:
    created = client.post(
        "/api/v1/users",
        headers=auth(admin_token),
        json={
            "email": email,
            "full_name": "Disposable User",
            "password": "Disposable@12345",
            "role": "viewer",
        },
    )
    assert created.status_code == 201, created.text


def test_delete_my_account_requires_password(client, admin_token):
    _disposable_user(client, admin_token, "disposable-a@example.com")
    login = client.post(
        "/api/v1/auth/login", json={"email": "disposable-a@example.com", "password": "Disposable@12345"}
    ).json()
    token = {"Authorization": f"Bearer {login['access_token']}"}
    wrong = client.request("DELETE", "/api/v1/users/me", headers=token, json={"password": "Wrong@123456"})
    assert wrong.status_code == 401
    gone = client.request("DELETE", "/api/v1/users/me", headers=token, json={"password": "Disposable@12345"})
    assert gone.status_code == 200
    assert "deleted" in gone.json()["message"].lower()
    # The account can no longer authenticate.
    relogin = client.post(
        "/api/v1/auth/login", json={"email": "disposable-a@example.com", "password": "Disposable@12345"}
    )
    assert relogin.status_code == 401


def test_delete_me_rejects_empty_password(client, admin_token):
    _disposable_user(client, admin_token, "disposable-b@example.com")
    login = client.post(
        "/api/v1/auth/login", json={"email": "disposable-b@example.com", "password": "Disposable@12345"}
    ).json()
    token = {"Authorization": f"Bearer {login['access_token']}"}
    response = client.request("DELETE", "/api/v1/users/me", headers=token, json={"password": ""})
    assert response.status_code == 422


# --------------------------------------------------------------------------------------
# Builder schema
# --------------------------------------------------------------------------------------
def test_builder_schema_lists_entities(client, admin_token):
    response = client.get("/api/v1/builder/schema", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    keys = {entity["entity"] for entity in payload["entities"]}
    assert {"products", "price_changes", "new_products", "removed_products"} <= keys
    assert {operator["operator"] for operator in payload["operators"]} >= {
        "eq",
        "contains",
        "between",
        "in",
        "empty",
    }
    assert "avg" in payload["aggregates"]


def test_builder_requires_authentication_and_query_right(client):
    assert client.get("/api/v1/builder/schema").status_code == 401


def test_builder_schema_allows_viewers(client, viewer_token):
    assert client.get("/api/v1/builder/schema", headers=auth(viewer_token)).status_code == 200


# --------------------------------------------------------------------------------------
# Builder query
# --------------------------------------------------------------------------------------
def test_builder_query_with_filters_and_sort(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "columns": ["canonical_name", "category_name", "price_usd", "rating"],
            "filters": [{"column": "category_name", "operator": "contains", "value": "Fiction"}],
            "sort": [{"column": "price_usd", "direction": "desc"}],
            "limit": 10,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["entity"] == "products"
    assert set(payload["columns"]) == {"canonical_name", "category_name", "price_usd", "rating"}
    assert payload["total"] >= 1
    assert payload["sql_preview"].startswith("SELECT")
    assert payload["duration_ms"] >= 0


def test_builder_query_group_by_with_aggregates(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "group_by": ["category_name"],
            "aggregates": [
                {"function": "count"},
                {"function": "avg", "column": "price_usd", "alias": "avg_price"},
            ],
            "sort": [{"column": "avg_price", "direction": "desc"}],
            "limit": 20,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["columns"][0] == "category_name"
    assert "avg_price" in payload["columns"]
    assert payload["row_count"] >= 1
    prices = [row[payload["columns"].index("avg_price")] for row in payload["rows"]]
    assert prices == sorted(prices, key=lambda value: (value is not None, value), reverse=True)


def test_builder_query_all_operators(client, admin_token):
    cases = [
        {"column": "price_usd", "operator": "between", "value": 1, "value2": 100000},
        {"column": "brand", "operator": "in", "value": ["Penguin"]},
        {"column": "discount_pct", "operator": "empty"},
        {"column": "discount_pct", "operator": "not_empty"},
        {"column": "canonical_name", "operator": "starts_with", "value": "The"},
        {"column": "canonical_name", "operator": "ends_with", "value": "Pro"},
        {"column": "canonical_name", "operator": "not_contains", "value": "zzz"},
        {"column": "rating", "operator": "gte", "value": 0},
        {"column": "rating", "operator": "ne", "value": -1},
    ]
    for flt in cases:
        response = client.post(
            "/api/v1/builder/query",
            headers=auth(admin_token),
            json={"entity": "products", "columns": ["canonical_name"], "filters": [flt], "limit": 5},
        )
        assert response.status_code == 200, flt


def test_builder_query_rejects_unknown_entity(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={"entity": "dim_user_secret", "limit": 5},
    )
    assert response.status_code in (400, 422)
    assert "unknown entity" in response.text


def test_builder_query_rejects_unknown_column_and_operator(client, admin_token):
    bad_column = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={"entity": "products", "columns": ["password_hash"], "limit": 5},
    )
    assert bad_column.status_code == 422
    assert "unknown select column" in bad_column.json()["message"]
    bad_operator = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "filters": [{"column": "brand", "operator": "drop", "value": "x"}],
            "limit": 5,
        },
    )
    assert bad_operator.status_code == 422


def test_builder_query_in_requires_list_values(client, admin_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(admin_token),
        json={
            "entity": "products",
            "filters": [{"column": "brand", "operator": "in", "value": "not-a-list"}],
            "limit": 5,
        },
    )
    assert response.status_code == 422


def test_builder_query_viewer_can_read(client, viewer_token):
    response = client.post(
        "/api/v1/builder/query",
        headers=auth(viewer_token),
        json={"entity": "source_coverage", "columns": ["source_name", "observations"], "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["row_count"] >= 1
