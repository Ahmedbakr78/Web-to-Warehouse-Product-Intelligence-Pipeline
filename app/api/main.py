"""FastAPI application factory, lifespan, error handlers and OpenAPI metadata."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.ratelimit import rate_limit_middleware
from app.api.routers import ROUTERS
from app.api.schemas import ErrorResponse
from app.core.config import settings
from app.core.db import dispose_all, ping
from app.core.errors import PipelineError
from app.core.logging import get_logger

log = get_logger(__name__)

API_PREFIX = "/api/v1"

DESCRIPTION = """
**Web-to-Warehouse Product Intelligence Pipeline** - REST API.

The API exposes the analytical warehouse built from permitted public web sources:

* `products` - canonical, deduplicated product catalogue with facets and price history
* `changes` - price changes, new products, removals and category drift
* `analytics` - KPI cards, trends, leaderboards and SQL reports
* `forecast` - price projections, anomaly detection, elasticity and price recommendations
* `pipeline` - run history, manual triggers, stage timings, source health
* `quality` - the 12-rule data-quality framework and its historical results
* `catalog` - reconciliation against the retailer's internal catalog (price gaps)
* `queries` - read-only SQL console plus the list of analytical views
* `builder` - compose, aggregate and save custom views without writing SQL
* `exports` - CSV/JSON datasets and PDF-ready report rendering
* `webhooks` - signed outbound notifications for pipeline and data events
* `jobs` - durable background queue with progress, cancellation and live streaming
* `stream` - Server-Sent Events and a WebSocket for live run and KPI updates
* `users` / `settings` / `audit` - account, preference and compliance management

### Authentication

1. `POST /api/v1/auth/login` with the documented demo credentials.
2. Send `Authorization: Bearer <access_token>` on every subsequent call.
3. Machine clients may instead use an API key (`pip_...`) created via
   `POST /api/v1/users/{id}/api-keys`.

### Roles

| role | capabilities |
| ---- | ------------ |
| `viewer` | read, query, export |
| `analyst` | + write, run_pipeline, alerts, saved views |
| `admin` | + manage sources, users, settings, audit |
"""

TAGS_METADATA: list[dict[str, Any]] = [
    {"name": "system", "description": "Health, readiness, metadata and feature catalogue."},
    {"name": "authentication", "description": "Login, token rotation, profile session and password change."},
    {"name": "users", "description": "Account management, roles, API keys and usage statistics."},
    {
        "name": "products",
        "description": "Deduplicated product catalogue, facets, price history and duplicates.",
    },
    {
        "name": "changes",
        "description": "Price changes, new/removed products, lifecycle events and category drift.",
    },
    {"name": "analytics", "description": "Dashboard KPIs, trends, leaderboards, exports and SQL reports."},
    {
        "name": "forecasting",
        "description": "Holt-Winters price forecasts with measured accuracy, robust anomaly "
        "detection, price elasticity and recommended prices.",
    },
    {
        "name": "pipeline",
        "description": "Run history, manual triggers, stage timings, source and scheduler status.",
    },
    {
        "name": "data-quality",
        "description": "Rule catalogue, latest report, historical results and score trend.",
    },
    {"name": "catalog", "description": "Internal catalog SKUs, reconciliation and pricing opportunities."},
    {
        "name": "sources",
        "description": "Registered ingestion sources, robots.txt statistics and raw previews.",
    },
    {"name": "query-lab", "description": "Read-only SQL console, views and starter queries."},
    {"name": "saved-views", "description": "Per-user filter presets for list screens."},
    {"name": "notifications", "description": "In-app notifications and user alert rules."},
    {"name": "settings", "description": "Global application settings (admin only for writes)."},
    {"name": "audit", "description": "Application audit trail and outbound HTTP compliance evidence."},
    {"name": "exports", "description": "Dataset exports in CSV and JSON, plus PDF report rendering."},
    {"name": "webhooks", "description": "Signed outbound webhooks with delivery retries and audit."},
    {
        "name": "jobs",
        "description": "Durable background queue: enqueue, inspect, cancel, retry and stream progress.",
    },
    {
        "name": "realtime",
        "description": "Server-Sent Events and WebSocket streams for live run, KPI and notification updates.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown: verify the database and warm the app."""
    import asyncio

    from app.jobs import start_worker, stop_worker
    from app.services.realtime import bind_loop

    settings.ensure_directories()
    bind_loop(asyncio.get_running_loop())
    health = ping()
    if health["connected"]:
        log.info(
            "api ready: database=%s dialect=%s tables=%s",
            health["database"],
            health["dialect"],
            health["tables"],
        )
        if settings.seed_demo_data:
            _ensure_reference_data()
    else:
        log.warning("api started but the database is unreachable: %s", health["error"])

    if health["connected"]:
        start_worker()

    yield

    stop_worker()
    dispose_all()
    log.info("api shutdown complete")


def _ensure_reference_data() -> None:
    """Create the demo accounts/settings on first boot (never fails the boot)."""
    try:
        from app.core.db import session_scope
        from app.etl.seed import seed_users

        with session_scope() as session:
            seed_users(session)
    except Exception as exc:  # pragma: no cover - never block startup
        log.warning("could not seed reference users: %s", exc)


def create_app() -> FastAPI:
    """Application factory (used by uvicorn, the CLI and the tests)."""
    app = FastAPI(
        title=f"{settings.app_name} API",
        description=DESCRIPTION,
        version=settings.app_version,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "Ahmed Abobakr"},
        license_info={"name": "MIT"},
    )

    # ------------------------------------------------------------------ middleware
    # Added last, so it is the outermost layer: a rejected request never reaches
    # the database, which is the point of having a budget at all.
    app.middleware("http")(rate_limit_middleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time-Ms", "X-Database", "Content-Disposition"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def add_timing_headers(request: Request, call_next: Any) -> Any:
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Process-Time-Ms"] = str(elapsed)
        response.headers["X-Database"] = settings.active_database
        if elapsed > 2000:
            log.warning("slow request %s %s took %sms", request.method, request.url.path, elapsed)
        return response

    # ------------------------------------------------------------------ error handlers
    @app.exception_handler(PipelineError)
    async def pipeline_error_handler(request: Request, exc: PipelineError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
                "path": request.url.path,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Request validation failed",
                "details": {
                    "errors": [
                        {
                            "field": ".".join(str(part) for part in error.get("loc", [])[1:]),
                            "message": error.get("msg"),
                            "type": error.get("type"),
                        }
                        for error in exc.errors()
                    ][:20]
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": f"http_{exc.status_code}", "message": str(exc.detail), "details": {}},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred",
                "details": {"type": type(exc).__name__} if settings.app_debug else {},
            },
        )

    # ------------------------------------------------------------------ routes
    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, Any]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "health": f"{API_PREFIX}/health",
            "api_prefix": API_PREFIX,
        }

    return app


app = create_app()

__all__ = ["app", "create_app", "API_PREFIX", "ErrorResponse"]
