"""Router registry."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    analytics,
    audit,
    auth,
    builder,
    catalog,
    changes,
    exports,
    health,
    notifications,
    pipeline,
    products,
    quality,
    queries,
    saved_views,
    settings,
    sources,
    users,
)

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    auth.router,
    users.router,
    products.router,
    changes.router,
    analytics.router,
    pipeline.router,
    quality.router,
    catalog.router,
    sources.router,
    queries.router,
    builder.router,
    saved_views.router,
    notifications.router,
    settings.router,
    audit.router,
    exports.router,
)

__all__ = ["ROUTERS"]
