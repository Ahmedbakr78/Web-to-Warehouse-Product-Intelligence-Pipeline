"""Catalog CSV import: template download, upsert behaviour and validation."""

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


VALID_CSV = (
    "sku,name,brand,category,supplier,cost_price,list_price,currency,qty_on_hand,status,product_url\n"
    "TEST-IMPORT-1,Import Widget One,Acme,Gadgets,Main,10,29.99,USD,5,active,\n"
    "TEST-IMPORT-2,Import Widget Two,Acme,Gadgets,Main,20,59.99,USD,3,active,https://example.com/t2\n"
)


def test_template_downloads_with_header(client, admin_token):
    response = client.get("/api/v1/catalog/template", headers=auth(admin_token))
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert response.text.splitlines()[0].startswith("sku,name,")
    assert "SKU-0001" in response.text


def test_import_creates_then_updates(client, admin_token):
    first = client.post(
        "/api/v1/catalog/import",
        headers=auth(admin_token),
        files={"file": ("catalog.csv", VALID_CSV, "text/csv")},
    )
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 2
    assert first.json()["updated"] == 0

    second = client.post(
        "/api/v1/catalog/import",
        headers=auth(admin_token),
        files={"file": ("catalog.csv", VALID_CSV, "text/csv")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["created"] == 0
    assert second.json()["updated"] == 2

    listing = client.get("/api/v1/catalog/products?q=TEST-IMPORT", headers=auth(admin_token)).json()
    assert listing["total"] >= 2


def test_import_rejects_bad_rows_without_writing(client, admin_token):
    bad = "sku,name,brand\n,No Sku Here,Acme\nBAD-1,,Acme\n"
    response = client.post(
        "/api/v1/catalog/import",
        headers=auth(admin_token),
        files={"file": ("bad.csv", bad, "text/csv")},
    )
    assert response.status_code == 422
    assert "nothing was imported" in response.json()["message"]


def test_import_rejects_non_csv_and_viewer_is_refused(client, admin_token, viewer_token):
    not_csv = client.post(
        "/api/v1/catalog/import",
        headers=auth(admin_token),
        files={"file": ("catalog.txt", VALID_CSV, "text/plain")},
    )
    assert not_csv.status_code == 422

    refused = client.post(
        "/api/v1/catalog/import",
        headers=auth(viewer_token),
        files={"file": ("catalog.csv", VALID_CSV, "text/csv")},
    )
    assert refused.status_code == 403


def test_export_round_trips_imported_rows(client, admin_token, viewer_token):
    for token in (admin_token, viewer_token):
        response = client.get("/api/v1/catalog/export.csv", headers=auth(token))
        assert response.status_code == 200, response.text[:200]
        assert "text/csv" in response.headers["content-type"]
        lines = response.text.splitlines()
        assert lines[0].startswith("sku,name,")
        assert any("TEST-IMPORT-1" in line for line in lines[1:])


def test_builder_schema_includes_runs_and_alerts(client, admin_token):
    schema = client.get("/api/v1/builder/schema", headers=auth(admin_token)).json()
    names = {entity["entity"] for entity in schema["entities"]}
    assert {"pipeline_runs", "alert_rules"} <= names

    payload = {
        "entity": "pipeline_runs",
        "columns": ["status"],
        "aggregates": [{"function": "count", "column": "run_id", "alias": "runs"}],
        "group_by": ["status"],
        "order_by": "runs",
        "order_dir": "desc",
        "limit": 10,
    }
    result = client.post("/api/v1/builder/query", headers=auth(admin_token), json=payload)
    assert result.status_code == 200, result.text
    assert "runs" in result.json()["columns"]
