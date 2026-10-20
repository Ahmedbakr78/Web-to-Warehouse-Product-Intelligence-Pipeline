"""Router registry."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    account,
    analytics,
    audit,
    auth,
    builder,
    catalog,
    changes,
    exports,
    forecast,
    health,
    jobs,
    notifications,
    pipeline,
    products,
    quality,
    queries,
    reports,
    saved_views,
    settings,
    sources,
    stream,
    users,
    webhooks,
)

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    auth.router,
    account.router,
    users.router,
    products.router,
    changes.router,
    analytics.router,
    forecast.router,
    pipeline.router,
    quality.router,
    reports.router,
    catalog.router,
    sources.router,
    queries.router,
    builder.router,
    saved_views.router,
    notifications.router,
    settings.router,
    audit.router,
    exports.router,
    webhooks.router,
    jobs.router,
    stream.router,
)

__all__ = ["ROUTERS"]
