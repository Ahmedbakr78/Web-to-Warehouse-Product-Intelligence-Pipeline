"""Dashboard-managed sources: the generic JSON adapter and its API surface.

Adding a source from the GUI must never need a deploy, and must never weaken
compliance: SSRF-safe URLs, a server-side robots re-check on create, and an
explicit terms confirmation. These tests pin all three, plus the adapter's
pagination styles against a stubbed transport (no network in the suite).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token
from app.core.errors import SourceNotFoundError
from app.ingestion.dynamic import enabled_dynamic_codes, is_dynamic_row, resolve_source
from app.ingestion.sources.generic_json import ADAPTER_NAME, PRESETS, GenericJsonSource, get_path
from app.models.dimensions import DimSource

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


@pytest.fixture(scope="module")
def analyst_token():
    return create_access_token(2, role="analyst", email="analyst@example.com")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _definition(**overrides):
    base = {
        "code": "gui_test_shop",
        "name": "GUI Test Shop",
        "base_url": "https://shop.example.com/products.json",
        "terms_url": "https://shop.example.com/terms",
        "currency": "USD",
        "rate_limit_per_minute": 30,
        "min_delay_seconds": 1.0,
        "enabled": True,
        "terms_allowed": True,
        "config": {
            "adapter": ADAPTER_NAME,
            "items_path": "products",
            "id_field": "id",
            "fields": {"name": "title", "price": "price", "category": "category"},
            "pagination": {"style": "none"},
        },
    }
    base.update(overrides)
    return base


def _insert_row(session, **overrides) -> DimSource:
    payload = _definition(**overrides)
    row = DimSource(
        source_code=payload["code"],
        name=payload["name"],
        kind="api",
        base_url=payload["base_url"],
        terms_url=payload.get("terms_url"),
        rate_limit_per_minute=payload["rate_limit_per_minute"],
        min_delay_seconds=payload["min_delay_seconds"],
        enabled=payload["enabled"],
        terms_allowed=payload["terms_allowed"],
        config=payload["config"],
    )
    session.add(row)
    session.flush()
    return row


class _StubClient:
    """Stand-in for CompliantHttpClient: canned payloads, no network."""

    def __init__(self, pages: list):
        self._pages = list(pages)
        self.calls: list[dict] = []

    def get_json(self, url, params=None):
        self.calls.append({"url": url, "params": params})
        if not self._pages:
            return {}
        return self._pages.pop(0)

    def close(self):
        pass


# --------------------------------------------------------------------------------------
# Path language
# --------------------------------------------------------------------------------------
def test_get_path_resolves_indices_and_constants():
    assert get_path({"a": {"b": [{"c": 7}]}}, "a.b.0.c") == 7
    assert get_path([1, 2], "") == [1, 2]
    assert get_path({"x": 1}, "const:USD") == "USD"
    assert get_path({"x": 1}, "missing") is not None


def test_get_path_missing_is_sentinel():
    from app.ingestion.sources.generic_json import _MISSING

    assert get_path({"x": 1}, "y") is _MISSING
    assert get_path({"x": 1}, "x.0") is _MISSING


def test_presets_cover_the_advertised_endpoints():
    assert set(PRESETS) >= {"dummyjson", "fakestore", "shopify", "openfoodfacts", "openlibrary"}
    for key, preset in PRESETS.items():
        assert preset["base_url"].startswith("https://"), key
        assert preset["items_path"] is not None
        assert preset["pagination"]["style"] in ("none", "skip_limit", "page_number")


# --------------------------------------------------------------------------------------
# Adapter fetching (stubbed transport)
# --------------------------------------------------------------------------------------
def test_fetch_single_shot_root_array():
    items = [{"id": i, "title": f"Widget {i}", "price": 9.99 + i} for i in range(1, 4)]
    source = GenericJsonSource(
        _definition(
            config={
                "adapter": ADAPTER_NAME,
                "items_path": "",
                "id_field": "id",
                "fields": {"name": "title", "price": "price"},
                "pagination": {"style": "none"},
            }
        ),
        client=_StubClient([items]),
    )
    records = list(source.fetch(limit=10))
    assert [record.name for record in records] == ["Widget 1", "Widget 2", "Widget 3"]
    assert records[0].source_product_id == "1"
    assert source.client.calls[0]["url"].endswith("products.json")


def test_fetch_skip_limit_stops_at_total():
    page_one = {"products": [{"id": 1, "title": "A", "price": 5}], "total": 2}
    page_two = {"products": [{"id": 2, "title": "B", "price": 6}], "total": 2}
    source = GenericJsonSource(
        _definition(
            config={
                "adapter": ADAPTER_NAME,
                "items_path": "products",
                "id_field": "id",
                "fields": {"name": "title", "price": "price"},
                "pagination": {
                    "style": "skip_limit",
                    "page_size": 1,
                    "limit_param": "limit",
                    "offset_param": "skip",
                    "total_path": "total",
                },
            }
        ),
        client=_StubClient([page_one, page_two]),
    )
    records = list(source.fetch(limit=10))
    assert len(records) == 2
    assert source.client.calls[1]["params"] == {"limit": 1, "skip": 1}


def test_fetch_missing_items_path_records_error():
    source = GenericJsonSource(
        _definition(
            config={
                "adapter": ADAPTER_NAME,
                "items_path": "nope",
                "id_field": "id",
                "fields": {"name": "title"},
                "pagination": {"style": "none"},
            }
        ),
        client=_StubClient([{"other": []}]),
    )
    assert list(source.fetch(limit=5)) == []
    assert any("items_path" in error for error in source.errors)


def test_url_template_renders_origin_and_handle():
    source = GenericJsonSource(
        _definition(
            base_url="https://demo.myshopify.com/products.json",
            config={
                "adapter": ADAPTER_NAME,
                "items_path": "products",
                "id_field": "id",
                "fields": {"name": "title", "price": "variants.0.price"},
                "pagination": {"style": "none"},
                "url_template": "{origin}/products/{handle}",
            },
        ),
        client=_StubClient(
            [{"products": [{"id": 9, "title": "Cap", "handle": "cap", "variants": [{"price": "19.00"}]}]}]
        ),
    )
    (record,) = list(source.fetch(limit=5))
    assert record.url == "https://demo.myshopify.com/products/cap"
    assert record.price_text == "19.00"


# --------------------------------------------------------------------------------------
# Dynamic resolution
# --------------------------------------------------------------------------------------
def test_resolve_prefers_registry_and_falls_back_to_database(session):
    from app.ingestion.base import get_source_class

    _insert_row(session, code="gui_dynamic_one")
    session.commit()

    resolved = resolve_source(session, "gui_dynamic_one")
    assert isinstance(resolved, GenericJsonSource)
    assert resolved.code == "gui_dynamic_one"
    assert resolved.enabled is True

    # A bundled source still resolves to its class, never to a row.
    assert get_source_class("dummyjson_products") is resolve_source(session, "dummyjson_products").__class__

    with pytest.raises(SourceNotFoundError):
        resolve_source(session, "no_such_source_xyz")


def test_enabled_dynamic_codes_respects_flags(session):
    _insert_row(session, code="gui_on")
    _insert_row(session, code="gui_off", enabled=False)
    _insert_row(session, code="gui_unconfirmed", terms_allowed=False)
    session.commit()

    codes = enabled_dynamic_codes(session)
    assert "gui_on" in codes
    assert "gui_off" not in codes
    assert "gui_unconfirmed" not in codes


def test_is_dynamic_row_only_matches_adapter(session):
    row = _insert_row(session, code="gui_adapter_check")
    assert is_dynamic_row(row) is True
    row.config = {"adapter": "something_else"}
    assert is_dynamic_row(row) is False
    assert is_dynamic_row(None) is False


# --------------------------------------------------------------------------------------
# API surface
# --------------------------------------------------------------------------------------
def _allow_robots(monkeypatch, allowed: bool = True):
    from app.ingestion import robots as robots_module

    class _Decision:
        rule = "robots.txt:allow" if allowed else "robots.txt:disallow"
        crawl_delay = None

        def __init__(self, ok: bool):
            self.allowed = ok

    monkeypatch.setattr(robots_module.RobotsCache, "can_fetch", lambda self, url, ua=None: _Decision(allowed))


def _public_dns(monkeypatch):
    """Resolve every hostname to a public IP: the sandbox has no real DNS, and
    the SSRF guard (correctly) rejects unresolvable hosts."""
    import socket

    real = socket.getaddrinfo

    def fake(host, *args, **kwargs):
        if host in ("127.0.0.1", "localhost", "::1"):
            return real(host, *args, **kwargs)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_presets_endpoint_lists_mappings(client, viewer_token):
    response = client.get("/api/v1/sources/presets", headers=auth(viewer_token))
    assert response.status_code == 200
    assert "dummyjson" in response.json()["presets"]


def test_check_endpoint_reports_verdict(client, analyst_token, viewer_token, monkeypatch):
    _allow_robots(monkeypatch, allowed=True)
    _public_dns(monkeypatch)

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"products": [{"id": 1, "title": "A", "price": 3}]}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return _FakeResponse()

    import app.api.routers.sources as sources_router

    monkeypatch.setattr(sources_router.httpx, "Client", _FakeClient)
    response = client.post(
        "/api/v1/sources/check",
        json={"base_url": "https://shop.example.com/products.json", "items_path": "products"},
        headers=auth(analyst_token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["shape"]["item_count"] == 1
    assert payload["shape"]["item_keys"] == ["id", "price", "title"]

    # Viewers can read sources but may not trigger outbound compliance checks.
    denied = client.post(
        "/api/v1/sources/check",
        json={"base_url": "https://shop.example.com/products.json"},
        headers=auth(viewer_token),
    )
    assert denied.status_code == 403


def test_check_endpoint_blocks_private_hosts(client, analyst_token):
    response = client.post(
        "/api/v1/sources/check",
        json={"base_url": "http://127.0.0.1:9999/products.json"},
        headers=auth(analyst_token),
    )
    assert response.status_code == 422


def test_create_source_happy_path(client, admin_token, session, monkeypatch):
    _allow_robots(monkeypatch, allowed=True)
    _public_dns(monkeypatch)
    response = client.post(
        "/api/v1/sources",
        json={
            "code": "gui_created",
            "name": "GUI Created Shop",
            "base_url": "https://shop.example.com/products.json",
            "terms_confirmed": True,
            "mapping": {
                "items_path": "products",
                "id_field": "id",
                "fields": {"name": "title", "price": "price"},
                "pagination": {"style": "none"},
            },
        },
        headers=auth(admin_token),
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["managed"] == "database"
    assert payload["terms_allowed"] is True

    listed = client.get("/api/v1/sources", headers=auth(admin_token)).json()
    assert any(item["code"] == "gui_created" and item["managed"] == "database" for item in listed)


def test_create_source_requires_terms_and_robots(client, admin_token, monkeypatch):
    _allow_robots(monkeypatch, allowed=True)
    _public_dns(monkeypatch)
    body = {
        "code": "gui_no_terms",
        "name": "No Terms Shop",
        "base_url": "https://shop.example.com/products.json",
        "terms_confirmed": False,
    }
    assert client.post("/api/v1/sources", json=body, headers=auth(admin_token)).status_code == 422

    _allow_robots(monkeypatch, allowed=False)
    body.update({"code": "gui_blocked", "terms_confirmed": True})
    denied = client.post("/api/v1/sources", json=body, headers=auth(admin_token))
    assert denied.status_code == 422
    assert "robots" in denied.text


def test_create_source_rejects_clashes_and_viewers(client, admin_token, viewer_token, session, monkeypatch):
    _allow_robots(monkeypatch, allowed=True)
    _public_dns(monkeypatch)
    _insert_row(session, code="gui_taken")
    session.commit()
    body = {
        "code": "gui_taken",
        "name": "Taken",
        "base_url": "https://shop.example.com/products.json",
        "terms_confirmed": True,
    }
    assert client.post("/api/v1/sources", json=body, headers=auth(admin_token)).status_code == 409

    body["code"] = "dummyjson_products"
    assert client.post("/api/v1/sources", json=body, headers=auth(admin_token)).status_code == 409

    body["code"] = "bad-code!"
    assert client.post("/api/v1/sources", json=body, headers=auth(admin_token)).status_code == 422

    body["code"] = "gui_viewer_try"
    assert client.post("/api/v1/sources", json=body, headers=auth(viewer_token)).status_code == 403


def test_update_and_delete_lifecycle(client, admin_token, session, monkeypatch):
    _allow_robots(monkeypatch, allowed=True)
    _insert_row(session, code="gui_lifecycle", enabled=False)
    session.commit()

    updated = client.patch("/api/v1/sources/gui_lifecycle", json={"enabled": True}, headers=auth(admin_token))
    assert updated.status_code == 200
    assert updated.json()["enabled"] is True

    # Bundled sources are not editable here.
    assert (
        client.patch(
            "/api/v1/sources/dummyjson_products", json={"enabled": False}, headers=auth(admin_token)
        ).status_code
        == 404
    )

    deleted = client.delete("/api/v1/sources/gui_lifecycle", headers=auth(admin_token))
    assert deleted.status_code == 200

    _insert_row(session, code="gui_historic")
    row = session.get(DimSource, "gui_historic")
    row.total_runs = 3
    session.commit()
    guarded = client.delete("/api/v1/sources/gui_historic", headers=auth(admin_token))
    assert guarded.status_code == 409


def test_preview_resolves_dynamic_source(client, admin_token, session, monkeypatch):
    from app.ingestion.http_client import CompliantHttpClient

    _insert_row(session, code="gui_preview")
    session.commit()
    monkeypatch.setattr(
        CompliantHttpClient,
        "get_json",
        lambda self, url, params=None, **kwargs: {"products": [{"id": 7, "title": "Prev", "price": 12.5}]},
    )
    response = client.get("/api/v1/sources/gui_preview/preview?limit=5", headers=auth(admin_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["returned"] == 1
    assert payload["records"][0]["canonical_name"] == "Prev"
