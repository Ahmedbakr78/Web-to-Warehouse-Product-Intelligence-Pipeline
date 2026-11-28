"""Report CSV export (previously advertised but unserved) and settings write fixes."""

from __future__ import annotations

import csv
import io

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


def test_report_csv_downloads(client, admin_token):
    response = client.get("/api/v1/reports/executive_summary/csv?days=30", headers=auth(admin_token))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="executive_summary-report.csv"' in response.headers["content-disposition"]
    lines = response.text.splitlines()
    assert lines[0] == "section,kind,label,value"
    assert len(lines) > 5


def test_report_csv_frame_and_tables_parse(client, admin_token):
    text = client.get("/api/v1/reports/price_movements/csv?days=30", headers=auth(admin_token)).text
    lines = text.splitlines()
    first_table = next((index for index, line in enumerate(lines) if line.startswith("#")), len(lines))
    frame_lines = [line for line in lines[:first_table] if line]
    metrics = list(csv.DictReader(io.StringIO("\n".join(frame_lines))))
    assert metrics
    assert set(metrics[0]) == {"section", "kind", "label", "value"}
    assert {row["kind"] for row in metrics} <= {"metric", "bar", "note", "text", "forecast"}
    tables = [line for line in lines if line.startswith("# table: ")]
    assert tables, "table blocks must be appended as real CSV sub-tables"
    # Every sub-table carries a header plus at least one data row.
    for line in tables:
        start = lines.index(line)
        assert lines[start + 1] and not lines[start + 1].startswith("#"), "table header missing"


def test_report_csv_rejects_unknown_template(client, admin_token):
    response = client.get("/api/v1/reports/nope/csv", headers=auth(admin_token))
    assert response.status_code == 422


def test_report_csv_needs_product_for_product_template(client, admin_token):
    response = client.get("/api/v1/reports/product/csv", headers=auth(admin_token))
    assert response.status_code == 422


def test_report_csv_viewer_can_read(client, viewer_token):
    response = client.get("/api/v1/reports/data_quality/csv?days=30", headers=auth(viewer_token))
    assert response.status_code == 200


def test_setting_write_preserves_type_and_sets_metadata(client, admin_token):
    headers = auth(admin_token)
    created = client.put(
        "/api/v1/settings/pytest.demo",
        headers=headers,
        json={"value": "42", "value_type": "number", "category": "pytest", "description": "demo", "is_public": True},
    )
    assert created.status_code == 200
    assert created.json()["value_type"] == "number"

    # A type-less write keeps the stored type instead of coercing to string.
    updated = client.put("/api/v1/settings/pytest.demo", headers=headers, json={"value": "43"})
    assert updated.status_code == 200
    body = updated.json()
    assert body["value"] == "43"
    assert body["value_type"] == "number"
    assert body["category"] == "pytest"

    assert client.delete("/api/v1/settings/pytest.demo", headers=headers).status_code == 200


def test_setting_mutations_are_audited(client, admin_token):
    headers = auth(admin_token)
    client.put("/api/v1/settings/pytest.audit", headers=headers, json={"value": "1"})
    trail = client.get("/api/v1/audit?days=1&page_size=50", headers=headers).json()
    actions = {item["action"] for item in trail["items"] if item["entity_type"] == "app_setting"}
    assert "setting.updated" in actions
    assert client.delete("/api/v1/settings/pytest.audit", headers=headers).status_code == 200
