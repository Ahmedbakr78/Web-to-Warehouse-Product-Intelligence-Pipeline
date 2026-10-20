"""Intelligence endpoints: the prioritized morning briefing.

This is a thin transport layer over :mod:`app.analytics.briefing`, which composes
existing analytics services. Every insight links back to the screen where the
user can act on it, so the briefing never becomes a dead-end report.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.analytics.briefing import build_briefing
from app.api.deps import DbSession, ReadUser

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get(
    "/briefing",
    summary="Prioritized morning briefing: opportunities, risks and actions",
)
def briefing(
    session: DbSession,
    _user: ReadUser,
    days: Annotated[int, Query(ge=1, le=3650, description="Analysis window in days")] = 30,
    limit: Annotated[int, Query(ge=1, le=20, description="Items per section")] = 6,
) -> dict[str, Any]:
    return build_briefing(session, days=days, limit=limit)
