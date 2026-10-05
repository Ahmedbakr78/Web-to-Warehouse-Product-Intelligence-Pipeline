"""Realtime endpoints: Server-Sent Events and a WebSocket.

SSE is the primary transport because the browser reconnects it automatically and it
passes through the same bearer-token auth as any other request. The WebSocket is
provided for clients that want one bidirectional channel.

`EventSource` cannot set headers, so these routes accept the credential as a query
parameter too (see `stream_user`). That is a transport concession only: the role and
API-key scope checks are the same ones every other read goes through.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.analytics import service as analytics
from app.api.deps import ReadUser, StreamUser, _resolve_token, get_session_factory
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.models.app_users import AppJobEvent
from app.services.realtime import (
    TOPIC_CHANGE,
    TOPIC_JOB,
    TOPIC_KPI,
    TOPIC_NOTIFICATION,
    TOPIC_QUALITY,
    TOPIC_RUN,
    broker,
)

log = get_logger(__name__)

router = APIRouter(prefix="/stream", tags=["realtime"])

#: What a client may subscribe to.
TOPICS = {
    "run": TOPIC_RUN,
    "job": TOPIC_JOB,
    "kpi": TOPIC_KPI,
    "change": TOPIC_CHANGE,
    "quality": TOPIC_QUALITY,
    "notification": TOPIC_NOTIFICATION,
}

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # Without this an nginx or CDN proxy will buffer the stream and nothing arrives
    # until the connection closes.
    "X-Accel-Buffering": "no",
}


def _resolve_topics(requested: list[str] | None) -> list[str]:
    if not requested:
        return list(TOPICS.values())
    resolved: list[str] = []
    for name in requested:
        topic = TOPICS.get(name.strip().lower())
        if topic is None:
            raise ValueError(f"unknown topic '{name}'; known topics: {', '.join(sorted(TOPICS))}")
        resolved.append(topic)
    return resolved


@router.get("/runs", summary="SSE: pipeline run progress")
async def stream_runs(_user: StreamUser, topics: Annotated[str | None, Query()] = None) -> StreamingResponse:
    selected = _resolve_topics(topics.split(",") if topics else ["run"])
    return StreamingResponse(
        _frames(selected),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/kpis", summary="SSE: KPI and price-change counters")
async def stream_kpis(_user: StreamUser, topics: Annotated[str | None, Query()] = None) -> StreamingResponse:
    selected = _resolve_topics(topics.split(",") if topics else ["kpi", "change", "quality"])
    return StreamingResponse(
        _frames(selected),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/notifications", summary="SSE: in-app notifications as they are created")
async def stream_notifications(_user: StreamUser) -> StreamingResponse:
    return StreamingResponse(
        _frames([TOPIC_NOTIFICATION]),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/everything", summary="SSE: every topic")
async def stream_everything(_user: StreamUser) -> StreamingResponse:
    return StreamingResponse(
        _frames(list(TOPICS.values())),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _frames(topics: list[str]) -> AsyncIterator[str]:
    """Merge the in-memory broker with a database poll.

    The broker only carries events published in *this* process, so with more than one
    Uvicorn worker a job executed by another process would be invisible. Polling
    `app_job_event` closes that gap: every process sees every event, and the poll is
    a cheap indexed `id > last` query.
    """
    from app.services.realtime import Message

    queue_obj = broker.subscribe(topics)
    resolved = topics
    last_event_id = _latest_job_event_id()
    try:
        yield Message(topic="open", data={"topics": resolved}).to_sse()
        while True:
            try:
                message = await asyncio.wait_for(queue_obj.get(), timeout=5.0)
                yield message.to_sse()
                continue
            except TimeoutError:
                pass
            # No broker traffic: check whether another worker wrote new progress.
            fresh = _job_events_since(last_event_id)
            for event in fresh:
                last_event_id = max(last_event_id, int(event["event_id"]))
                yield Message(
                    topic="job",
                    data={
                        "kind": "job_progress",
                        "job_id": event["job_id"],
                        "event_id": event["event_id"],
                        "level": event["level"],
                        "stage": event["stage"],
                        "message": event["message"],
                        "progress_pct": event["progress_pct"],
                    },
                ).to_sse(event_id=event["event_id"])
            if not fresh:
                yield ": keep-alive\n\n"
    finally:
        broker.unsubscribe(resolved, queue_obj)


def _latest_job_event_id() -> int:
    from app.core.db import read_session

    try:
        with read_session() as session:
            return int(session.execute(sa.select(sa.func.max(AppJobEvent.event_id))).scalar() or 0)
    except Exception:  # noqa: BLE001 - the stream must survive a DB blip
        return 0


def _job_events_since(after_id: int, limit: int = 50) -> list[dict[str, Any]]:
    from app.core.db import read_session

    try:
        with read_session() as session:
            # Materialise the scalars inside the session: ORM objects become detached
            # the moment it closes, and a detached attribute access raises.
            rows = session.execute(
                sa.select(
                    AppJobEvent.event_id,
                    AppJobEvent.job_id,
                    AppJobEvent.level,
                    AppJobEvent.stage,
                    AppJobEvent.message,
                    AppJobEvent.progress_pct,
                )
                .where(AppJobEvent.event_id > after_id)
                .order_by(AppJobEvent.event_id)
                .limit(limit)
            ).all()
    except Exception:  # noqa: BLE001 - the stream must survive a DB blip
        return []
    return [
        {
            "event_id": row[0],
            "job_id": row[1],
            "level": row[2],
            "stage": row[3],
            "message": row[4],
            "progress_pct": row[5],
        }
        for row in rows
    ]


@router.get("/snapshot", summary="Current KPI snapshot (the same payload SSE pushes)")
def snapshot(_user: ReadUser, days: Annotated[int, Query(ge=1, le=365)] = 1) -> dict[str, Any]:
    """A polling-friendly alternative to the stream, and the SSE client's first paint."""
    from app.core.db import read_session

    with read_session() as session:
        return {
            "kpi": analytics.kpi_summary(session, days=days),
            "changes": analytics.change_event_summary(session, days=days),
            "subscribers": broker.subscriber_count,
            "topics": broker.topics(),
        }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """A bidirectional channel: send `{"action":"subscribe","topics":["run"]}`."""
    token = websocket.query_params.get("token")
    if not token:
        # The browser WebSocket API cannot set an Authorization header, so the token
        # arrives as a query parameter. It is still verified exactly the same way.
        await websocket.close(code=4401, reason="missing token")
        return
    try:
        session = get_session_factory()()
        try:
            _resolve_token(session, _bearer(token))
        finally:
            session.close()
    except AuthenticationError:
        await websocket.close(code=4401, reason="invalid token")
        return
    except Exception:  # noqa: BLE001 - never leak the reason on the wire
        log.warning("websocket authentication failed", exc_info=True)
        await websocket.close(code=4401, reason="authentication failed")
        return

    await websocket.accept()
    # Say hello immediately: a client that waits for a first frame would otherwise
    # sit idle until the first keep-alive, up to 25 seconds later.
    await websocket.send_json({"topic": "open", "topics": list(TOPICS)})
    queue_obj = broker.subscribe(list(TOPICS.values()))
    resolved = list(TOPICS.values())

    async def pump() -> None:
        while True:
            try:
                message = await asyncio.wait_for(queue_obj.get(), timeout=25.0)
            except TimeoutError:
                await websocket.send_json({"topic": "keepalive"})
                continue
            await websocket.send_text(message.to_json())

    async def listen() -> None:
        while True:
            payload = await websocket.receive_json()
            action = str(payload.get("action", "")).lower()
            if action == "subscribe":
                names = payload.get("topics") or []
                try:
                    wanted = _resolve_topics([str(name) for name in names])
                except ValueError as exc:
                    await websocket.send_json({"topic": "error", "message": str(exc)})
                    continue
                broker.unsubscribe(resolved, queue_obj)
                for topic in wanted:
                    broker._subscribers[topic].add(queue_obj)
                resolved[:] = wanted
                await websocket.send_json({"topic": "subscribed", "topics": wanted})
            elif action == "ping":
                await websocket.send_json({"topic": "pong"})
            elif action == "close":
                break

    pump_task = asyncio.create_task(pump())
    listen_task = asyncio.create_task(listen())
    try:
        done, pending = await asyncio.wait({pump_task, listen_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        broker.unsubscribe(resolved, queue_obj)
        for task in (pump_task, listen_task):
            if not task.done():
                task.cancel()


def _bearer(token: str) -> Any:
    """Wrap a raw token in the credential object `_resolve_token` expects."""
    from fastapi.security import HTTPAuthorizationCredentials

    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


__all__ = ["router"]
