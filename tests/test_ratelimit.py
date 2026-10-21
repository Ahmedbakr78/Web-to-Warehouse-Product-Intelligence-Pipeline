"""Tests for the rate limiter, circuit breaker and robots decision cache."""

from __future__ import annotations

import time

from app.ingestion.ratelimit import CircuitBreaker, RateLimiter, RatePolicy
from app.ingestion.robots import RobotsCache, RobotsDecision


# --------------------------------------------------------------------------------------
# Rate limiter
# --------------------------------------------------------------------------------------
def test_limiter_allows_the_first_request_immediately():
    limiter = RateLimiter(requests_per_second=1, requests_per_minute=60, min_delay_seconds=0, burst=1)
    started = time.perf_counter()
    limiter.acquire("host")
    assert time.perf_counter() - started < 0.05


def test_limiter_enforces_the_minimum_gap():
    limiter = RateLimiter(
        requests_per_second=100, requests_per_minute=60_000, min_delay_seconds=0.05, burst=1
    )
    limiter.acquire("host")
    started = time.perf_counter()
    limiter.acquire("host")
    waited = time.perf_counter() - started
    assert waited >= 0.04, "the second request must respect the configured delay"


def test_limiter_uses_crawl_delay_when_higher():
    limiter = RateLimiter(requests_per_second=1000, requests_per_minute=60_000, min_delay_seconds=0, burst=1)
    limiter.set_crawl_delay("host", 0.05)
    limiter.acquire("host")
    started = time.perf_counter()
    limiter.acquire("host")
    assert time.perf_counter() - started >= 0.04


def test_limiter_penalise_throttles_host():
    limiter = RateLimiter(requests_per_second=1000, requests_per_minute=60_000, min_delay_seconds=0, burst=10)
    limiter.penalise("host", 0.2)
    started = time.perf_counter()
    limiter.acquire("host")
    assert time.perf_counter() - started >= 0.15


def test_limiter_is_per_host():
    limiter = RateLimiter(
        requests_per_second=100, requests_per_minute=60_000, min_delay_seconds=0.05, burst=1
    )
    limiter.acquire("a")
    started = time.perf_counter()
    limiter.acquire("b")  # a different host must not wait
    assert time.perf_counter() - started < 0.03


def test_limiter_stats_and_reset():
    limiter = RateLimiter(requests_per_second=1000, requests_per_minute=60_000, min_delay_seconds=0, burst=5)
    for _ in range(3):
        limiter.acquire("host")
    stats = limiter.stats()
    assert stats["requests"] >= 3
    assert stats["hosts"] == 1
    limiter.reset()
    assert limiter.stats()["hosts"] == 0


def test_custom_policy_overrides_defaults():
    limiter = RateLimiter(requests_per_second=100, requests_per_minute=60_000, min_delay_seconds=0, burst=1)
    limiter.acquire(
        "host", RatePolicy(requests_per_second=1, requests_per_minute=10, min_delay_seconds=0.05, burst=1)
    )
    started = time.perf_counter()
    limiter.acquire(
        "host", RatePolicy(requests_per_second=1, requests_per_minute=10, min_delay_seconds=0.05, burst=1)
    )
    assert time.perf_counter() - started >= 0.04


# --------------------------------------------------------------------------------------
# Circuit breaker
# --------------------------------------------------------------------------------------
def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=3, reset_seconds=60)
    for _ in range(2):
        breaker.record_failure("host")
    assert breaker.is_open("host") is False
    breaker.record_failure("host")
    assert breaker.is_open("host") is True


def test_circuit_breaker_resets_on_success():
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=60)
    breaker.record_failure("host")
    breaker.record_success("host")
    assert breaker.is_open("host") is False


def test_circuit_breaker_recovers_after_reset_window():
    breaker = CircuitBreaker(failure_threshold=1, reset_seconds=0.05)
    breaker.record_failure("host")
    assert breaker.is_open("host") is True
    time.sleep(0.08)
    assert breaker.is_open("host") is False


# --------------------------------------------------------------------------------------
# robots.txt cache
# --------------------------------------------------------------------------------------
def test_local_and_synthetic_sources_skip_robots():
    cache = RobotsCache()
    decision = cache.can_fetch("local://demo-catalogue/products")
    assert decision.allowed is True


def test_decision_dataclass_is_truthy():
    assert bool(RobotsDecision(allowed=True, rule="robots.txt:allow")) is True
    assert bool(RobotsDecision(allowed=False, rule="robots.txt:disallow")) is False


def test_an_unauthorised_robots_txt_disallows_the_host(monkeypatch):
    """RFC 9309: a 401/403 on robots.txt means the whole host is off limits.

    A site that refuses to publish its robots.txt has not granted permission
    to crawl it, so the request must not be made.
    """
    import urllib.error

    from app.ingestion import robots as robots_module

    def refuse(url, *args, **kwargs):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    monkeypatch.setattr(robots_module.urllib.request, "urlopen", refuse)
    cache = robots_module.RobotsCache()
    decision = cache.can_fetch("https://example.com/products")
    assert decision.allowed is False
    assert "unauthorised" in decision.rule


def test_an_unavailable_robots_txt_allows_the_host(monkeypatch):
    """RFC 9309: any other 4xx means the file is unavailable -> allow."""
    import urllib.error

    from app.ingestion import robots as robots_module

    def missing(url, *args, **kwargs):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(robots_module.urllib.request, "urlopen", missing)
    cache = robots_module.RobotsCache()
    decision = cache.can_fetch("https://example.com/products")
    assert decision.allowed is True
    # An unavailable file is treated as an allow-all policy, so the rule
    # reads as a normal allow rather than as a failure.
    assert "unauthorised" not in decision.rule


def test_the_fallback_rule_does_not_claim_an_allow_list():
    """The rule string must describe the decision that was actually made."""
    from app.ingestion import robots as robots_module

    cache = robots_module.RobotsCache()
    decision = cache.can_fetch("local://demo-catalogue/products")
    assert "allow-listed" not in decision.rule


def test_the_compliance_policy_matches_what_the_code_does():
    """The stated policy and the implemented policy must agree.

    ``app/ingestion/compliance.py`` is the single statement of the rules. A
    guarantee that the code no longer honours is a false claim, so the
    outcomes the policy declares are checked against the decisions the
    transport actually makes.
    """
    from app.ingestion import compliance

    assert compliance.POLICY_VERSION
    assert compliance.GUARANTEES

    # The policy knows which outcomes let a request through, and the
    # unauthorised one is not among them.
    assert "unauthorised" not in compliance.allowed_outcomes()
    assert "unavailable" in compliance.allowed_outcomes()

    # Every outcome the policy describes has a rule string that names the
    # decision it makes.
    for outcome in compliance.ROBOTS_POLICY:
        rule = compliance.rule_for(outcome)
        assert (
            rule
            and rule != "robots.txt:allow"
            or outcome
            in {
                "unavailable",
                "not-applicable",
            }
        )
