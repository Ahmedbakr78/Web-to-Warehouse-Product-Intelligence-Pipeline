"""Compliant HTTP client used by every source.

Guarantees enforced here (not in each scraper):

* ``robots.txt`` is consulted before each request.
* Rate limits / crawl-delay are applied per host.
* Retries use exponential backoff with jitter and honour ``Retry-After``.
* Responses are cached on disk so re-running a pipeline is cheap and polite.
* Every request is written to ``ingestion_http_log`` for the compliance audit.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.errors import ComplianceError, IngestionError, RateLimitError
from app.core.logging import get_logger
from app.ingestion.ratelimit import CircuitBreaker, RateLimiter, RatePolicy
from app.ingestion.robots import get_robots_cache

log = get_logger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
)


@dataclass
class FetchResult:
    """Normalised response wrapper returned by :meth:`CompliantHttpClient.get`."""

    url: str
    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    from_cache: bool = False
    retries: int = 0
    robots_allowed: bool = True
    robots_rule: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass
class HttpAuditEntry:
    """In-memory audit rows flushed to the DB once per run."""

    url: str
    method: str
    status_code: int | None
    elapsed_ms: float
    response_bytes: int
    robots_allowed: bool | None
    robots_rule: str | None
    from_cache: bool
    retry_count: int
    error: str | None = None

    def as_row(self, run_id: str | None, source_code: str | None) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "source_code": source_code,
            "method": self.method,
            "url": self.url[:2048],
            "host": urlparse(self.url).netloc or None,
            "status_code": self.status_code,
            "elapsed_ms": self.elapsed_ms,
            "response_bytes": self.response_bytes,
            "robots_allowed": self.robots_allowed,
            "robots_rule": self.robots_rule,
            "from_cache": self.from_cache,
            "retry_count": self.retry_count,
            "error": (self.error or None) and self.error[:2000],
        }


class CompliantHttpClient:
    """Polite HTTP client: robots gate + rate limit + cache + retry + audit log."""

    def __init__(
        self,
        *,
        source_code: str | None = None,
        run_id: str | None = None,
        user_agent: str | None = None,
        requests_per_second: float | None = None,
        requests_per_minute: int | None = None,
        min_delay_seconds: float | None = None,
        respect_robots: bool | None = None,
        use_cache: bool | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.source_code = source_code
        self.run_id = run_id
        self.user_agent = user_agent or settings.ingest_user_agent
        self.respect_robots = settings.respect_robots_txt if respect_robots is None else respect_robots
        self.use_cache = settings.cache_enabled if use_cache is None else use_cache
        self.cache_dir = cache_dir or settings.cache_dir
        self.audit: list[HttpAuditEntry] = []

        policy = RatePolicy(
            requests_per_second=(
                settings.requests_per_second if requests_per_second is None else requests_per_second
            ),
            requests_per_minute=(
                settings.requests_per_minute if requests_per_minute is None else requests_per_minute
            ),
            min_delay_seconds=(
                settings.crawl_delay_fallback_seconds if min_delay_seconds is None else min_delay_seconds
            ),
            burst=max(1, int(requests_per_second or settings.requests_per_second)),
        )
        self.policy = policy
        self.limiter = _shared_limiter()
        self.breaker = _shared_breaker()
        self.robots = get_robots_cache()
        self._client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            },
            limits=httpx.Limits(
                max_connections=settings.max_concurrent_requests,
                max_keepalive_connections=settings.max_concurrent_requests,
            ),
        )

    # ------------------------------------------------------------------ caching
    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        host = (urlparse(url).netloc or "unknown").replace(":", "_")
        return self.cache_dir / host / f"{digest}.json"

    def _read_cache(self, url: str) -> FetchResult | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            path.unlink(missing_ok=True)
            return None
        if (time.time() - payload.get("stored_at", 0)) > settings.cache_ttl_seconds:
            path.unlink(missing_ok=True)
            return None
        return FetchResult(
            url=url,
            status_code=payload.get("status_code", 200),
            text=payload.get("text", ""),
            headers=payload.get("headers", {}),
            elapsed_ms=payload.get("elapsed_ms", 0.0),
            from_cache=True,
            robots_rule="cache",
        )

    def _write_cache(self, result: FetchResult) -> None:
        if not self.use_cache or not result.ok:
            return
        path = self._cache_path(result.url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "stored_at": time.time(),
                        "status_code": result.status_code,
                        "text": result.text,
                        "headers": result.headers,
                        "elapsed_ms": result.elapsed_ms,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as exc:  # pragma: no cover - disk issues are non fatal
            log.debug("cache write failed url=%s error=%s", result.url, exc)

    # ------------------------------------------------------------------ fetching
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        check_robots: bool = True,
        force_refresh: bool = False,
    ) -> FetchResult:
        """Fetch a URL after compliance checks. Raises on persistent failure."""
        full_url = str(httpx.URL(url, params=params)) if params else url
        host = urlparse(full_url).netloc or "default"

        decision = self.robots.can_fetch(full_url, self.user_agent)
        if check_robots and self.respect_robots and not decision.allowed:
            self._record(
                full_url, "GET", None, 0.0, 0, False, decision.rule, False, 0, "blocked by robots.txt"
            )
            raise ComplianceError(
                f"robots.txt forbids fetching {full_url}",
                details={"url": full_url, "rule": decision.rule, "user_agent": self.user_agent},
            )
        if decision.crawl_delay:
            self.limiter.set_crawl_delay(host, decision.crawl_delay)

        if not force_refresh:
            cached = self._read_cache(full_url)
            if cached is not None:
                self._record(
                    full_url,
                    "GET",
                    cached.status_code,
                    0.0,
                    len(cached.text),
                    decision.allowed,
                    "cache",
                    True,
                    0,
                )
                return cached

        if self.breaker.is_open(host):
            raise IngestionError(f"circuit breaker open for host {host}", details={"host": host})

        last_error: str | None = None
        for attempt in range(settings.max_retries + 1):
            self.limiter.acquire(host, self.policy)
            started = time.perf_counter()
            try:
                response = self._client.get(full_url, headers=headers)
                elapsed = (time.perf_counter() - started) * 1000
                result = FetchResult(
                    url=full_url,
                    status_code=response.status_code,
                    text=response.text,
                    headers=dict(response.headers),
                    elapsed_ms=round(elapsed, 2),
                    retries=attempt,
                    robots_allowed=decision.allowed,
                    robots_rule=decision.rule,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                    self.limiter.penalise(host, retry_after or settings.retry_backoff_seconds * (attempt + 1))
                    last_error = f"HTTP {response.status_code}"
                    self._record(
                        full_url,
                        "GET",
                        response.status_code,
                        elapsed,
                        len(result.text),
                        decision.allowed,
                        decision.rule,
                        False,
                        attempt,
                        last_error,
                    )
                    if attempt < settings.max_retries and response.status_code in RETRYABLE_STATUS:
                        time.sleep(settings.retry_backoff_seconds * (2**attempt))
                        continue
                    self.breaker.record_failure(host)
                    if response.status_code == 429:
                        raise RateLimitError(f"rate limited by {host}", details={"url": full_url})
                    return result

                self.breaker.record_success(host)
                self._write_cache(result)
                self._record(
                    full_url,
                    "GET",
                    response.status_code,
                    elapsed,
                    len(result.text),
                    decision.allowed,
                    decision.rule,
                    False,
                    attempt,
                )
                return result

            except RETRYABLE_EXCEPTIONS as exc:
                elapsed = (time.perf_counter() - started) * 1000
                last_error = f"{type(exc).__name__}: {exc}"
                self._record(
                    full_url,
                    "GET",
                    None,
                    elapsed,
                    0,
                    decision.allowed,
                    decision.rule,
                    False,
                    attempt,
                    last_error,
                )
                if attempt < settings.max_retries:
                    time.sleep(settings.retry_backoff_seconds * (2**attempt))
                    continue
                self.breaker.record_failure(host)
                raise IngestionError(f"request failed: {last_error}", details={"url": full_url}) from exc

        self.breaker.record_failure(host)
        raise IngestionError(
            f"exhausted {settings.max_retries} retries for {full_url}",
            details={"url": full_url, "last_error": last_error},
        )

    def get_json(self, url: str, **kwargs: Any) -> Any:
        """GET + JSON decode with a helpful error message on malformed payloads."""
        result = self.get(url, **kwargs)
        if not result.ok:
            raise IngestionError(
                f"unexpected status {result.status_code} for {url}",
                details={"url": url, "status_code": result.status_code},
            )
        try:
            return result.json()
        except ValueError as exc:
            raise IngestionError(f"invalid JSON from {url}", details={"url": url}) from exc

    def get_soup(self, url: str, **kwargs: Any):
        """GET + parse into a BeautifulSoup document (lxml parser)."""
        from bs4 import BeautifulSoup

        result = self.get(url, **kwargs)
        if not result.ok:
            raise IngestionError(
                f"unexpected status {result.status_code} for {url}",
                details={"url": url, "status_code": result.status_code},
            )
        return BeautifulSoup(result.text, "lxml")

    # ------------------------------------------------------------------ audit
    def _record(
        self,
        url: str,
        method: str,
        status_code: int | None,
        elapsed_ms: float,
        size: int,
        robots_allowed: bool | None,
        rule: str | None,
        from_cache: bool,
        retries: int = 0,
        error: str | None = None,
    ) -> None:
        self.audit.append(
            HttpAuditEntry(
                url=url,
                method=method,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                response_bytes=size,
                robots_allowed=robots_allowed,
                robots_rule=rule,
                from_cache=from_cache,
                retry_count=retries,
                error=error,
            )
        )

    def audit_rows(self) -> list[dict[str, Any]]:
        """Flush buffered audit rows shaped for ``ingestion_http_log``."""
        return [entry.as_row(self.run_id, self.source_code) for entry in self.audit]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CompliantHttpClient:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


# --------------------------------------------------------------------------------------
# Process-wide singletons (one connection pool + one limiter for the whole process)
# --------------------------------------------------------------------------------------
_limiter: RateLimiter | None = None
_breaker: CircuitBreaker | None = None


def _shared_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(
            requests_per_second=settings.requests_per_second,
            requests_per_minute=settings.requests_per_minute,
            min_delay_seconds=settings.crawl_delay_fallback_seconds,
            burst=max(1, int(settings.requests_per_second)),
        )
    return _limiter


def _shared_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        _breaker = CircuitBreaker()
    return _breaker


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            delta = parsedate_to_datetime(value) - _utcnow()
            return max(0.0, delta.total_seconds())
        except Exception:
            return None


def _utcnow():
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc)


def get_shared_limiter() -> RateLimiter:
    return _shared_limiter()


__all__ = ["CompliantHttpClient", "FetchResult", "HttpAuditEntry", "get_shared_limiter"]
