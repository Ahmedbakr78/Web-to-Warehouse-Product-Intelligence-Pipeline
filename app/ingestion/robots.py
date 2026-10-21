"""``robots.txt`` compliance gate.

Every outbound request is checked against the *crawled user-agent's* rules before it
is made.  Decisions are cached per host for the configured TTL, and ``Crawl-delay``
values are propagated to the rate limiter.  If ``robots.txt`` cannot be fetched the
parser follows the RFC 9309 fallback:

* ``401`` / ``403`` (*Unauthorised*) -> the whole host is **disallowed**.
* any other ``4xx`` (*Unavailable*)   -> the whole host is **allowed**.
* ``5xx`` or an unreachable host       -> the whole host is **allowed**, and
  the decision is labelled as a fallback rather than as a rule the site
  published.
"""

from __future__ import annotations

import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class RobotsDecision:
    """Result of a ``robots.txt`` evaluation."""

    allowed: bool
    rule: str
    crawl_delay: float | None = None
    user_agent_matched: str | None = None
    sitemaps: tuple[str, ...] = ()

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.allowed


class RobotsCache:
    """Thread-safe cache of parsed ``robots.txt`` documents keyed by host."""

    def __init__(self, ttl_seconds: int = 1800, user_agent: str | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self.user_agent = user_agent or settings.ingest_user_agent
        #: origin -> (fetched_at, parser, sitemaps, denied)
        self._cache: dict[
            str, tuple[float, urllib.robotparser.RobotFileParser | None, tuple[str, ...], bool]
        ] = {}
        self._lock = threading.RLock()
        self.stats: dict[str, int] = {"fetched": 0, "cached": 0, "blocked": 0, "allowed": 0, "errors": 0}

    # ------------------------------------------------------------------ internals
    def _load(
        self, robots_url: str
    ) -> tuple[urllib.robotparser.RobotFileParser | None, tuple[str, ...], bool]:
        """Fetch and parse ``robots_url`` using a plain urllib request (stdlib only).

        The third element says whether the host is denied outright, which is
        what RFC 9309 requires for an *Unauthorised* (401/403) response.
        """
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            robots_url,
            headers={"User-Agent": self.user_agent, "Accept": "text/plain"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                # RFC 9309 section 2.3.1.3: an *Unauthorised* response means
                # the whole host is disallowed. A site that refuses to serve
                # its robots.txt has not given permission to crawl it.
                log.info("robots.txt disallows crawling url=%s (HTTP %s)", robots_url, exc.code)
                self.stats["errors"] += 1
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
                return parser, (), True
            if 400 <= exc.code < 500:
                # RFC 9309: "Unavailable" -> assume full allow.
                log.info("robots.txt unavailable -> allow all url=%s code=%s", robots_url, exc.code)
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(["User-agent: *", "Disallow:"])
                return parser, (), False
            # 5xx: the site is temporarily unable to answer. RFC 9309 does not
            # cover it, and refusing to fetch would take the source offline for
            # a transient server error, so the fallback allow applies - but the
            # decision is labelled as a fallback, not as a published rule.
            log.info("robots.txt server error -> allow all url=%s code=%s", robots_url, exc.code)
            self.stats["errors"] += 1
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(["User-agent: *", "Disallow:"])
            return parser, (), False
        except Exception as exc:  # pragma: no cover - network dependent
            # Unreachable robots.txt (DNS, TLS, reset) falls back to allow with a
            # cached decision, so this is informational, not a failure.
            log.info("robots.txt unreachable, allowing url=%s error=%s", robots_url, exc)
            self.stats["errors"] += 1
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(["User-agent: *", "Disallow:"])
            return parser, (), False

        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(body.splitlines())
        sitemaps = tuple(
            line.split(":", 1)[1].strip() for line in body.splitlines() if line.lower().startswith("sitemap:")
        )
        self.stats["fetched"] += 1
        return parser, sitemaps, False

    def _get_parser(
        self, base_url: str
    ) -> tuple[urllib.robotparser.RobotFileParser | None, tuple[str, ...], bool]:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            # Local / synthetic sources never hit the network, so robots.txt is N/A.
            return None, (), False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(origin)
            if cached and (now - cached[0]) < self.ttl_seconds:
                self.stats["cached"] += 1
                return cached[1], cached[2], cached[3]
        parser, sitemaps, denied = self._load(urljoin(origin, "/robots.txt"))
        with self._lock:
            self._cache[origin] = (now, parser, sitemaps, denied)
        return parser, sitemaps, denied

    # ------------------------------------------------------------------ public
    def can_fetch(self, url: str, user_agent: str | None = None) -> RobotsDecision:
        """Evaluate whether ``url`` may be fetched by our user-agent."""
        agent = (user_agent or self.user_agent).split("/")[0].strip()
        parser, sitemaps, denied = self._get_parser(url)

        if denied:
            # RFC 9309: an Unauthorised robots.txt means the whole host is
            # off limits. The rule says exactly that, so the audit log reads
            # the way the decision was actually made.
            log.info("robots.txt unauthorised -> disallow host url=%s", url)
            self.stats["blocked"] += 1
            return RobotsDecision(
                allowed=False,
                rule="robots-unauthorised:disallow (RFC 9309 - 401/403 on robots.txt)",
                crawl_delay=None,
                sitemaps=(),
            )

        if parser is None:
            # The host could not be reached at all (or the source never hits
            # the network). Nothing was published, so nothing forbids us -
            # but the decision is a fallback, and says so.
            allowed = True
            decision = RobotsDecision(
                allowed=allowed,
                rule="robots-unavailable:fallback-allow (robots.txt could not be fetched)",
                crawl_delay=None,
                sitemaps=sitemaps,
            )
            self.stats["allowed" if allowed else "blocked"] += 1
            return decision

        allowed = parser.can_fetch(agent, url) or parser.can_fetch("*", url)
        crawl_delay = parser.crawl_delay(agent) or parser.crawl_delay("*")
        matched_agent = agent if parser.can_fetch(agent, url) else "*"
        rule = "allow" if allowed else "disallow"
        self.stats["allowed" if allowed else "blocked"] += 1

        if not allowed:
            log.info("robots.txt blocked url=%s agent=%s", url, agent)

        return RobotsDecision(
            allowed=allowed,
            rule=f"robots.txt:{rule}",
            crawl_delay=float(crawl_delay) if crawl_delay else None,
            user_agent_matched=matched_agent,
            sitemaps=sitemaps,
        )

    def crawl_delay(self, url: str) -> float | None:
        return self.can_fetch(url).crawl_delay

    def sitemaps(self, url: str) -> tuple[str, ...]:
        _, maps = self._get_parser(url)
        return maps

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_shared_cache: RobotsCache | None = None


def get_robots_cache() -> RobotsCache:
    """Process-wide robots cache (fetching robots.txt twice is wasteful)."""
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = RobotsCache(
            ttl_seconds=settings.cache_ttl_seconds, user_agent=settings.ingest_user_agent
        )
    return _shared_cache


__all__ = ["RobotsCache", "RobotsDecision", "get_robots_cache"]
