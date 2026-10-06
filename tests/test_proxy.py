"""Egress proxy resolution: explicit proxy wins, no_proxy hosts go direct."""

from __future__ import annotations

from app.core.config import Settings
from app.ingestion.http_client import resolve_proxy


def test_no_proxy_by_default():
    assert resolve_proxy("https://example.com/a") is None
    assert resolve_proxy("https://example.com/a", proxy_url="  ") is None


def test_explicit_proxy_applies():
    proxy = "http://proxy.internal:3128"
    assert resolve_proxy("https://example.com/a", proxy_url=proxy) == proxy


def test_no_proxy_hosts_bypass():
    proxy = "http://proxy.internal:3128"
    assert (
        resolve_proxy("http://localhost:8000/api", proxy_url=proxy, no_proxy="localhost,127.0.0.1")
        is None
    )
    assert (
        resolve_proxy("http://127.0.0.1:5432/db", proxy_url=proxy, no_proxy="localhost,127.0.0.1")
        is None
    )
    assert (
        resolve_proxy("https://example.com/a", proxy_url=proxy, no_proxy="localhost,127.0.0.1")
        == proxy
    )


def test_settings_reject_non_http_proxy():
    import pydantic

    with __import__("pytest").raises(pydantic.ValidationError):
        Settings(ingest_proxy_url="socks5://proxy:1080")
    assert Settings(ingest_proxy_url="").ingest_proxy_url == ""
    assert Settings(ingest_proxy_url="http://p:3128/").ingest_proxy_url == "http://p:3128"
