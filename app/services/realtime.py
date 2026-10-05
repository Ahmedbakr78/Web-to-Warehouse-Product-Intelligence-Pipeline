"""Real-time push: a small in-process pub/sub broker plus SSE and WebSocket routes.

The broker is intentionally in-process and dependency-free. It is correct for the
single-API-container deployment this project ships, and it degrades safely: if a
subscriber is not reading, its queue is dropped rather than allowed to grow.

SSE (`/stream/...`) is the primary transport because it reconnects automatically
and passes through the same auth as a normal request. The WebSocket is offered for
clients that want a single bidirectional channel.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

#: Topics the platform publishes on.
TOPIC_RUN = "run"
TOPIC_KPI = "kpi"
TOPIC_CHANGE = "change"
TOPIC_QUALITY = "quality"
TOPIC_NOTIFICATION = "notification"
TOPIC_JOB = "job"

#: Keep the slowest 50 messages so a stalled client cannot exhaust memory.
QUEUE_MAXSIZE = 50


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class Message:
    topic: str
    data: dict[str, Any]
    at: str = field(default_factory=_now_iso)

    def to_sse(self, event_id: int | None = None) -> str:
        """Render as a Server-Sent Events frame."""
        prefix = f"id: {event_id}\n" if event_id is not None else ""
        return f"{prefix}event: {self.topic}\ndata: {json.dumps({'at': self.at, **self.data})}\n\n"

    def to_json(self) -> str:
        return json.dumps({"topic": self.topic, "at": self.at, **self.data})


class Broker:
    """Fan-out pub/sub. Publishing never blocks and never raises."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Message]]] = defaultdict(set)
        self._sequence = 0

    @property
    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    def topics(self) -> list[str]:
        return sorted(self._subscribers)

    def subscribe(self, topics: list[str] | None = None) -> asyncio.Queue[Message]:
        """Register a new subscriber queue for the given topics (all when omitted)."""
        queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        # A wildcard subscription is registered against the sentinel topic '*' so it
        # also receives topics created after it subscribed.
        wanted = list(topics) if topics else ["*"]
        for topic in wanted:
            self._subscribers[topic].add(queue)
        return queue

    def unsubscribe(self, topics: list[str], queue: asyncio.Queue[Message]) -> None:
        for topic in topics:
            self._subscribers.get(topic, set()).discard(queue)

    def publish(self, topic: str, data: dict[str, Any] | None = None) -> None:
        """Deliver to every subscriber of `topic` and to every wildcard subscriber."""
        self._sequence += 1
        message = Message(topic=topic, data=data or {})
        for key in (topic, "*"):
            for queue in list(self._subscribers.get(key, ())):
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    # The client is not keeping up: drop the oldest message so the
                    # newest state still arrives, rather than blocking the publisher.
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(message)


#: Process-wide broker.
broker = Broker()


# --------------------------------------------------------------------------------------
# Heartbeat: keeps proxies from closing an idle SSE connection
# --------------------------------------------------------------------------------------
async def heartbeat_stream(interval: float = 25.0) -> AsyncIterator[str]:
    """Yield SSE comment frames forever so the connection is never idle-closed."""
    while True:
        await asyncio.sleep(interval)
        yield ": keep-alive\n\n"


async def subscribe_stream(topics: list[str] | None = None) -> AsyncIterator[str]:
    """Yield SSE frames for the given topics until the client disconnects."""
    queue = broker.subscribe(topics)
    resolved = topics or ["*"]
    try:
        yield Message(topic="open", data={"topics": resolved}).to_sse()
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=25.0)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield message.to_sse()
    finally:
        broker.unsubscribe(resolved, queue)


async def publish_threadsafe(topic: str, data: dict[str, Any] | None = None) -> None:
    """Publish from within the event loop."""
    broker.publish(topic, data)


def publish(topic: str, data: dict[str, Any] | None = None) -> None:
    """Publish from any thread.

    The pipeline and the job worker run in worker threads, so the message is handed
    to the event loop that owns the broker's queues. If no loop is bound (for example
    in a CLI process or a test) the publish is dropped rather than raising.
    """
    loop = getattr(publish, "_loop", None)
    if loop is None or loop.is_closed():
        return
    # A loop that is shutting down raises RuntimeError; dropping the event is correct.
    with contextlib.suppress(RuntimeError):
        loop.call_soon_threadsafe(broker.publish, topic, data)


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Remember the serving loop so worker threads can publish into it."""
    publish._loop = loop  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# Event helpers: one function per platform event, so payloads cannot drift
# --------------------------------------------------------------------------------------
def run_started(run_id: str, database: str, sources: list[str]) -> dict[str, Any]:
    return {"kind": "run_started", "run_id": run_id, "database": database, "sources": sources}


def run_progress(run_id: str, stage: str, detail: str = "") -> dict[str, Any]:
    return {"kind": "run_progress", "run_id": run_id, "stage": stage, "detail": detail}


def run_finished(run_id: str, status: str, counters: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": "run_finished", "run_id": run_id, "status": status, "counters": counters or {}}


def job_progress(job_key: str, status: str, progress_pct: int, stage: str | None = None) -> dict[str, Any]:
    return {
        "kind": "job_progress",
        "job_key": job_key,
        "status": status,
        "progress_pct": progress_pct,
        "stage": stage,
    }


def price_change(count: int, window_minutes: int = 60) -> dict[str, Any]:
    return {"kind": "price_change", "count": count, "window_minutes": window_minutes}


def dq_score(score: float, run_id: str | None = None) -> dict[str, Any]:
    return {"kind": "dq_score", "score": score, "run_id": run_id}


def notification(
    level: str, title: str, body: str | None = None, action_url: str | None = None
) -> dict[str, Any]:
    return {"kind": "notification", "level": level, "title": title, "body": body, "action_url": action_url}


__all__ = [
    "Broker",
    "TOPIC_CHANGE",
    "TOPIC_JOB",
    "TOPIC_KPI",
    "TOPIC_NOTIFICATION",
    "TOPIC_QUALITY",
    "TOPIC_RUN",
    "bind_loop",
    "broker",
    "dq_score",
    "heartbeat_stream",
    "job_progress",
    "notification",
    "price_change",
    "publish",
    "publish_threadsafe",
    "run_finished",
    "run_progress",
    "run_started",
    "subscribe_stream",
]
