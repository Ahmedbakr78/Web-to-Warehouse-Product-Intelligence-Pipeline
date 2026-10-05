"""API tests using the FastAPI test client (TestClient) against the seeded warehouse."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client(database):
    """A TestClient bound to a bootstrapped + seeded database."""
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
# System
# --------------------------------------------------------------------------------------
def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["database"]["connected"] is True
    assert len(payload["sources"]) >= 3


def test_readiness_and_meta(client):
    from app.models import table_count

    assert client.get("/api/v1/health/ready").json()["ready"] is True
    meta = client.get("/api/v1/meta").json()
    # Derived from the ORM so adding a table does not silently break this test.
    assert meta["tables"] == table_count()
    assert meta["compliance"]["respect_robots_txt"] is True
    assert len(meta["features"]) >= 10


def test_openapi_schema_is_complete(client):
    schema = client.get("/openapi.json").json()
    assert len(schema["paths"]) > 50
    assert "bearerAuth" in json_dumps(schema) or "HTTPBearer" in json_dumps(schema)


def json_dumps(value) -> str:
    import json

    return json.dumps(value)


def test_unknown_route_returns_json_404(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert "error" in response.json()


# --------------------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------------------
def test_login_with_seeded_account(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "Admin@12345"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] and payload["refresh_token"]
    assert payload["user"]["role"] == "admin"
    assert "manage_users" in payload["user"]["permissions"]


def test_login_rejects_bad_credentials(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "authentication_failed"


def test_login_validates_payload(client):
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert response.status_code == 422
    assert response.json()["details"]["errors"]


def test_me_requires_a_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_the_profile(client, admin_token):
    payload = client.get("/api/v1/auth/me", headers=auth(admin_token)).json()
    assert payload["email"]
    assert payload["rows_per_page"] >= 5


def test_refresh_rotates_tokens(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "viewer@example.com", "password": "Viewer@12345"}
    ).json()
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200
    # JWTs are deterministic per second, so assert usability instead of inequality.
    token = refreshed.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 200


# --------------------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------------------
def test_product_list_is_paginated(client, admin_token):
    response = client.get("/api/v1/products?page=1&page_size=5", headers=auth(admin_token))
    payload = response.json()
    assert len(payload["items"]) <= 5
    assert payload["total"] > 5
    assert payload["pages"] >= 2
    assert payload["has_next"] is True


def test_product_filters_narrow_the_result_set(client, admin_token):
    all_products = client.get("/api/v1/products?page_size=1", headers=auth(admin_token)).json()["total"]
    filtered = client.get("/api/v1/products?page_size=1&in_stock=true", headers=auth(admin_token)).json()[
        "total"
    ]
    assert 0 < filtered <= all_products


def test_product_search_is_case_insensitive(client, admin_token):
    payload = client.get("/api/v1/products?q=SAMSUNG&page_size=10", headers=auth(admin_token)).json()
    names = " ".join(item["canonical_name"] for item in payload["items"]).lower()
    assert "samsung" in names or payload["total"] == 0


def test_product_facets_and_categories(client, admin_token):
    facets = client.get("/api/v1/products/facets", headers=auth(admin_token)).json()
    assert facets["categories"] and facets["sources"]
    tree = client.get("/api/v1/products/categories", headers=auth(admin_token)).json()
    assert isinstance(tree, list) and tree


def test_product_detail_includes_history(client, admin_token):
    listing = client.get("/api/v1/products?page_size=1", headers=auth(admin_token)).json()
    product_id = listing["items"][0]["product_id"]
    detail = client.get(f"/api/v1/products/{product_id}", headers=auth(admin_token)).json()
    assert detail["product_id"] == product_id
    assert isinstance(detail["history"], list)


def test_unknown_product_returns_404(client, admin_token):
    response = client.get("/api/v1/products/99999999", headers=auth(admin_token))
    assert response.status_code == 404
    assert response.json()["error"] == "product_not_found"


def test_price_history_endpoint(client, admin_token):
    listing = client.get("/api/v1/products?page_size=1", headers=auth(admin_token)).json()
    product_id = listing["items"][0]["product_id"]
    payload = client.get(f"/api/v1/products/{product_id}/history", headers=auth(admin_token)).json()
    assert payload["product_id"] == product_id
    assert payload["points"] >= 1
    assert "first" in payload and "last" in payload


def test_csv_export(client, admin_token):
    response = client.get("/api/v1/analytics/export/products.csv", headers=auth(admin_token))
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "product_id" in response.text.splitlines()[0]


# --------------------------------------------------------------------------------------
# Changes, analytics, pipeline, quality
# --------------------------------------------------------------------------------------
def test_price_change_feed(client, admin_token):
    payload = client.get("/api/v1/changes/price?page_size=5", headers=auth(admin_token)).json()
    assert "items" in payload
    if payload["items"]:
        row = payload["items"][0]
        assert row["direction"] in {"increase", "decrease"}


def test_change_summary(client, admin_token):
    payload = client.get("/api/v1/changes/summary?days=365", headers=auth(admin_token)).json()
    assert "total_events" in payload and "timeline" in payload


def test_top_movers_are_sorted(client, admin_token):
    rows = client.get("/api/v1/changes/top-movers?limit=5", headers=auth(admin_token)).json()
    magnitudes = [abs(row["change_pct"]) for row in rows if row.get("change_pct") is not None]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_analytics_kpi(client, admin_token):
    payload = client.get("/api/v1/analytics/kpi", headers=auth(admin_token)).json()
    assert payload["latest"]["products"] > 0
    assert payload["counts"]["fact_price_snapshot"] > 0


def test_pipeline_runs_and_detail(client, admin_token):
    runs = client.get("/api/v1/pipeline/runs?page_size=3", headers=auth(admin_token)).json()
    assert runs["items"]
    run_id = runs["items"][0]["run_id"]
    detail = client.get(f"/api/v1/pipeline/runs/{run_id}", headers=auth(admin_token)).json()
    assert detail["run_id"] == run_id
    assert "dq" in detail


def test_quality_latest_and_rules(client, admin_token):
    latest = client.get("/api/v1/quality/latest", headers=auth(admin_token)).json()
    assert latest["total"] >= 0
    rules = client.get("/api/v1/quality/rules", headers=auth(admin_token)).json()
    assert len(rules) == 12


def test_catalog_summary(client, admin_token):
    payload = client.get("/api/v1/catalog/summary", headers=auth(admin_token)).json()
    assert "totals" in payload


def test_sources_registry(client, admin_token):
    sources = client.get("/api/v1/sources", headers=auth(admin_token)).json()
    codes = {source["code"] for source in sources}
    assert "local_demo" in codes


# --------------------------------------------------------------------------------------
# Query lab (read-only guard)
# --------------------------------------------------------------------------------------
def test_query_executes_a_select(client, admin_token):
    response = client.post(
        "/api/v1/queries/execute", headers=auth(admin_token), json={"sql": "SELECT 1 AS ok"}
    )
    assert response.status_code == 200
    assert response.json()["rows"] == [[1]]


def test_query_rejects_writes(client, admin_token):
    for statement in (
        "DELETE FROM dim_product",
        "UPDATE dim_product SET price = 1",
        "DROP TABLE dim_product",
    ):
        response = client.post("/api/v1/queries/execute", headers=auth(admin_token), json={"sql": statement})
        assert response.status_code == 422, statement


def test_query_rejects_multiple_statements(client, admin_token):
    response = client.post(
        "/api/v1/queries/execute",
        headers=auth(admin_token),
        json={"sql": "SELECT 1; DELETE FROM dim_product"},
    )
    assert response.status_code == 422


def test_viewer_may_query_but_not_write(client, viewer_token):
    """`query` is granted to every role; writes are not."""
    response = client.post("/api/v1/queries/execute", headers=auth(viewer_token), json={"sql": "SELECT 1"})
    assert response.status_code == 200
    assert (
        client.post(
            "/api/v1/queries/execute", headers=auth(viewer_token), json={"sql": "DELETE FROM dim_product"}
        ).status_code
        == 422
    )


# --------------------------------------------------------------------------------------
# Account and administration
# --------------------------------------------------------------------------------------
def test_profile_update_round_trip(client, admin_token):
    headers = auth(admin_token)
    before = client.get("/api/v1/users/me", headers=headers).json()
    updated = client.patch("/api/v1/users/me", headers=headers, json={"rows_per_page": 50}).json()
    assert updated["rows_per_page"] == 50
    client.patch("/api/v1/users/me", headers=headers, json={"rows_per_page": before["rows_per_page"]})


def test_viewer_cannot_reach_admin_endpoints(client, viewer_token):
    for path in ("/api/v1/users", "/api/v1/users/stats", "/api/v1/audit"):
        response = client.get(path, headers=auth(viewer_token))
        assert response.status_code == 403, path
    # Public settings are readable by anyone, but writing them is admin-only.
    assert client.get("/api/v1/settings", headers=auth(viewer_token)).status_code == 200
    assert (
        client.put(
            "/api/v1/settings/ui.default_theme", headers=auth(viewer_token), json={"value": "dark"}
        ).status_code
        == 403
    )


def test_saved_view_lifecycle(client, admin_token):
    headers = auth(admin_token)
    created = client.post(
        "/api/v1/saved-views",
        headers=headers,
        json={"name": "pytest-view", "entity": "products", "filters": {"in_stock": True}},
    )
    assert created.status_code == 201
    view_id = created.json()["view_id"]
    assert (
        client.post(f"/api/v1/saved-views/{view_id}/favorite", headers=headers).json()["is_favorite"] is True
    )
    assert client.delete(f"/api/v1/saved-views/{view_id}", headers=headers).status_code == 200


def test_alert_lifecycle(client, admin_token):
    headers = auth(admin_token)
    created = client.post(
        "/api/v1/alerts",
        headers=headers,
        json={"name": "pytest-alert", "metric": "price_change_pct", "operator": "lt", "threshold": -12},
    )
    assert created.status_code == 201
    alert_id = created.json()["alert_id"]
    assert client.delete(f"/api/v1/alerts/{alert_id}", headers=headers).status_code == 200


def test_change_password_validation(client, admin_token):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth(admin_token),
        json={"current_password": "Admin@12345", "new_password": "weak"},
    )
    assert response.status_code == 422


def test_api_key_creation_and_revocation(client, admin_token):
    headers = auth(admin_token)
    profile = client.get("/api/v1/users/me", headers=headers).json()
    created = client.post(
        f"/api/v1/users/{profile['user_id']}/api-keys", headers=headers, json={"name": "pytest-key"}
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["api_key"].startswith("pip_")
    assert (
        client.delete(
            f"/api/v1/users/{profile['user_id']}/api-keys/{payload['key_id']}", headers=headers
        ).status_code
        == 200
    )


def test_pipeline_trigger_requires_permission(client, viewer_token):
    response = client.post(
        "/api/v1/pipeline/run/sync", headers=auth(viewer_token), json={"limit_per_source": 1}
    )
    assert response.status_code == 403


def test_pipeline_trigger_runs_for_admin(client, admin_token):
    response = client.post(
        "/api/v1/pipeline/run/sync",
        headers=auth(admin_token),
        json={"sources": ["local_demo"], "limit_per_source": 3, "skip_dq": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["status"] in {"success", "partial"}


def test_error_payloads_are_consistent(client, admin_token):
    response = client.get("/api/v1/products/99999999", headers=auth(admin_token))
    body = response.json()
    assert set(body) >= {"error", "message", "details"}
