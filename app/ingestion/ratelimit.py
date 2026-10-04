"""Host-aware rate limiting (token bucket + sliding window) and crawl-delay support.

Two complementary mechanisms are combined so the pipeline stays a good citizen:

* **Token bucket** - smooths the average request rate per host.
* **Sliding window** - enforces a hard ceiling per minute even if bursts are allowed.

``robots.txt`` ``Crawl-delay`` values always win over the configured defaults, and a
``Retry-After`` header from a 429/503 response dynamically throttles the host.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class RatePolicy:
    """Per-host request budget."""

    requests_per_second: float = 1.0
    requests_per_minute: int = 30
    min_delay_seconds: float = 0.0
    burst: int = 3


@dataclass
class HostState:
    """Mutable limiter state for a single host."""

    policy: RatePolicy
    tokens: float = field(default=0.0)
    last_refill: float = field(default_factory=time.monotonic)
    last_request: float = 0.0
    window: deque[float] = field(default_factory=deque)
    cooldown_until: float = 0.0
    crawl_delay: float = 0.0
    total_requests: int = 0
    total_wait_seconds: float = 0.0

    @property
    def effective_delay(self) -> float:
        """Slowest of the global delay, the per-minute budget and robots crawl-delay."""
        per_minute_delay = 60.0 / self.policy.requests_per_minute if self.policy.requests_per_minute else 0.0
        return max(self.policy.min_delay_seconds, per_minute_delay, self.crawl_delay)


class RateLimiter:
    """Thread-safe, multi-host rate limiter with dynamic crawl-delay support."""

    def __init__(
        self,
        requests_per_second: float = 1.0,
        requests_per_minute: int = 30,
        min_delay_seconds: float = 0.0,
        burst: int = 3,
    ) -> None:
        self.default_policy = RatePolicy(
            requests_per_second=requests_per_second,
            requests_per_minute=requests_per_minute,
            min_delay_seconds=min_delay_seconds,
            burst=burst,
        )
        self._hosts: dict[str, HostState] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ helpers
    def _state(self, host: str, policy: RatePolicy | None = None) -> HostState:
        with self._lock:
            state = self._hosts.get(host)
            if state is None:
                state = HostState(policy=policy or self.default_policy, tokens=self.default_policy.burst)
                self._hosts[host] = state
            elif policy is not None:
                state.policy = policy
            return state

    def _refill(self, state: HostState) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - state.last_refill)
        rate = state.policy.requests_per_second
        if rate > 0:
            state.tokens = min(state.policy.burst, state.tokens + elapsed * rate)
        state.last_refill = now

    # ------------------------------------------------------------------ public
    def acquire(self, host: str = "default", policy: RatePolicy | None = None) -> float:
        """Block until a request to ``host`` is allowed. Returns the seconds waited."""
        state = self._state(host, policy)
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                self._refill(state)

                if now < state.cooldown_until:
                    sleep_for = state.cooldown_until - now
                else:
                    self._prune_window(state, now)
                    window_delay = 0.0
                    if len(state.window) >= state.policy.requests_per_minute:
                        window_delay = max(0.0, state.window[0] + 60.0 - now) + 0.01
                    gap_delay = max(0.0, state.effective_delay - (now - state.last_request))
                    token_delay = 0.0 if state.tokens >= 1.0 else (1.0 - state.tokens) / max(
                        state.policy.requests_per_second, 0.001
                    )
                    sleep_for = max(window_delay, gap_delay, token_delay)

                if sleep_for <= 0:
                    state.tokens -= 1.0
                    state.last_request = now
                    state.window.append(now)
                    state.total_requests += 1
                    state.total_wait_seconds += waited
                    return waited

                state.total_wait_seconds += sleep_for
                waited += sleep_for
            time.sleep(min(sleep_for, 5.0))

    def penalise(self, host: str, seconds: float) -> None:
        """Throttle a host after 429/503 or a ``Retry-After`` header."""
        with self._lock:
            state = self._state(host)
            state.cooldown_until = max(state.cooldown_until, time.monotonic() + max(0.0, seconds))
        log.warning("host throttled host=%s seconds=%.1f", host, seconds)

    def set_crawl_delay(self, host: str, seconds: float) -> None:
        """Apply a ``Crawl-delay`` advertised in ``robots.txt``."""
        with self._lock:
            state = self._state(host)
            state.crawl_delay = max(0.0, float(seconds or 0.0))
        log.info("crawl-delay applied host=%s seconds=%.2f", host, state.crawl_delay)

    def stats(self, host: str | None = None) -> dict[str, float | int]:
        with self._lock:
            hosts = [host] if host else list(self._hosts)
            snapshot = {name: self._hosts[name] for name in hosts if name in self._hosts}
            return {
                "hosts": len(self._hosts),
                "requests": sum(s.total_requests for s in snapshot.values()),
                "wait_seconds": round(sum(s.total_wait_seconds for s in snapshot.values()), 3),
            }

    def reset(self) -> None:
        with self._lock:
            self._hosts.clear()

    @staticmethod
    def _prune_window(state: HostState, now: float) -> None:
        cutoff = now - 60.0
        while state.window and state.window[0] < cutoff:
            state.window.popleft()


class CircuitBreaker:
    """Tiny circuit breaker that stops hammering a dead host."""

    def __init__(self, failure_threshold: int = 5, reset_seconds: float = 120.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}
        self._lock = threading.RLock()

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._opened_at.pop(key, None)

    def record_failure(self, key: str) -> None:
        with self._lock:
            count = self._failures.get(key, 0) + 1
            self._failures[key] = count
            if count >= self.failure_threshold:
                self._opened_at[key] = time.monotonic()
                log.error("circuit opened key=%s failures=%d", key, count)

    def is_open(self, key: str) -> bool:
        with self._lock:
            opened = self._opened_at.get(key)
            if opened is None:
                return False
            if time.monotonic() - opened > self.reset_seconds:
                self._failures.pop(key, None)
                self._opened_at.pop(key, None)
                return False
            return True


__all__ = ["RateLimiter", "RatePolicy", "CircuitBreaker"]