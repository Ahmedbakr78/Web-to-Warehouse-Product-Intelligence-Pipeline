"""Conditional GET: ETag/Last-Modified revalidation saves bandwidth."""

from __future__ import annotations

import json
import time

import httpx

from app.core.config import settings
from app.ingestion.http_client import CompliantHttpClient


def _client(tmp_path, handler, **kwargs):
    client = CompliantHttpClient(
        source_code="test",
        respect_robots=False,
        use_cache=True,
        cache_dir=tmp_path / "cache",
        requests_per_second=100,
        min_delay_seconds=0,
        **kwargs,
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def _expire_body(client, url):
    """Backdate the cached body past its TTL; validators still survive."""
    path = client._cache_path(url)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["stored_at"] = time.time() - settings.cache_ttl_seconds - 60
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_etag_revalidation_serves_cached_body_without_download(tmp_path):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        if "if-none-match" in request.headers:
            assert request.headers["if-none-match"] == '"abc123"'
            return httpx.Response(304, headers={"ETag": '"abc123"'})
        return httpx.Response(200, text='{"items": [1, 2, 3]}', headers={"ETag": '"abc123"'})

    client = _client(tmp_path, handler)
    first = client.get("https://example.com/api/products")
    assert first.status_code == 200 and not first.revalidated
    _expire_body(client, "https://example.com/api/products")

    second = client.get("https://example.com/api/products")
    assert second.status_code == 200
    assert second.revalidated is True
    assert second.from_cache is True
    assert second.text == '{"items": [1, 2, 3]}'
    assert len(seen) == 1 or "if-none-match" in seen[1]  # second request conditional
    audit = client.audit[-1]
    assert audit.status_code == 304 and audit.from_cache is True


def test_last_modified_sent_when_no_etag(tmp_path):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        if "if-modified-since" in request.headers:
            return httpx.Response(304)
        return httpx.Response(200, text="hi", headers={"Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT"})

    client = _client(tmp_path, handler)
    client.get("https://example.com/feed")
    _expire_body(client, "https://example.com/feed")
    second = client.get("https://example.com/feed")
    assert second.revalidated is True and second.text == "hi"


def test_304_without_cache_falls_back_to_full_fetch(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(304)  # no cache yet: must retry unconditionally
        return httpx.Response(200, text="fresh")

    client = _client(tmp_path, handler)
    result = client.get("https://example.com/nocache")
    assert result.status_code == 200 and result.text == "fresh"
    assert calls["n"] == 2


def test_caller_headers_win_over_validators(tmp_path):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return httpx.Response(200, text="v", headers={"ETag": '"x"'})

    client = _client(tmp_path, handler)
    client.get("https://example.com/h")
    _expire_body(client, "https://example.com/h")
    client.get("https://example.com/h", headers={"If-None-Match": '"custom"'})
    assert seen[1].get("if-none-match") == '"custom"'


def test_expired_validators_are_not_sent(tmp_path):
    client = _client(tmp_path, lambda request: httpx.Response(200, text="new"))
    path = client._cache_path("https://example.com/old")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "stored_at": time.time() - 31 * 24 * 3600,
                "status_code": 200,
                "text": "old",
                "headers": {"ETag": '"stale"'},
                "elapsed_ms": 1.0,
            }
        ),
        encoding="utf-8",
    )
    assert client._read_validators("https://example.com/old") == {}
    result = client.get("https://example.com/old")
    assert result.text == "new" and not result.revalidated
