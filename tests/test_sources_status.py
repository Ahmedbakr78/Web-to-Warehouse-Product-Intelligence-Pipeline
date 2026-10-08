"""Regression tests for `GET /pipeline/sources/status` row hydration.

The Sources screen reads compliance and politeness metadata (``terms_allowed``,
``rate_limit_per_minute``, ``min_delay_seconds``) from this payload. A bundled
source that has never run has no ``dim_source`` row, so an earlier version
emitted a seven-key placeholder for it and every never-run source rendered as
"terms restricted · 0 req/min · 0s delay" — directly contradicting the
compliance header, which is built from the registry.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token
from app.ingestion.base import all_source_codes

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


def _status(client, token) -> list[dict]:
    response = client.get("/api/v1/pipeline/sources/status", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def test_every_registered_source_is_reported(client, admin_token):
    rows = _status(client, admin_token)
    codes = {row["source_code"] for row in rows}
    assert set(all_source_codes()) <= codes


def test_every_row_carries_the_same_shape(client, admin_token):
    """A consumer must not have to guess which keys exist per row."""
    rows = _status(client, admin_token)
    shapes = {frozenset(row) for row in rows}
    assert len(shapes) == 1, f"inconsistent row shapes: {[sorted(s) for s in shapes]}"


def test_never_run_sources_keep_their_compliance_metadata(client, admin_token):
    """The regression: registry metadata must survive the absence of a dim_source row."""
    rows = _status(client, admin_token)
    never_ran = [row for row in rows if (row.get("total_runs") or 0) == 0 and row.get("managed") == "code"]
    assert never_ran, "expected at least one bundled source that has never run"
    for row in never_ran:
        assert row["terms_allowed"] is True, row["source_code"]
        assert row["rate_limit_per_minute"] > 0, row["source_code"]
        assert row["min_delay_seconds"] >= 0, row["source_code"]
        assert row["base_url"], row["source_code"]
        assert row["name"], row["source_code"]
        assert row["kind"] in {"api", "scrape", "synthetic"}, row["source_code"]


def test_never_run_sources_report_idle_not_unknown(client, admin_token):
    """'idle' says registered-and-ready; 'unknown' reads as a health failure."""
    rows = _status(client, admin_token)
    for row in rows:
        if (row.get("total_runs") or 0) == 0:
            assert row["sync_status"] in {"idle", "disabled"}, row["source_code"]


def test_status_agrees_with_the_registry_on_terms(client, admin_token):
    """The compliance header and the cards must never disagree."""
    registry = client.get("/api/v1/sources", headers=auth(admin_token)).json()
    allowed = {row["code"] for row in registry if row["terms_allowed"]}
    status = _status(client, admin_token)
    reported_allowed = {row["source_code"] for row in status if row.get("terms_allowed")}
    assert allowed <= reported_allowed, sorted(allowed - reported_allowed)
