"""Per-product history CSV download: header, auth scope and 404 behaviour."""

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


def test_history_csv_downloads_with_expected_columns(client, admin_token):
    response = client.get("/api/v1/products/1/history.csv", headers=auth(admin_token))
    assert response.status_code == 200, response.text[:200]
    assert "text/csv" in response.headers["content-type"]
    assert "product-1-history.csv" in response.headers.get("content-disposition", "")
    lines = response.text.splitlines()
    assert lines[0].startswith("snapshot_id,captured_at,")
    assert "price_usd" in lines[0]
    assert len(lines) >= 2


def test_history_csv_is_readable_by_viewers(client, viewer_token):
    response = client.get("/api/v1/products/1/history.csv", headers=auth(viewer_token))
    assert response.status_code == 200


def test_history_csv_404_for_unknown_product(client, admin_token):
    response = client.get("/api/v1/products/999999999/history.csv", headers=auth(admin_token))
    assert response.status_code == 404
