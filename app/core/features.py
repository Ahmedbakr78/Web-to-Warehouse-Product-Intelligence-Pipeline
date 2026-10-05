"""Structured feature catalogue: one source of truth for the API, dashboard and docs.

    The catalogue powers ``GET /meta/features`` (consumed by the dashboard's
    Features screen) and keeps the marketing surface (README, docs, website)
    aligned with what is actually implemented - a feature only appears here
    once it is shipped and covered by tests.

Each group carries a ``key``, a human ``title``, a Lucide icon name (used by
the dashboard), a one-line ``summary`` and the list of shipped features.
"""

from __future__ import annotations

from typing import Any

FEATURE_GROUPS: list[dict[str, Any]] = [
    {
        "key": "integrations",
        "title": "Integrations: export, webhooks & backfill",
        "icon": "plug-zap",
        "summary": "Get data out and events in: signed webhooks with retries, CSV/JSON export of every dataset, and historical backfill.",
        "features": [
            {
                "name": "12 exportable datasets",
                "detail": "Products, price changes, new/removed, runs, DQ, catalog, categories, movers, sources, alerts, audit, HTTP audit",
            },
            {
                "name": "CSV and JSON downloads",
                "detail": "GET /export/{dataset}.csv|.json with a date-stamped filename and a JSON envelope",
            },
            {
                "name": "Filter-aware exports",
                "detail": "Every dataset declares its filters (source, status, severity, search) and they are bound, never interpolated",
            },
            {
                "name": "Bounded exports",
                "detail": "Row cap enforced in SQL (50k) so a download can never exhaust memory",
            },
            {
                "name": "Export preview endpoint",
                "detail": "GET /export/{dataset} returns the first rows as JSON for in-app previews",
            },
            {
                "name": "Outbound webhooks",
                "detail": "Per-user subscriptions filtered by event, with in-app test delivery",
            },
            {
                "name": "HMAC-SHA256 signing",
                "detail": "X-Webhook-Signature over timestamp+body, so receivers can verify authenticity and detect replays",
            },
            {
                "name": "10 pipeline events",
                "detail": "run.completed/failed/started, dq.failed, price.spike, product.new/removed, catalog.mismatch, alert.triggered, backfill.completed",
            },
            {
                "name": "Delivery retries",
                "detail": "Exponential backoff (30s, 5m, 30m) up to a per-subscription attempt limit",
            },
            {
                "name": "Delivery log",
                "detail": "Status code, duration, response excerpt and error stored per attempt",
            },
            {
                "name": "Secret rotation",
                "detail": "Per-subscription signing secret, shown once and rotatable without recreating the hook",
            },
            {
                "name": "SSRF-safe targets",
                "detail": "Only public http(s) URLs accepted; loopback, private, link-local and metadata endpoints are blocked",
            },
            {
                "name": "Auto-disable on failure",
                "detail": "A subscription is disabled after repeated consecutive failures so it cannot slow the pipeline",
            },
            {
                "name": "Historical backfill",
                "detail": "Replay any date range, one run per day, up to 31 days per job",
            },
            {
                "name": "Backfill job tracking",
                "detail": "Every day tagged with the job id, with progress, per-day results and roll-up counts",
            },
            {
                "name": "Fault-isolated backfill",
                "detail": "A failing day is recorded and the job continues, so one bad source cannot abandon the range",
            },
        ],
    },
    {
        "key": "observability",
        "title": "Run comparison & observability",
        "icon": "git-compare-arrows",
        "summary": "Judge every run against any other: metric deltas, DQ regressions, catalogue movement and price drift.",
        "features": [
            {
                "name": "Compare any two runs",
                "detail": "GET /pipeline/runs/compare?base=&target= diffs a reference run against the current one",
            },
            {
                "name": "12 metric deltas",
                "detail": "Records, duplicates, new/removed products, catalog matches and DQ counts with absolute and percentage change",
            },
            {
                "name": "DQ regression detection",
                "detail": "Rules that turned red since the base run, and rules that were fixed",
            },
            {
                "name": "Catalogue movement",
                "detail": "Products added and dropped between the two runs, with display names",
            },
            {
                "name": "Price movement ranking",
                "detail": "Largest price moves between runs, sorted by absolute delta",
            },
            {
                "name": "Performance comparison",
                "detail": "Duration delta and percentage, so regressions in runtime are visible",
            },
            {
                "name": "Safe on empty baseline",
                "detail": "Zero baselines report a null percentage instead of dividing by zero",
            },
        ],
    },
    {
        "key": "ingestion",
        "title": "Ingestion & web compliance",
        "icon": "globe",
        "summary": "Permitted public sources collected politely: robots.txt, rate limits, retries, cache.",
        "features": [
            {
                "name": "5 bundled sources",
                "detail": "3 JSON APIs, 1 BeautifulSoup/LXML HTML scraper, 1 offline fixture",
            },
            {
                "name": "robots.txt gate (RFC 9309)",
                "detail": "Parsed once per host, cached, honoured per request",
            },
            {
                "name": "Token-bucket rate limiter",
                "detail": "Per-source requests/second, requests/minute and crawl-delay floors",
            },
            {
                "name": "Circuit breaker",
                "detail": "Opens after repeated failures, half-open probes, auto reset",
            },
            {
                "name": "Response cache",
                "detail": "Content-addressed JSON cache with TTL - demo-friendly and fast",
            },
            {
                "name": "Retry with backoff",
                "detail": "Exponential backoff, capped retries, per-request audit",
            },
            {
                "name": "Terms allow-list",
                "detail": "Only sources whose terms permit automated access are ever fetched",
            },
            {
                "name": "HTTP audit log",
                "detail": "Every outbound request recorded with robots decision and timing",
            },
            {
                "name": "Source health checks",
                "detail": "Registry metadata, rate limits, paging capability, live preview",
            },
        ],
    },
    {
        "key": "cleaning",
        "title": "Cleaning & normalisation",
        "icon": "sparkles",
        "summary": "29-step cleaner turning messy web text into warehouse-ready records.",
        "features": [
            {"name": "Product-name cleaner", "detail": "Case, punctuation, volume suffixes, marketing noise"},
            {"name": "Category normaliser", "detail": "Levels, slugs, taxonomy tree derivation"},
            {
                "name": "Price parser",
                "detail": "Ranges, was/pricing text, thousands separators, 18+ currency symbols",
            },
            {"name": "Currency conversion", "detail": "Offline FX table to USD - no external dependency"},
            {"name": "Rating parser", "detail": "Stars, counts, 0-5 scaling"},
            {"name": "Availability normaliser", "detail": "in_stock / out_of_stock / pre_order / unknown"},
            {"name": "Brand extraction", "detail": "Cleaned and validated against the product name"},
            {"name": "URL validation", "detail": "Scheme + host sanity before anything is stored"},
            {"name": "Quality flags", "detail": "Unparseable price, missing rating, unknown availability..."},
        ],
    },
    {
        "key": "dedupe",
        "title": "Duplicate resolution",
        "icon": "copy",
        "summary": "Fuzzy fingerprints keep one row per real-world product.",
        "features": [
            {"name": "Name fingerprints", "detail": "Normalised key + brand folding"},
            {"name": "Blocking keys", "detail": "O(n) candidate pools instead of all-pairs comparison"},
            {"name": "Levenshtein similarity"},
            {"name": "Jaro-Winkler similarity"},
            {"name": "Token-set similarity"},
            {"name": "Trigram similarity"},
            {"name": "Digit signature match", "detail": "Model numbers survive textual noise"},
            {
                "name": "Combined strategy + score",
                "detail": "Best-of similarity with 0.90 threshold (configurable)",
            },
        ],
    },
    {
        "key": "warehouse",
        "title": "Warehouse model",
        "icon": "database",
        "summary": "23-table Kimball star schema on PostgreSQL 16 and MySQL 8.4.",
        "features": [
            {"name": "Star schema", "detail": "5 dimensions, 5 fact/change tables, aggregates"},
            {"name": "Cross-dialect DDL", "detail": "One SQLAlchemy 2.0 model set, three databases"},
            {
                "name": "20 analytical views",
                "detail": "KPI, price history, movers, coverage, reconciliation...",
            },
            {"name": "Staging zone", "detail": "Raw observations kept verbatim with reject reasons"},
            {"name": "Historical snapshots", "detail": "fact_price_snapshot keyed by (product, run)"},
            {"name": "Slow-changing dimensions", "detail": "Category assignments tracked over time"},
            {"name": "Idempotent loads", "detail": "Re-runs converge to the same warehouse state"},
        ],
    },
    {
        "key": "etl",
        "title": "ETL pipeline",
        "icon": "workflow",
        "summary": "9 instrumented stages with per-stage timings and counters.",
        "features": [
            {
                "name": "extract -> stage -> transform -> resolve -> load -> detect -> reconcile -> quality -> aggregate"
            },
            {
                "name": "Per-stage timings",
                "detail": "Every run records stage durations for the Pipeline screen",
            },
            {"name": "Run history", "detail": "Status, counters, sources, trigger, actor"},
            {"name": "Failure isolation", "detail": "One dead source never kills the run"},
            {"name": "Manual trigger API", "detail": "Async or sync, any source mix, any dialect"},
            {"name": "CLI", "detail": "17 Typer commands: bootstrap, seed, verify, run, report..."},
        ],
    },
    {
        "key": "changes",
        "title": "Change detection",
        "icon": "trending-up",
        "summary": "The four SQL questions answered continuously, plus drift and bands.",
        "features": [
            {"name": "Price changes", "detail": "Direction, delta, percent, significance, magnitude band"},
            {"name": "New products", "detail": "First-sighting events with source attribution"},
            {"name": "Removed products", "detail": "Absent-from-source detection with grace window"},
            {"name": "Category changes", "detail": "Reclassification events and category drift report"},
            {"name": "Recurring products", "detail": "Back-in-stock sightings"},
            {"name": "Change timeline", "detail": "Daily activity feed powering the dashboard charts"},
        ],
    },
    {
        "key": "catalog",
        "title": "Catalog reconciliation",
        "icon": "git-compare",
        "summary": "Internal SKUs matched against the market, with price-gap analysis.",
        "features": [
            {"name": "Fuzzy SKU matching", "detail": "Same dedupe stack, tuned for catalog rows"},
            {"name": "Match strategies", "detail": "fingerprint / token / trigram with scores"},
            {"name": "Price-gap analysis", "detail": "Absolute and percent gaps vs internal prices"},
            {"name": "Pricing opportunities", "detail": "Where the market is cheaper or dearer"},
            {"name": "Reconciliation summary", "detail": "Match rate, mismatches, strategy mix"},
        ],
    },
    {
        "key": "quality",
        "title": "Data quality",
        "icon": "shield-check",
        "summary": "12 rules across 6 dimensions with a 0-100 score and a blocking gate.",
        "features": [
            {
                "name": "12 DQ rules",
                "detail": "Uniqueness, completeness, validity, consistency, timeliness, accuracy",
            },
            {"name": "Quality score", "detail": "Weighted 0-100 score per run"},
            {"name": "Pass/warn/fail severities", "detail": "Only critical failures block the DAG"},
            {"name": "History & trend", "detail": "90-day score trend on the Quality screen"},
            {"name": "Run-scoped results", "detail": "Every rule result tied to its pipeline run"},
        ],
    },
    {
        "key": "analytics",
        "title": "Analytics & SQL reporting",
        "icon": "bar-chart-3",
        "summary": "20 views + 8 standalone analysis scripts, ported across dialects.",
        "features": [
            {"name": "Headline KPIs", "detail": "Products, sources, price bands, ratings, stock mix"},
            {"name": "Price trends", "detail": "Category price index, volatility, std-dev"},
            {"name": "Top movers", "detail": "Largest absolute and relative movement"},
            {"name": "Source coverage matrix", "detail": "Products, observations, success rate per source"},
            {"name": "Category & brand leaderboards"},
            {"name": "Availability analysis"},
            {
                "name": "CSV exports",
                "detail": "Products, price-change report, catalog report, compliance report",
            },
            {"name": "Read-only query lab", "detail": "SELECT/WITH/EXPLAIN console over all views"},
        ],
    },
    {
        "key": "api",
        "title": "REST API",
        "icon": "plug",
        "summary": "110+ documented operations, consistent envelopes, typed responses.",
        "features": [
            {"name": "OpenAPI 3.1 schema", "detail": "Swagger UI + ReDoc out of the box"},
            {"name": "Consistent error envelope", "detail": "{error, message, details} everywhere"},
            {"name": "Pagination + facets", "detail": "Cursor-free paging, filter facets, suggestions"},
            {"name": "GZip + timing headers", "detail": "X-Process-Time-Ms, X-Database on every response"},
            {"name": "Rate limiting", "detail": "Per-key and per-user request budgets"},
            {
                "name": "Service metadata",
                "detail": "/meta, /meta/tables, /meta/features, /version, /stats/tables",
            },
            {
                "name": "View builder API",
                "detail": "POST /builder/query: server-side group-by + aggregate + filter",
            },
        ],
    },
    {
        "key": "security",
        "title": "Security & access control",
        "icon": "lock",
        "summary": "Argon2id, JWT rotation, API keys, RBAC, lockouts, audit.",
        "features": [
            {"name": "Argon2id password hashing", "detail": "Auto rehash on login"},
            {"name": "JWT access + refresh", "detail": "Rotation, issuer checks, type separation"},
            {"name": "API keys", "detail": "pip_-prefixed, SHA-256 + pepper, scopes, expiry, revocation"},
            {"name": "3-role RBAC", "detail": "viewer / analyst / admin with server-side enforcement"},
            {"name": "Brute-force lockout", "detail": "5 attempts -> 15-minute lock, audited"},
            {"name": "Full audit trail", "detail": "Every mutating action logged with IP and user agent"},
            {"name": "Own-activity feed", "detail": "GET /audit/me for the Account screen"},
            {
                "name": "Account self-service",
                "detail": "Profile, password, preferences, data export, account deletion",
            },
        ],
    },
    {
        "key": "dashboard",
        "title": "Dashboard & user experience",
        "icon": "layout-dashboard",
        "summary": "19 screens, 5 themes, 12 accents, PWA, command palette, phone tab bar.",
        "features": [
            {
                "name": "19 analytic screens",
                "detail": "Dashboard, Analytics, Changes, Products, Catalog, Quality, Sources and more",
            },
            {
                "name": "5 themes",
                "detail": "Light, dark, midnight (OLED), high contrast and system; switched via CSS "
                "variables with no flash and no re-render",
            },
            {
                "name": "12 accent colours",
                "detail": "Indigo, blue, sky, cyan, teal, emerald, green, amber, orange, rose, pink, violet",
            },
            {"name": "3 density levels", "detail": "Compact, comfortable, spacious"},
            {
                "name": "5 font scales",
                "detail": "Independent of density, so dense rows and large text can coexist",
            },
            {
                "name": "3 motion levels",
                "detail": "Full, reduced, none - none also stops the loading spinners",
            },
            {"name": "RTL support", "detail": "The whole layout mirrors using CSS logical properties"},
            {"name": "Command palette", "detail": "Ctrl/Cmd-K or / - screens, products, actions"},
            {
                "name": "Keyboard shortcuts",
                "detail": "Ctrl/Cmd-B toggles navigation, [ and ] collapse or expand the rail",
            },
            {
                "name": "Three-state sidebar",
                "detail": "Expanded, icon rail, or off-canvas drawer; the choice is shared across tabs",
            },
            {"name": "Phone bottom tab bar", "detail": "Five primary destinations under 640px"},
            {
                "name": "Card-view tables on phones",
                "detail": "Dense data tables become stacked cards below 640px instead of a "
                "horizontal scroller",
            },
            {
                "name": "Silent reload",
                "detail": "No smooth scroll, no page transition, scroll position restored on back, "
                "focus moved to the page heading",
            },
            {"name": "Modern scrollbars", "detail": "Custom thin scrollbars with scroll shadows and no scroll chaining"},
            {"name": "PWA", "detail": "Installable, maskable icons, offline fallback"},
            {"name": "Accessibility", "detail": "WCAG 2.1 AA: focus rings, ARIA, reduced motion"},
            {"name": "Notification centre", "detail": "Bell, unread badge, mark read, alert rules"},
            {
                "name": "Feature catalogue screen",
                "detail": "Searchable list of everything the platform ships, counts read from /meta/features",
            },
        ],
    },
    {
        "key": "operations",
        "title": "Operations, orchestration & DX",
        "icon": "settings",
        "summary": "Airflow DAG, Docker Compose stack, CI, 44 make targets.",
        "features": [
            {"name": "Airflow 2.10 DAG", "detail": "14 tasks, guards, branching, pool, retries with backoff"},
            {
                "name": "REST-transport fallback",
                "detail": "DAG drives the pipeline via API when SQLAlchemy pins conflict",
            },
            {"name": "Report artifacts", "detail": "Every run publishes a JSON KPI artifact"},
            {
                "name": "Docker Compose stack",
                "detail": "api, postgres, mysql, airflow-webserver, airflow-scheduler, frontend",
            },
            {
                "name": "GitHub Actions CI",
                "detail": "4 jobs: backend, databases (PG+MySQL), api-smoke, frontend",
            },
            {"name": "44 Make targets", "detail": "make everything / make check one-command verification"},
            {"name": "78-check API smoke suite"},
            {
                "name": "Static project website",
                "detail": "website/index.html - one-file premium landing page",
            },
        ],
    },
]


def feature_catalogue() -> dict[str, Any]:
    """The catalogue in the shape served by ``GET /meta/features``."""
    groups = [
        {
            "key": group["key"],
            "title": group["title"],
            "icon": group["icon"],
            "summary": group["summary"],
            "feature_count": len(group["features"]),
            "features": [dict(feature) for feature in group["features"]],
        }
        for group in FEATURE_GROUPS
    ]
    return {
        "total_features": sum(group["feature_count"] for group in groups),
        "total_groups": len(groups),
        "groups": groups,
    }


def feature_names() -> list[str]:
    """Flat names (used by ``GET /meta``)."""
    return [feature["name"] for group in FEATURE_GROUPS for feature in group["features"]]


__all__ = ["FEATURE_GROUPS", "feature_catalogue", "feature_names"]
