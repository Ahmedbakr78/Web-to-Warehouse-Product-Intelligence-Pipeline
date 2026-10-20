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
                "name": "Excel (.xlsx) downloads",
                "detail": "GET /export/{dataset}.xlsx with native dates/decimals, bold header, freeze + autofilter",
            },
            {
                "name": "Export format picker",
                "detail": "One ExportButton offers CSV, Excel and JSON on every dataset screen",
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
        "key": "gui_sources",
        "title": "GUI source onboarding",
        "icon": "globe",
        "summary": "Add a JSON feed from the dashboard: compliance proof first, field mapping second, no deploy.",
        "features": [
            {
                "name": "Add-source dialog",
                "detail": "Name, code, endpoint, mapping and politeness on the Sources screen, one save away from enabled",
            },
            {
                "name": "Endpoint presets",
                "detail": "DummyJSON, FakeStore, Shopify products.json, Open Food Facts and Open Library mappings in one click",
            },
            {
                "name": "Compliance pre-check",
                "detail": "SSRF guard plus a live robots.txt verdict before anything is saved",
            },
            {
                "name": "JSON shape sniff",
                "detail": "One bounded GET reports item keys and counts so the mapping is filled from evidence",
            },
            {
                "name": "Server-side re-check",
                "detail": "Create re-verifies robots itself; a blocked endpoint is rejected even if the pre-check was skipped",
            },
            {
                "name": "Generic JSON adapter",
                "detail": "Dot-path fields, three pagination styles, URL templates; dashboard rows run the same pipeline",
            },
            {
                "name": "Source lifecycle controls",
                "detail": "Enable, disable and delete (guarded by run history) for dashboard rows; bundled rows are read-only",
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
                "name": "9 bundled sources",
                "detail": "6 JSON APIs, 2 BeautifulSoup/LXML HTML scrapers, 1 offline fixture",
            },
            {
                "name": "Steam Store API",
                "detail": "Curated games: cent prices with discount pairs, genres, review-score mapping",
            },
            {
                "name": "Open Food Facts Prices",
                "detail": "Crowd-observed grocery prices: multi-currency, discount pairs, store + country",
            },
            {
                "name": "Rejected sources logged",
                "detail": "iTunes Search API refused: /search disallowed by robots.txt — compliance over coverage",
            },
            {
                "name": "ScrapeMe.live practice shop",
                "detail": "WooCommerce sandbox: GBP prices, sale pairs, stock flags, category slugs",
            },
            {
                "name": "Google Books API",
                "detail": "Official Books API with optional free key (GOOGLE_BOOKS_API_KEY)",
            },
            {
                "name": "FreeAPI demo products",
                "detail": "100-item catalogue: price, brand, category, rating, stock, discount pairs",
            },
            {
                "name": "Predic8 fruit shop",
                "detail": "Listing-detail crawl, euro prices and vendor lists for grocery lines",
            },
            {
                "name": "SampleAPIs coffee menu",
                "detail": "Hot and iced cafe drinks with ingredients and images",
            },
            {
                "name": "SampleAPIs Switch catalogue",
                "detail": "1000+ titles in one call: genres, studios, publishers, release dates",
            },
            {
                "name": "TheMealDB meals",
                "detail": "Category discovery then per-category dishes with photos",
            },
            {
                "name": "TheCocktailDB drinks",
                "detail": "Three alcohol-option filters covering the whole menu",
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
            {
                "name": "Egress proxy support",
                "detail": "Optional INGEST_PROXY_URL for all fetches with INGEST_NO_PROXY bypass list",
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
        "summary": "29-table Kimball star schema on PostgreSQL 16 and MySQL 8.4.",
        "features": [
            {"name": "Star schema", "detail": "5 dimensions, 5 fact/change tables, aggregates"},
            {"name": "Cross-dialect DDL", "detail": "One SQLAlchemy 2.0 model set, three databases"},
            {
                "name": "23 analytical views",
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
            {
                "name": "Run-scoped snapshot dedupe",
                "detail": "One row per (product, run) even when two sources resolve to the same product",
            },
            {
                "name": "Per-source savepoints",
                "detail": "A failed source rolls back alone; the run transaction stays usable",
            },
            {
                "name": "Per-source commit",
                "detail": "Each source is durable before the next starts; later deaths lose nothing",
            },
            {
                "name": "Rollback-and-reconnect",
                "detail": "Dead connections recover via pool refresh; the run continues partial",
            },
            {
                "name": "Fetch-before-transaction",
                "detail": "Slow HTTP never holds an open transaction idle during a run",
            },
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
            {
                "name": "CSV catalog import",
                "detail": "POST /catalog/import upserts 5,000 SKUs per file with per-row validation",
            },
            {
                "name": "Import template download",
                "detail": "GET /catalog/template serves header plus example rows for spreadsheets",
            },
            {
                "name": "All-or-nothing validation",
                "detail": "Any invalid row rejects the file; a half-loaded catalog is impossible",
            },
            {
                "name": "Import audit trail",
                "detail": "Every import writes catalog.import with created/updated counts and actor",
            },
            {
                "name": "One-click Catalog upload",
                "detail": "Template + Import CSV buttons on the SKUs tab with toasts and refresh",
            },
            {
                "name": "Role-gated writes",
                "detail": "Analyst and admin can import; viewers get a 403 on both UI and API",
            },
            {
                "name": "CSV catalog export",
                "detail": "GET /catalog/export.csv downloads every SKU in import-compatible columns",
            },
            {
                "name": "Import/export round-trip",
                "detail": "Export, edit in a spreadsheet, re-import: same header, upsert by sku",
            },
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
        "summary": "23 views + 8 standalone analysis scripts, ported across dialects.",
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
            {
                "name": "Query history",
                "detail": "Every execution recorded to app_query_history with rows, duration and truncation",
            },
            {
                "name": "Pinned snippets",
                "detail": "Name any run to pin it; snippets survive pruning and clearing",
            },
            {
                "name": "History panel",
                "detail": "All/snippet filter, one-click reload into the editor, per-entry delete, clear-keeps-snippets",
            },
            {
                "name": "Secret-table guard",
                "detail": "app_user, app_api_key, app_session and app_webhook are unreadable from the console",
            },
            {
                "name": "Server-side row cap",
                "detail": "The LIMIT is wrapped into the SQL so the engine never materialises unbounded results",
            },
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
            {
                "name": "Multi-level sorting",
                "detail": "Comma-separated sort_by/sort_dir, allowlisted, 3 levels, NULLS LAST both dialects",
            },
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
            {
                "name": "Per-product history CSV",
                "detail": "GET /products/{id}/history.csv: every snapshot with USD prices, 5k cap",
            },
            {
                "name": "Named file downloads",
                "detail": "Content-Disposition filenames on every CSV, PDF and template export",
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
            {
                "name": "API key rotation",
                "detail": "POST .../rotate: atomic swap, old secret dies instantly, policy inherited, audited",
            },
            {
                "name": "API key editing",
                "detail": "PATCH rename/rescope/re-budget/re-expire, owner-rights capped, audited",
            },
            {
                "name": "Grantable-scopes endpoint",
                "detail": "GET /users/me/scopes: full list plus the role-capped subset pickers may offer",
            },
            {"name": "3-role RBAC", "detail": "viewer / analyst / admin with server-side enforcement"},
            {"name": "Brute-force lockout", "detail": "5 attempts -> 15-minute lock, audited"},
            {"name": "Full audit trail", "detail": "Every mutating action logged with IP and user agent"},
            {"name": "Own-activity feed", "detail": "GET /audit/me for the Account screen"},
            {
                "name": "Account self-service",
                "detail": "Profile, password, preferences, data export, account deletion",
            },
            {
                "name": "Public self-registration",
                "detail": "POST /auth/register creates a viewer and returns tokens; role forced server-side",
            },
            {
                "name": "Registration kill-switch",
                "detail": "REGISTRATION_ENABLED=false refuses signups with 403 for centrally-provisioned fleets",
            },
            {
                "name": "Create-account screen",
                "detail": "Sign-in / sign-up mode switch on Login with full-name validation and instant sign-in",
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
                "name": "Shortcut reference dialog",
                "detail": "Press ? anywhere for every shortcut on one screen, also in the palette",
            },
            {
                "name": "Header collapse control",
                "detail": "Collapse or expand the rail from the top bar, with the state shared across tabs",
            },
            {
                "name": "Three-state sidebar",
                "detail": "Expanded, icon rail, or off-canvas drawer; the choice is shared across tabs",
            },
            {
                "name": "Rounded floating sidebar",
                "detail": "Detached rounded card with its own border and shadow; content reserves its width",
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
            {
                "name": "No scrollbars",
                "detail": "Scrollbars removed everywhere; wheel, touch, keyboard and shadows carry navigation",
            },
            {"name": "PWA", "detail": "Installable, maskable icons, offline fallback"},
            {"name": "Accessibility", "detail": "WCAG 2.1 AA: focus rings, ARIA, reduced motion"},
            {"name": "Notification centre", "detail": "Bell, unread badge, mark read, alert rules"},
            {
                "name": "Feature catalogue screen",
                "detail": "Searchable list of everything the platform ships, counts read from /meta/features",
            },
            {
                "name": "History CSV on products",
                "detail": "Export CSV button on every product page, disabled until snapshots load",
            },
            {
                "name": "Activity CSV export",
                "detail": "One-click CSV of the Account activity feed, same columns as the table",
            },
            {
                "name": "Audit-trail CSV export",
                "detail": "One-click CSV of the application audit tab with user, action and timing columns",
            },
            {
                "name": "Backtest CSV export",
                "detail": "Forecast accuracy table to CSV with MAPE, MAE and RMSE per product",
            },
            {
                "name": "Watchlist-aware product export",
                "detail": "Products CSV/JSON follows the Watched filter with watchlist filenames",
            },
            {
                "name": "Sources ExportButton",
                "detail": "One-click CSV, Excel and JSON of the source coverage dataset on the Sources screen",
            },
            {
                "name": "Alerts ExportButton",
                "detail": "One-click CSV, Excel and JSON of every alert rule on the Alerts toolbar",
            },
            {
                "name": "Runs ExportButton",
                "detail": "One-click CSV, Excel and JSON of run history beside the status filter",
            },
            {
                "name": "Side-by-side product comparison",
                "detail": "Select up to 4 products for a live server-side attribute matrix",
            },
            {
                "name": "Server-side full export",
                "detail": "Export-all downloads every filtered product, not just the visible page",
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
            {"name": "86-check API smoke suite"},
            {
                "name": "Static project website",
                "detail": "website/ - a multi-page site generated from the live OpenAPI document",
            },
            {
                "name": "Single canonical version",
                "detail": "The VERSION file feeds the API, the CLI, pyproject.toml and the dashboard, "
                "so the four can never disagree (scripts/sync_version.py enforces it)",
            },
            {
                "name": "Documentation drift gate",
                "detail": "CI fails when a measured count in the docs no longer matches the code",
            },
            {
                "name": "Rendered Mermaid diagrams",
                "detail": "Every diagram in docs/ is rendered to SVG and embedded",
            },
            {
                "name": "Presentation deck generator",
                "detail": "make deck builds a 12-slide PDF from measured counts, with a --check drift gate",
            },
        ],
    },
    {
        "key": "appearance",
        "title": "Appearance & personalisation",
        "icon": "palette",
        "summary": "Six independent axes of personalisation, applied before the first paint.",
        "features": [
            {
                "name": "Five palettes",
                "detail": "Light, dark, midnight for OLED screens, a high-contrast WCAG mode and "
                "system-follows-OS",
            },
            {"name": "Twelve accent colours", "detail": "Any colour can be applied without a rebuild"},
            {
                "name": "No flash on reload",
                "detail": "An inline pre-paint script resolves the stored preference before React mounts",
            },
            {
                "name": "System mode actually works",
                "detail": "OS dark mode is resolved through the same code path, so a server profile "
                "of `system` no longer forces light",
            },
            {
                "name": "Server-persisted profile",
                "detail": "Every appearance choice is saved to the user record, so a new device or "
                "browser inherits it",
            },
            {
                "name": "Cross-tab synchronisation",
                "detail": "Two open tabs stay visually identical via the storage event",
            },
            {
                "name": "Silent navigation",
                "detail": "Scroll is never animated; back restores the previous offset and forward "
                "starts at the top",
            },
            {
                "name": "Live dual preview",
                "detail": "The theme picker renders miniature versions of the real palettes",
            },
            {
                "name": "Font scaling",
                "detail": "Five steps from 13px to 19px, applied independently of density",
            },
            {
                "name": "RTL mirroring",
                "detail": "Logical properties flip the layout without a second stylesheet",
            },
        ],
    },
    {
        "key": "forecasting",
        "title": "Forecasting & anomaly detection",
        "icon": "trending-up",
        "summary": "Damped Holt-Winters projections with measured accuracy, three independent anomaly detectors, "
        "and pricing advice derived from elasticity.",
        "features": [
            {
                "name": "Damped Holt-Winters",
                "detail": "Trend, seasonality and damping, selected automatically from the length of the history",
            },
            {
                "name": "Prediction intervals",
                "detail": "A lower and upper bound per point, widening as the horizon grows",
            },
            {
                "name": "Two-sided confidence bands",
                "detail": "80% and 95%, because a single band hides how uncertain the projection is",
            },
            {
                "name": "Holdout backtest",
                "detail": "MAPE, MAE and RMSE measured on the tail the model never saw",
            },
            {
                "name": "Accuracy grading",
                "detail": "Each product is graded excellent, good, fair or poor from its MAPE",
            },
            {
                "name": "MAD anomaly detector",
                "detail": "Median absolute deviation, which a single outlier cannot inflate",
            },
            {"name": "Standard-deviation detector", "detail": "Flagged when the move exceeds three sigma"},
            {
                "name": "IQR fence detector",
                "detail": "Tukey fences, which do not assume the distribution is normal",
            },
            {
                "name": "Anomaly severity",
                "detail": "Ranked by z-score and labelled informational or critical",
            },
            {
                "name": "Seasonality profile",
                "detail": "Day-of-week and monthly factors expressed as an index above or below 100",
            },
            {
                "name": "Price recommendations",
                "detail": "Hold, raise, cut or negotiate, with the margin effect stated in the response",
            },
            {
                "name": "Demand elasticity",
                "detail": "Absolute price change against volume change, computed from the facts table",
            },
            {
                "name": "Forecast rebuild job",
                "detail": "Recomputed in the background, cancellable and retryable",
            },
            {
                "name": "Forecasting screen",
                "detail": "Accuracy, anomalies and a per-product projection drawn with a confidence band",
            },
            {
                "name": "Cold-start fallback",
                "detail": "Too little history returns a flat series rather than a fabricated curve",
            },
            {
                "name": "Projection CSV export",
                "detail": "Per-product forecast points with confidence bounds to CSV from the projection card",
            },
        ],
    },
    {
        "key": "jobs",
        "title": "Background job queue",
        "icon": "workflow",
        "summary": "Durable, leased, retryable background work with a persisted progress log, so nothing "
        "long-running ever holds an HTTP request open.",
        "features": [
            {
                "name": "Durable job rows",
                "detail": "Every job is a row, so a restart resumes the work instead of losing it",
            },
            {
                "name": "Lease with heartbeat",
                "detail": "A worker holds a lease and renews it; a dead worker's job is reclaimed",
            },
            {
                "name": "Bounded retry",
                "detail": "A fixed attempt budget with the last error recorded on the row",
            },
            {
                "name": "Cooperative cancellation",
                "detail": "A cancel request is honoured at the next checkpoint rather than by a kill",
            },
            {
                "name": "Persisted progress events",
                "detail": "Stage, message and percentage per step, not just a final status",
            },
            {
                "name": "Coalesced progress writes",
                "detail": "Events are buffered so a SQLite write lock cannot stall the worker",
            },
            {
                "name": "Six job types",
                "detail": "Pipeline run, backfill, export, forecast rebuild, aggregate rebuild and report PDF",
            },
            {
                "name": "Job detail endpoint",
                "detail": "Status, attempts, lease expiry, error and the whole progress log",
            },
            {
                "name": "Worker introspection",
                "detail": "Queue depth, running count and lease age, for a dashboard or an alert",
            },
            {"name": "Live jobs screen", "detail": "The same queue with SSE progress, cancel and retry"},
            {
                "name": "Enqueue returns immediately",
                "detail": "The caller gets a job reference, not a result it has to wait for",
            },
        ],
    },
    {
        "key": "realtime",
        "title": "Realtime streaming",
        "icon": "zap",
        "summary": "Server-Sent Events and WebSocket over one broker, with a database event log so a second API "
        "worker cannot hide events published by the first.",
        "features": [
            {"name": "SSE per topic", "detail": "Run, job, KPI, change, quality and notification topics"},
            {
                "name": "WebSocket channel",
                "detail": "One bidirectional connection for clients that prefer a socket",
            },
            {
                "name": "Topic filtering",
                "detail": "A client subscribes to what it actually renders, not to everything",
            },
            {
                "name": "Cross-worker delivery",
                "detail": "Events are polled from the database, not only from this process's memory",
            },
            {
                "name": "Snapshot first paint",
                "detail": "A polling-friendly snapshot, so a freshly opened screen is never blank",
            },
            {
                "name": "Keep-alive comments",
                "detail": "The connection is held open between events instead of being dropped",
            },
            {
                "name": "No proxy buffering",
                "detail": "X-Accel-Buffering off, so nginx cannot hold frames until the stream closes",
            },
            {
                "name": "Bounded client buffer",
                "detail": "A chatty topic cannot grow the browser's event array without limit",
            },
            {
                "name": "Capped exponential reconnect",
                "detail": "Backoff after a drop, so a server restart is not hammered",
            },
            {
                "name": "Query credential for EventSource",
                "detail": "The transport accepts a query token, since the browser cannot set headers; the role "
                "and scope checks are unchanged",
            },
        ],
    },
    {
        "key": "reports",
        "title": "Reports & document generation",
        "icon": "file-search",
        "summary": "Five declarative reports assembled from typed blocks and rendered identically to HTML, JSON, "
        "CSV and PDF.",
        "features": [
            {
                "name": "Executive summary",
                "detail": "Market position, data freshness and trustworthiness at a glance",
            },
            {
                "name": "Price movement report",
                "detail": "Largest movers, direction mix and per-category volatility",
            },
            {"name": "Data quality report", "detail": "Every rule, its current verdict and the score trend"},
            {
                "name": "Catalog reconciliation",
                "detail": "Our list prices against the market, and the gaps worth chasing",
            },
            {"name": "Product report", "detail": "One product's price history, movements and projection"},
            {
                "name": "Typed blocks",
                "detail": "heading, tiles, table, bars and callout, all rendered by a single renderer",
            },
            {
                "name": "Section selection",
                "detail": "Any subset of a template's sections, kept in the template's own order",
            },
            {"name": "Window parameters", "detail": "1 to 365 days, with a 1 to 60 day forecast horizon"},
            {
                "name": "HTML preview",
                "detail": "The server's own render, so the screen matches the export",
            },
            {
                "name": "PDF download",
                "detail": "WeasyPrint with Pango and Cairo, embedded fonts, headers and page numbers",
            },
            {
                "name": "Queued PDF rendering",
                "detail": "A slow render becomes a job instead of a request the caller waits on",
            },
            {
                "name": "Graceful unavailability",
                "detail": "A host without PDF support answers 501 and explains why, rather than failing at 500",
            },
            {
                "name": "CSV built from the blocks",
                "detail": "One export definition, so the CSV cannot drift away from the screen",
            },
            {
                "name": "Report builder screen",
                "detail": "Template, window, section chips and HTML, CSV and PDF export",
            },
            {
                "name": "Server report CSV",
                "detail": "GET /reports/{template}/csv: scalar facts frame plus every table block as a CSV sub-table",
            },
        ],
    },
    {
        "key": "schema",
        "title": "Schema & migrations",
        "icon": "database",
        "summary": "Alembic owns the schema: 29 tables and 23 views built from nothing, with drift detection in "
        "continuous integration.",
        "features": [
            {"name": "Alembic integrated", "detail": "Real revisions instead of create_all on every boot"},
            {
                "name": "Complete initial revision",
                "detail": "Every table the models declare, created in dependency order",
            },
            {
                "name": "Views are part of the migration",
                "detail": "The 23 analytical views are applied by the revision, not by a bootstrap afterthought",
            },
            {
                "name": "Drift check",
                "detail": "`alembic check` fails when the models and the revision disagree",
            },
            {
                "name": "Reviewed autogenerate",
                "detail": "Foreign tables are excluded so only the warehouse schema is managed",
            },
            {
                "name": "Downgrade path",
                "detail": "The revision drops its views and tables cleanly, and the gate proves it",
            },
            {
                "name": "Target-aware environment",
                "detail": "The migration target is resolved from the active database setting",
            },
            {
                "name": "Idempotent upgrade",
                "detail": "Applying an already-applied revision is a no-op rather than an error",
            },
            {
                "name": "CLI and Make targets",
                "detail": "db-upgrade, db-downgrade, db-current, db-history and db-check",
            },
            {
                "name": "Separate version table",
                "detail": "alembic_version cannot collide with a warehouse table of the same name",
            },
            {
                "name": "Dedicated Airflow database",
                "detail": "Orchestration metadata lives outside the analytical warehouse",
            },
        ],
    },
    {
        "key": "account_security",
        "title": "Two-factor & session control",
        "icon": "fingerprint",
        "summary": "TOTP two-step sign-in with recovery codes, plus per-device sessions that can be revoked "
        "individually or all at once.",
        "features": [
            {
                "name": "TOTP two-step sign-in",
                "detail": "RFC 6238, SHA-1, 30 second steps, one step of drift allowed",
            },
            {
                "name": "Enrolment QR code",
                "detail": "An otpauth:// URI plus the secret in text, for a phone or a desktop authenticator",
            },
            {
                "name": "Nothing enabled until confirmed",
                "detail": "Activation needs a real code, so a mistyped secret cannot lock anyone out of their account",
            },
            {
                "name": "Encrypted secret",
                "detail": "The shared secret is encrypted at rest, not stored in the clear",
            },
            {
                "name": "Single-use recovery codes",
                "detail": "Eight codes, stored hashed, each invalidated the moment it is used",
            },
            {
                "name": "Recovery works while locked",
                "detail": "Three wrong codes lock the second factor, but a recovery code still proves possession",
            },
            {
                "name": "Attempt counter",
                "detail": "Remaining attempts are shown before the lock, not only after it",
            },
            {
                "name": "A session per device",
                "detail": "Device, address, user agent, sign-in time and last activity",
            },
            {
                "name": "Revoke one session",
                "detail": "The refresh token behind that session is invalidated immediately",
            },
            {"name": "Sign out everywhere else", "detail": "One call invalidates every other session"},
            {
                "name": "Hashed refresh tokens",
                "detail": "Rotation stores only a digest, so a database leak is not a session leak",
            },
            {
                "name": "Persistent session handle",
                "detail": "The handle survives a reload, which is what makes revocation possible at all",
            },
            {
                "name": "Devices and 2FA screen",
                "detail": "Both controls on one Account tab, next to the password form",
            },
        ],
    },
    {
        "key": "access_control",
        "title": "API access control",
        "icon": "sliders",
        "summary": "Rate limiting with honest headers, and API-key scopes that are genuinely enforced against the "
        "owner's own rights.",
        "features": [
            {
                "name": "Sliding-window rate limit",
                "detail": "Per-client budgets in seconds and minutes, not a fixed window that resets at the edge",
            },
            {
                "name": "Standard 429 response",
                "detail": "With Retry-After, so a well-behaved client can back off correctly",
            },
            {
                "name": "Limit headers on every response",
                "detail": "The remaining budget is visible before the limit is hit, not after",
            },
            {
                "name": "Outermost middleware",
                "detail": "A rejected request never reaches the database, which is the point of having a budget",
            },
            {
                "name": "Scoped API keys",
                "detail": "A key carries its own rights, capped by what its owner holds",
            },
            {
                "name": "Scopes checked on every route",
                "detail": "A scoped key is authorised twice: against the owner, then against its own scopes",
            },
            {
                "name": "Usage counters",
                "detail": "Last used and total calls per key, which is how a leaked credential gets noticed",
            },
            {"name": "Expiring keys", "detail": "An optional expiry is rejected at authentication time"},
            {
                "name": "Key rotation",
                "detail": "Revoke the old key and issue a new one, with no gap in access",
            },
            {
                "name": "Type-preserving setting writes",
                "detail": "A type-less PUT keeps the stored value_type instead of coercing to string",
            },
            {
                "name": "Setting metadata writes",
                "detail": "Category, description and visibility are settable through the API, not just the seed",
            },
            {
                "name": "Setting audit trail",
                "detail": "Every admin setting change and deletion lands in app_audit_log",
            },
            {
                "name": "Test-env rate-limit bypass",
                "detail": "The test suite disables the API budget so file order can never 429 an unrelated test",
            },
        ],
    },
    {
        "key": "quality_gates",
        "title": "Engineering quality gates",
        "icon": "clipboard",
        "summary": "What has to pass before this project counts as working: tests, typing, lint, schema drift "
        "and a smoke run against the live stack.",
        "features": [
            {
                "name": "439 automated tests",
                "detail": "Unit and integration, running against SQLite so no service is needed",
            },
            {
                "name": "104-check API smoke run",
                "detail": "Every endpoint exercised against the running stack, in the smoke script",
            },
            {"name": "Strict typing", "detail": "mypy clean across 85 source files"},
            {"name": "Lint clean", "detail": "Ruff over app, tests, scripts, DAGs and migrations"},
            {
                "name": "Schema drift gate",
                "detail": "CI runs alembic check, so the models cannot drift away from the revision",
            },
            {
                "name": "Migration round trip",
                "detail": "Upgrade, downgrade and re-upgrade are all exercised, not just the happy path",
            },
            {
                "name": "Frontend type gate",
                "detail": "tsc, then ESLint at zero warnings, then a production build",
            },
            {
                "name": "Tests need no services",
                "detail": "A fresh clone can run the suite before Docker exists on the machine",
            },
            {
                "name": "PostgreSQL parity",
                "detail": "The same suite runs against PostgreSQL by changing a single URL",
            },
            {
                "name": "Documentation drift check",
                "detail": "A measured count in the docs that stops matching the code fails the build",
            },
            {
                "name": "Pre-commit hooks",
                "detail": "Ruff, whitespace and the stats drift gate run at commit via make precommit",
            },
        ],
    },
    {
        "key": "builder_max",
        "title": "Query & aggregate builder Max",
        "icon": "wand-2",
        "summary": "Self-service analytics without raw SQL: 11 entities, 15 operators, 6 aggregates, chart preview, generated SQL and cURL.",
        "features": [
            {
                "name": "13 builder entities",
                "detail": "products, price_changes, new/removed, category_index, brand_summary, source_coverage, top_movers, availability, quality_latest, catalog_reconciliation, pipeline_runs, alert_rules",
            },
            {
                "name": "Rows mode filters",
                "detail": "search, category, brand, source, availability, price/rating/change ranges, in-stock, significant-only",
            },
            {
                "name": "15 filter operators",
                "detail": "eq, ne, gt, gte, lt, lte, contains, not_contains, starts/ends_with, in, not_in, between, empty, not_empty",
            },
            {
                "name": "6 aggregate functions",
                "detail": "count, count_distinct, sum, avg, min, max with up to 8 measures per query",
            },
            {
                "name": "Group-by + having",
                "detail": "Server-side grouping with aggregate-aware ordering and result capping",
            },
            {
                "name": "Whitelist-assembled SQL",
                "detail": "Entity/column whitelist plus bind parameters — structurally incapable of injection",
            },
            {
                "name": "Live SQL preview",
                "detail": "POST /builder/query returns sql_preview beside columns, rows and duration_ms",
            },
            {
                "name": "cURL copy button",
                "detail": "One click copies an authenticated curl for the exact builder state",
            },
            {"name": "Chart preview", "detail": "Bar chart renders the first grouped measure instantly"},
            {
                "name": "Saved views",
                "detail": "Name any builder state, reuse it from Products/Changes screens, usage-counted",
            },
            {
                "name": "View sharing scope",
                "detail": "Private views plus usage counts; admin can audit all views",
            },
            {
                "name": "CSV export",
                "detail": "builder-{entity}.csv generated client-side from visible columns",
            },
            {"name": "JSON export", "detail": "Same rows as JSON with entity plus applied filters envelope"},
            {"name": "Column picker", "detail": "Per-entity column sets with sticky, sortable headers"},
            {
                "name": "Sort everywhere",
                "detail": "asc/desc on any whitelisted column, default sort per entity",
            },
            {
                "name": "Multi-sort editor",
                "detail": "Up to 3 tie-breaker levels on products + price-changes, single elsewhere",
            },
            {
                "name": "Pinned columns",
                "detail": "Freeze any column to the left edge; pins persist in views and links",
            },
            {
                "name": "Clone saved view",
                "detail": "Duplicate any preset under a new name instead of starting blank",
            },
            {
                "name": "Share-as-URL link",
                "detail": "base64url ?view= restores entity, filters, sorts, columns and pins",
            },
            {
                "name": "Pagination control",
                "detail": "Page-size selector persisted to profile, total + duration shown",
            },
            {"name": "Debounced search", "detail": "300ms debounce so typing never hammers the API"},
            {
                "name": "Stale-while-revalidate",
                "detail": "Cached preview first, silent refetch, no spinners on revisit",
            },
            {
                "name": "Join guidance",
                "detail": "Cross-entity recipes (products x changes x catalog) documented with example SQL",
            },
            {
                "name": "Builder schema endpoint",
                "detail": "GET /builder/schema drives entity/column/operator pickers — no hardcoded lists",
            },
            {
                "name": "12 filter-mode entities",
                "detail": "products, changes, runs, quality, catalog, new, removed, movers, sources plus categories, brands, availability",
            },
            {
                "name": "Array-preview normalisation",
                "detail": "Analytics and event entities render bare arrays; the empty-preview bug is gone",
            },
            {
                "name": "Saved views for all 12 entities",
                "detail": "The saved-view contract accepts every filter entity; unknown names still 422",
            },
            {
                "name": "Entity-aware page shortcut",
                "detail": "Open-as-a-page appears only where it resolves: the products entity",
            },
            {
                "name": "Pipeline-runs entity",
                "detail": "Group and aggregate etl_run: status, trigger, counters, DQ score per run",
            },
            {
                "name": "Alert-rules entity",
                "detail": "Group and aggregate app_alert_rule: metric, channel, trigger counts",
            },
            {
                "name": "Error envelope",
                "detail": "Unknown entity/column returns {error,message,details.available} with 422",
            },
            {"name": "Builder docs page", "detail": "docs plus QueryLab examples mirror the same whitelist"},
            {
                "name": "HAVING post-filters",
                "detail": "Post-aggregation predicates over grouping columns and aggregate aliases",
            },
            {
                "name": "AND/OR filter logic",
                "detail": "WHERE filters combine with AND or OR per request; HAVING stays AND",
            },
            {
                "name": "Groupable enforcement",
                "detail": "The schema's groupable flag is enforced server-side, not just advertised",
            },
            {
                "name": "Alias injection guard",
                "detail": "Aggregate aliases must match a strict identifier shape before interpolation",
            },
            {
                "name": "Stable grouped paging",
                "detail": "Grouped queries without a sort still emit ORDER BY, so OFFSET pages are deterministic",
            },
            {
                "name": "Capability advertisement",
                "detail": "GET /builder/schema lists filter_logic values and supported capabilities",
            },
            {
                "name": "Saved-view retrieve & update",
                "detail": "GET and PATCH one view; renames are clash-checked per user",
            },
            {
                "name": "Saved-view duplicate",
                "detail": "POST /saved-views/{id}/duplicate copies filters, sort and columns under a fresh name",
            },
            {
                "name": "Default view pinning",
                "detail": "One default per entity per user; the list endpoint sorts it first",
            },
            {
                "name": "View visibility rules",
                "detail": "Private views 404 for other users; shared views are readable but never mutable",
            },
            {
                "name": "Saved-view audit trail",
                "detail": "Create, update, duplicate, default, delete land in app_audit_log",
            },
        ],
    },
    {
        "key": "account_max",
        "title": "Account self-service Max",
        "icon": "user-cog",
        "summary": "Nine tabs of control: profile, appearance, security, devices, keys, alerts, activity, data and preferences.",
        "features": [
            {
                "name": "9 account tabs",
                "detail": "Profile, Appearance, Security, Devices & 2FA, API keys, Alerts, Activity, Data & privacy, Preferences",
            },
            {
                "name": "Avatar picker",
                "detail": "12 theme-aware colours with initials fallback, shown in topbar and sidebar",
            },
            {
                "name": "Full-name editing",
                "detail": "Validated, audited, reflected in JWT display name immediately",
            },
            {
                "name": "Password strength meter",
                "detail": "Length, variety and breach-hint feedback before submit",
            },
            {
                "name": "Rows-per-page control",
                "detail": "Persisted default page size used by every table screen",
            },
            {
                "name": "Default landing page",
                "detail": "Choose Dashboard, Analytics, Products or Pipeline as post-login route",
            },
            {
                "name": "Signed webhook alert delivery",
                "detail": "Route a rule to the user's active alert.triggered webhook subscriptions with a signed payload",
            },
            {
                "name": "Default alert threshold",
                "detail": "Per-user default that prefills the threshold when creating a price alert rule",
            },
            {
                "name": "Keyboard shortcut reference",
                "detail": "Press ? anywhere: palette, sidebar, rail, overlay shortcuts on one screen",
            },
            {
                "name": "Session timeout display",
                "detail": "Idle and absolute lifetimes visible beside each device row",
            },
            {
                "name": "Sign out everywhere",
                "detail": "One call revokes every refresh token except the current session",
            },
            {
                "name": "Recovery code download",
                "detail": "One-click .txt export at enrol time, hashed at rest, single-use",
            },
            {
                "name": "API key scopes UI",
                "detail": "read/query/run/admin checkboxes capped by owner role, shown per key",
            },
            {
                "name": "Key last-used display",
                "detail": "Relative time plus total calls — leaked credentials get noticed",
            },
            {
                "name": "Personal activity feed",
                "detail": "GET /audit/me powers the Activity tab with IP and user-agent",
            },
            {
                "name": "Portable data export",
                "detail": "GET /users/me/export downloads profile, prefs, keys metadata and activity as JSON",
            },
            {
                "name": "Danger-zone confirm",
                "detail": "DELETE /users/me needs password, cascades, writes audit, signs out",
            },
            {
                "name": "Alert rules inline",
                "detail": "Create, pause and test alert rules without leaving Account",
            },
            {
                "name": "Preference sync",
                "detail": "Appearance plus prefs saved server-side, inherited by new devices",
            },
            {
                "name": "Preferences backup",
                "detail": "Export/import pip.* plus server prefs as JSON, allowlist-validated on restore",
            },
            {
                "name": "Key rotate + edit UI",
                "detail": "Per-key Rotate, edit modal with scope picker, relative expiry, budget control",
            },
            {"name": "Cross-tab live sync", "detail": "storage event keeps two open tabs visually identical"},
            {
                "name": "Accessible forms",
                "detail": "Labels, focus rings, ARIA descriptions and keyboard-only operation",
            },
            {"name": "Toast confirmations", "detail": "Every mutation confirms with undo hint where safe"},
        ],
    },
    {
        "key": "ux_mobile_max",
        "title": "Design system, mobile & motion Max",
        "icon": "smartphone",
        "summary": "Perfect light and dark, silent reloads, fixed sidebar, Lucide icons everywhere, no scrollbars.",
        "features": [
            {
                "name": "Perfect white mode",
                "detail": "Warm paper surfaces, indigo brand ramp, AAA body text on white",
            },
            {
                "name": "Perfect dark mode",
                "detail": "Navy surfaces, lifted borders, recoloured charts with zero pure-black crush",
            },
            {"name": "Midnight OLED theme", "detail": "True-black surfaces for phones and OLED laptops"},
            {"name": "High-contrast theme", "detail": "2px borders, 3px focus rings, AAA text in both bases"},
            {
                "name": "System follows OS",
                "detail": "prefers-color-scheme resolved through the same path, no forced light",
            },
            {
                "name": "No flash on reload",
                "detail": "Inline pre-paint script resolves theme plus accent before React mounts",
            },
            {
                "name": "12 accent colours",
                "detail": "Indigo to violet applied via CSS vars without a rebuild",
            },
            {
                "name": "3 densities + 5 font scales",
                "detail": "Compact/comfortable/spacious independent of 13–19px text",
            },
            {
                "name": "3 motion levels",
                "detail": "Full/reduced/none; none also stops spinners and progress bars",
            },
            {
                "name": "Silent reload policy",
                "detail": "No route transitions, no smooth scroll, 120ms functional transitions only",
            },
            {
                "name": "Scroll restoration",
                "detail": "Back restores offset, forward starts at top, focus moves to h1",
            },
            {
                "name": "Three-state sidebar",
                "detail": "Expanded, icon rail, off-canvas drawer; choice shared across tabs",
            },
            {
                "name": "Rounded floating sidebar",
                "detail": "Detached rounded card; the content column reserves its width",
            },
            {
                "name": "Phone bottom tab bar",
                "detail": "Five primary destinations under 640px with safe-area padding",
            },
            {
                "name": "Card-view tables",
                "detail": "Dense tables become stacked cards below 640px — no horizontal blowout",
            },
            {
                "name": "Drawer scroll lock",
                "detail": "Body locked while drawer/modal open, focus trapped, Esc closes",
            },
            {
                "name": "Lucide icons everywhere",
                "detail": "Every button, modal action, tab, stat, empty state and toast — no emoji, aria-hidden decorative",
            },
            {
                "name": "Brand logo everywhere",
                "detail": "One logo in the sidebar, login, favicons, PWA icons, README and website",
            },
            {
                "name": "Skeleton-free refetch",
                "detail": "Tables keep stale rows during background refetch; skeletons only on first load",
            },
            {
                "name": "Scroll shadows",
                "detail": "Top/bottom fades driven by scrollTop vs scrollHeight via data-scroll-shadow",
            },
            {
                "name": "No scroll chaining",
                "detail": "overscroll-behavior:contain on main, nav, table-wrap and scroll areas",
            },
            {
                "name": "Stable gutter",
                "detail": "scrollbar-gutter:stable stops sideways jumps when pages grow",
            },
            {
                "name": "PWA installable",
                "detail": "Manifest, maskable icons, offline fallback, safe-area viewport from 320px",
            },
            {
                "name": "Command palette",
                "detail": "Ctrl/Cmd-K or /: screens, live products and actions with full keyboard nav",
            },
        ],
    },
    {
        "key": "platform_max",
        "title": "Platform, docs & release Max",
        "icon": "rocket",
        "summary": "Free and unlimited: one-command runs, measured docs, rendered diagrams, website and private-safe releases.",
        "features": [
            {
                "name": "44 Make targets",
                "detail": "make everything/check/up/bootstrap/demo/analysis/deck/verify-dialects and more",
            },
            {
                "name": "One-command everything",
                "detail": "install, env, databases, schema, demo data, pipeline, tests, frontend build",
            },
            {
                "name": "One-command local runner",
                "detail": "run-local.sh: version-gated preflight, foreign port-conflict guard, no-rebuild re-runs, logs/status/open actions",
            },
            {
                "name": "Single canonical version",
                "detail": "VERSION feeds API, CLI, pyproject and dashboard via sync_version.py",
            },
            {
                "name": "Stats sync gate",
                "detail": "project_stats.py rewrites README block; check_stats.py fails CI on drift",
            },
            {
                "name": "30 numbered docs",
                "detail": "Proposal through access-control, each with purpose plus Mermaid",
            },
            {
                "name": "80 Mermaid diagrams",
                "detail": "Context, stack, sequences, DAG, ER, DFD, deployment — rendered to SVG",
            },
            {
                "name": "Infographic 2560x1440",
                "detail": "One 16:9 DEPI Data Engineering slide, freshness-gated by generator",
            },
            {
                "name": "12-slide deck",
                "detail": "make deck builds PDF from measured counts in the DEPI palette",
            },
            {
                "name": "Multi-section website",
                "detail": "Hero, features from live OpenAPI, docs, quickstart, About — light/dark/system",
            },
            {
                "name": "SEO + OG tags",
                "detail": "Description, og:title/description/type, color-scheme, favicon",
            },
            {
                "name": "Public repo, private-safe",
                "detail": "Public for grading; secrets never committed, .env.example only",
            },
            {
                "name": "Topic taxonomy",
                "detail": "etl, airflow, fastapi, react, postgres, mysql, data-quality, scraping, warehouse, dashboard",
            },
            {
                "name": "Release notes",
                "detail": "Tag v1.x with changelog, counts, demo accounts and verify steps",
            },
            {
                "name": "4-job CI",
                "detail": "backend, databases PG+MySQL, api-smoke, frontend type+lint+build",
            },
            {
                "name": "6-service Compose",
                "detail": "api, postgres, mysql, airflow webserver/scheduler, frontend nginx with /api proxy",
            },
            {"name": "Nginx frontend", "detail": "Static build plus API proxy, gzip, cache headers"},
            {
                "name": "Health probes",
                "detail": "Liveness plus real DB readiness used by Compose and Airflow",
            },
            {
                "name": "Structured logs",
                "detail": "structlog with run_id, stage, duration and slow-request warnings",
            },
            {"name": "Timing headers", "detail": "X-Process-Time-Ms plus X-Database on every response"},
            {
                "name": "One-command backup",
                "detail": "make backup snapshots postgres, mysql and sqlite into a timestamped folder",
            },
            {
                "name": "Free forever stack",
                "detail": "No paid APIs: offline FX, seeded demo, SQLite-runnable tests",
            },
        ],
    },
    {
        "key": "watchlist_max",
        "title": "Watchlist & personal tracking Max",
        "icon": "star",
        "summary": "Star products into a migration-free personal watchlist that syncs with the profile and exports with it.",
        "features": [
            {
                "name": "Migration-free watchlist",
                "detail": "Stored in profile preferences JSON: no schema change, syncs to every device",
            },
            {
                "name": "Watchlist API trio",
                "detail": "GET /users/me/watchlist plus idempotent POST and DELETE per product",
            },
            {
                "name": "Star column on Products",
                "detail": "One-click star per row with filled state, toasts and live count",
            },
            {
                "name": "Watched-only filter",
                "detail": "Toolbar toggle narrows the table to starred products with its own empty state",
            },
            {
                "name": "Watch button on detail",
                "detail": "Header Watch/Watched toggle on every product page with instant feedback",
            },
            {
                "name": "Live product summaries",
                "detail": "Watchlist resolves ids against vw_product_current: price, rating, stock, source",
            },
            {
                "name": "200-item cap + validation",
                "detail": "Unknown product ids 404, malformed ids skipped, oldest trimmed past the cap",
            },
            {
                "name": "HTTP-log CSV export",
                "detail": "One-click CSV of the Audit compliance log with robots, cache and timing columns",
            },
            {
                "name": "Dark infographic artefacts",
                "detail": "2560x1440 dark SVG plus PNG and PDF, freshness-gated like the light set",
            },
            {
                "name": "One-click watchlist clear",
                "detail": "DELETE /users/me/watchlist empties the list and reports the removed count",
            },
        ],
    },
    {
        "key": "v19_polish",
        "title": "v1.9 polish: real-only defaults, theme memory & modern scrollbars",
        "icon": "sparkles",
        "summary": "Production hardening: real-network defaults, lossless theme toggle, theme-aware scrollbars, Account Sessions/Watchlist/Shortcuts tabs and per-source aggregates.",
        "features": [
            {
                "name": "Single canonical source loader",
                "detail": "load_builtin_sources imports the package once — registry can never drift from disk (31 adapters)",
            },
            {
                "name": "Real-only production defaults",
                "detail": "DAG + pipeline.default_sources default to dummyjson/fakestore/openlibrary; local_demo stays test/CI-only",
            },
            {
                "name": "Seed availability fix",
                "detail": "Unknown-availability defect no longer overwritten by RNG; null prices carry null USD",
            },
            {
                "name": "Seed catalog O(n) fix",
                "detail": "seed_catalog materialises the iterable once — no generator consumption, no quadratic len()",
            },
            {
                "name": "Per-source category aggregates",
                "detail": "refresh_category_daily(source_code) scopes and stores per-source rows instead of ignoring the arg",
            },
            {
                "name": "Lossless theme toggle",
                "detail": "Toggle remembers last dark variant (dark/midnight) in pip.last-dark; new cycle() helper",
            },
            {
                "name": "Light + dark high-contrast",
                "detail": "High-contrast follows the OS so both light-HC and dark-HC palettes are reachable",
            },
            {
                "name": "Modern theme-aware scrollbars",
                "detail": "Thin rounded thumbs via scrollbar-width + ::-webkit-scrollbar; .no-scrollbar/.scroll-thin utilities",
            },
            {
                "name": "Consistent nav icons",
                "detail": "Categories=FolderTree and Audit=Filter in nav.ts match the nav-icons registry",
            },
            {
                "name": "Icon typo guard",
                "detail": "iconFor warns in dev on unknown names instead of silently falling back",
            },
            {
                "name": "Account Watchlist tab",
                "detail": "Starred-product count badge, export JSON, watched-only guidance",
            },
            {
                "name": "Account Sessions tab",
                "detail": "Active-device table with current-device badge from /account/sessions",
            },
            {
                "name": "Account Shortcuts tab",
                "detail": "Keyboard-first reference: palette, Esc, sortable headers, silent reload policy",
            },
            {
                "name": "Team & weights documented",
                "detail": "CONTRIBUTORS.md + docs/00_team.md with 6 members, roles and 28/15/14/14/15/14 split",
            },
            {
                "name": "Open Library subjects feed",
                "detail": "Switched from robots-blocked /search.json to allowed /subjects/<subject>.json — live records again",
            },
            {
                "name": "Dead-host removal",
                "detail": "fakestore_products unreachable, removed from DAG/seed defaults; isolation covers future outages",
            },
            {
                "name": "Real-only auto-select",
                "detail": "Bare run-pipeline excludes local_demo; synthetic rows only load when explicitly requested",
            },
            {
                "name": "One-command real verification",
                "detail": "run-full-app.sh: lint, tests, live smoke, real pipeline, frontend, compose — FULL APP TEST: PASS",
            },
            {
                "name": "Single entrypoint for everything",
                "detail": "./run.sh verifies with real data then launches the stack; verify-only/offline/quick/stop/clean/status flags",
            },
            {
                "name": "TVMaze shows source",
                "detail": "250-show pages: genres, network, posters, /10 ratings rescaled — live verified",
            },
            {
                "name": "Internet Archive texts source",
                "detail": "Public-domain texts via the robots-allowed advancedsearch feed — live verified",
            },
            {
                "name": "DummyJSON recipes source",
                "detail": "Grocery depth: ratings, review counts, tags, meal types — live verified",
            },
            {
                "name": "Scrapy crawling engine",
                "detail": "BookSpider with robots middleware, autothrottle and item cap; --engine scrapy on preview",
            },
            {
                "name": "Conditional GET revalidation",
                "detail": "ETag/Last-Modified validators, 304 serves cache with zero bytes, audited as revalidated",
            },
        ],
    },
    {
        "key": "intelligence",
        "title": "v1.11.0: Morning Briefing & Intelligence Layer",
        "icon": "sunrise",
        "summary": "A ranked, explainable action queue that composes every analytical service into one screen — no metric is reinvented.",
        "features": [
            {
                "name": "Morning briefing screen",
                "detail": "A dedicated /briefing route with a hero summary, KPI tiles and a prioritized action queue",
            },
            {
                "name": "Briefing REST endpoint",
                "detail": "GET /intelligence/briefing returns headline metrics, opportunities, risks, categories and freshness",
            },
            {
                "name": "Configurable analysis window",
                "detail": "7, 30, 90 and 180-day windows with the choice persisted to the account",
            },
            {
                "name": "Severity-ranked action queue",
                "detail": "Every insight is ordered by severity, then by the absolute size of the move, so the first row is the first action",
            },
            {
                "name": "Deep-linked insights",
                "detail": "Every card opens the exact product, change feed, catalog, quality or source screen where it can be resolved",
            },
            {
                "name": "Opportunity detection",
                "detail": "Price drops, catalog price gaps and discounted listings are merged into one opportunity lane",
            },
            {
                "name": "Risk detection",
                "detail": "Price rises, stockout pressure, statistical anomalies, DQ failures and stale sources are merged into one risk lane",
            },
            {
                "name": "Category signal radar",
                "detail": "Categories ranked by average absolute move with increase/decrease counts for the selected window",
            },
            {
                "name": "Data freshness pulse",
                "detail": "Healthy vs stale source counts and the percentage of unseen products per source",
            },
            {
                "name": "Best value picks",
                "detail": "Highly rated, sufficiently reviewed listings ranked by rating per dollar, with invalid ratings excluded",
            },
            {
                "name": "Briefing export",
                "detail": "Download the entire briefing as date-stamped JSON for stand-ups and offline review",
            },
            {
                "name": "Copy action summary",
                "detail": "One click copies a numbered stand-up summary to the clipboard",
            },
            {
                "name": "Briefing result cache",
                "detail": "A short-lived server-side cache keeps repeat visits instant while staying fresh enough for demos",
            },
            {
                "name": "Anomaly noise filter",
                "detail": "Extreme >65% moves and unit-mismatch catalog gaps are excluded from the human action queue",
            },
            {
                "name": "Duplicate insight suppression",
                "detail": "Repeated product and catalog snapshots collapse to a single actionable card",
            },
            {
                "name": "Sub-dollar price formatting",
                "detail": "Crypto and micro-priced listings render with 4-8 decimal precision instead of rounding to $0.00",
            },
            {
                "name": "Account briefing defaults",
                "detail": "Default window and queue size can be set once and follow the user to every device",
            },
            {
                "name": "Route preloading",
                "detail": "The briefing chunk is prefetched during idle time, so navigation stays silent with no spinner",
            },
            {
                "name": "Read-only access control",
                "detail": "The briefing requires an authenticated read user and never exposes mutation capabilities",
            },
            {
                "name": "Briefing test contract",
                "detail": "Integration tests cover authentication, window validation, bounded sections, deep links and severity values",
            },
        ],
    },
    {
        "key": "demo_scale",
        "title": "v1.11.0: 10x Demo Warehouse",
        "icon": "database-zap",
        "summary": "A deterministic, idempotent expansion that takes the demo from thousands to 25k products and 550k+ observations.",
        "features": [
            {
                "name": "25k product demo cohort",
                "detail": "19,500 additional synthetic products under the reserved SYN- namespace, appended without touching existing rows",
            },
            {
                "name": "550k+ price observations",
                "detail": "26 days of history per synthetic product produces a fact table large enough to exercise every chart",
            },
            {
                "name": "Realistic price walks",
                "detail": "Drift, promo cycles and rare clearance shocks instead of independent random prices",
            },
            {
                "name": "Full lifecycle history",
                "detail": "First sightings, delistings, availability changes and significant price-change records are generated together",
            },
            {
                "name": "Catalog reconciliation at scale",
                "detail": "13k internal catalog SKUs and latest-run match snapshots, including price mismatches and discontinued items",
            },
            {
                "name": "Seeded quality defects",
                "detail": "Out-of-range ratings, missing prices and unknown availability keep the DQ framework meaningful",
            },
            {
                "name": "Category rollups rebuilt",
                "detail": "agg_category_daily is recomputed from facts for the generated window, so dashboard totals always agree",
            },
            {
                "name": "Idempotent expand-demo CLI",
                "detail": "The command detects an existing cohort and skips the expensive work on reruns",
            },
        ],
    },
    {
        "key": "v111_polish",
        "title": "v1.11.0: Mobile, Theme & Zero-Friction UI",
        "icon": "panels-top-left",
        "summary": "Responsive layout, instant navigation and a complete theme system that never flashes or animates routes.",
        "features": [
            {"name": "Fixed desktop sidebar", "detail": "Persistent navigation with a collapse-to-rail mode and remembered state"},
            {"name": "Mobile drawer navigation", "detail": "Full-height drawer with backdrop dismissal and safe-area-aware sizing"},
            {"name": "Mobile bottom tab bar", "detail": "Five primary destinations plus a More sheet on small screens"},
            {"name": "Global scrollbar hiding", "detail": "Clean chrome on every scroll container while wheel, touch and keyboard scrolling remain intact"},
            {"name": "Silent route preloading", "detail": "Lazy chunks are fetched during idle time so navigation shows content, not spinners"},
            {"name": "120ms motion policy", "detail": "One global transition budget for hovers and state changes; no page transitions or smooth scroll"},
            {"name": "Motion none mode", "detail": "A persisted preference removes decorative animation and functional spinners render statically"},
            {"name": "Five theme palettes", "detail": "Light, dark, midnight, high-contrast and system-following modes"},
            {"name": "Ten accent presets", "detail": "Brand colour tokens update charts, links, focus rings and badges together"},
            {"name": "Three density presets", "detail": "Comfortable, compact and ultra-compact spacing for tables and cards"},
            {"name": "Four text-size presets", "detail": "Font scaling independent of density for accessibility and large displays"},
            {"name": "RTL layout support", "detail": "CSS logical properties mirror the entire interface without a second stylesheet"},
            {"name": "Visible focus rings", "detail": "Every interactive element exposes a consistent keyboard focus indicator"},
            {"name": "Skip-to-content link", "detail": "Keyboard users jump straight past the navigation shell"},
            {"name": "Responsive KPI grids", "detail": "Two columns on phones, three on tablets and six on wide dashboards"},
            {"name": "Compact mobile stat tiles", "detail": "Smaller typography and padding keep six KPIs readable in a phone viewport"},
            {"name": "Command palette", "detail": "Search every screen and action from the header with Ctrl/Cmd-K"},
            {"name": "Keyboard shortcut sheet", "detail": "Documented shortcuts for navigation, dialogs and the command palette"},
            {"name": "Toast notifications", "detail": "Non-blocking success and error feedback with consistent placement"},
            {"name": "Route-level code splitting", "detail": "Each screen ships its own chunk so the initial dashboard load stays light"},
            {"name": "Pre-paint theme application", "detail": "Theme, accent, density and direction apply before first paint, eliminating flashes"},
        ],
    },
    {
        "key": "team",
        "title": "Team catalogue as code",
        "icon": "users",
        "summary": "Members, roles, weights and function ownership served live — the credit surface cannot drift.",
        "features": [
            {
                "name": "Team module",
                "detail": "TEAM list with 6 members, roles, weights (sum 100) and function inventories",
            },
            {
                "name": "Team API endpoint",
                "detail": "GET /meta/team serves lead, weights and function ownership",
            },
        ],
    },
    {
        "key": "v110_compliance_builders",
        "title": "v1.10.0: Live Compliance Posture, Builder Presets, SQL Compiler & Zero-Flicker SPA",
        "icon": "shield-check",
        "summary": "Live multi-worker robots.txt auditing, 1-click compliance verification, visual SQL query compilation, builder quick-presets, and zero-flicker background refreshing.",
        "features": [
            {
                "name": "Live robots.txt audit endpoint",
                "detail": "POST /api/v1/sources/audit-compliance audits all 35+ registered public sources and writes durable verdicts to ingestion_http_log",
            },
            {
                "name": "Cross-worker compliance aggregation",
                "detail": "Blends in-memory RobotsCache with warehouse ingestion_http_log totals across multi-worker uvicorn and background Airflow processes",
            },
            {
                "name": "One-click UI compliance verification",
                "detail": "Interactive Audit live robots.txt button directly inside the compliance posture card with loading spinners and immediate cache invalidation",
            },
            {
                "name": "Empty-state compliance self-healing",
                "detail": "Interactive inline trigger allows one-click recovery and live robots audit when starting from a blank database",
            },
            {
                "name": "View Builder Quick-Presets",
                "detail": "Instant pre-configured filters for Flash Drops (>=15%), Out of Stock Alerts, Luxury Tier ($100+), Top Movers, and New Arrivals (7d)",
            },
            {
                "name": "Aggregate Builder Quick-Presets",
                "detail": "Pre-computed metrics for Category Distribution, Average Price by Tier, and In-Stock Ratios",
            },
            {
                "name": "Visual Parameterized SQL Compiler",
                "detail": "One-click Copy SQL button compiles UI builder filters into syntactically valid, parameterized SQL queries with clean indentation",
            },
            {
                "name": "Live Preview Statistics",
                "detail": "Instant record count and aggregation stats preview right above builder tabular outputs",
            },
            {
                "name": "Zero-Flicker Data Updates",
                "detail": "Queries keep the previous page visible while refetching, so live data updates never flash a skeleton or shift layout",
            },
            {
                "name": "Live Pipeline WebSocket",
                "detail": "Authenticated /stream/events pushes warehouse counters and job progress to the dashboard",
            },
            {
                "name": "Preference Backup & Restore",
                "detail": "Export appearance, page size and start-page preferences as JSON and restore them through an allowlist-validated import",
            },
            {
                "name": "Copy Buttons on Code Blocks",
                "detail": "API tokens, SQL previews and query results have copy-to-clipboard buttons with checkmark confirmations",
            },
            {
                "name": "Zero-Rebuild Docker Volume Mounting",
                "detail": "Live mount of ./frontend/dist directly into pip-frontend container for instantaneous production updates",
            },
            {
                "name": "Modern Theme-Aware Custom Scrollbars",
                "detail": "Thin, rounded, non-intrusive scrollbars adapting smoothly between Light, Dark, Midnight, and High-Contrast modes",
            },
            {
                "name": "Universal Responsive Touch Navigation",
                "detail": "Off-canvas mobile slide-out drawer combined with fixed desktop sidebar for optimal responsive ergonomics",
            },
            {
                "name": "SQLite Fallback Isolation",
                "detail": "Automatic fallback and schema initialization for standalone verification scripts without PostgreSQL dependency",
            },
            {
                "name": "PostgreSQL Analytical Warehouse Guard",
                "detail": "Automatic dialect detection and validation ensuring production ETL targets real PostgreSQL schemas",
            },
            {
                "name": "MySQL Secondary Dialect Cross-Verification",
                "detail": "Continuous validation of secondary MySQL storage target ensuring dialect-agnostic ETL logic",
            },
            {
                "name": "Real-Only Production Ingestion",
                "detail": "Default pipeline runs strictly filter out synthetic local_demo test fixtures, guaranteeing 100% authentic public data",
            },
            {
                "name": "DEPI Data Engineering Branding",
                "detail": "Dedicated 16:9 infographic slides and executive project documentation aligned with DEPI Data Engineering capstone standards",
            },
            {
                "name": "Durable HTTP Audit Log Counters",
                "detail": "Accurate metrics for fetched, cached, allowed, blocked, and error calls computed directly via ANSI standard SQL",
            },
            {
                "name": "Pre-warmed robots.txt Cache",
                "detail": "Process-wide thread-safe memory cache with 30-minute RFC-compliant TTL reducing external network load",
            },
            {
                "name": "Dynamic Source Onboarding Validation",
                "detail": "SSRF-guarded URL checking with live shape sniffing before registering any user-defined JSON adapter",
            },
            {
                "name": "Builder Schema Autocomplete",
                "detail": "Dynamic column and operator introspection powering frontend filter suggestion dropdowns",
            },
            {
                "name": "Multi-Theme Contrast Compliance",
                "detail": "WCAG AA compliant contrast ratios across all 4 visual themes: Light, Dark, Midnight, and High-Contrast",
            },
        ],
    },
    {
        "key": "enterprise_warehouse_platform",
        "title": "Enterprise Warehouse & Analytical Core",
        "icon": "database",
        "summary": "Deep analytical warehouse architecture: star schema dimensions, facts, change capture, Airflow DAGs, and high-throughput ingestion.",
        "features": [
            {
                "name": "Star Schema Architecture",
                "detail": "DimProduct, DimSource, DimDate, DimCurrency dimensions joined with FactPriceSnapshot fact tables",
            },
            {
                "name": "SCD Type 2 Dimension Tracking",
                "detail": "Historical dimension tracking preserving category migrations, title revisions, and attribute updates over time",
            },
            {
                "name": "Change Data Capture (CDC)",
                "detail": "Dedicated ChgPriceChange, ChgNewProduct, ChgRemovedProduct tables tracking daily market fluctuations",
            },
            {
                "name": "Airflow DAG Orchestration",
                "detail": "Production Airflow DAG product_intelligence_pipeline with task retries, alert fan-out, and SLA monitoring",
            },
            {
                "name": "Automated Quality Gatekeeper",
                "detail": "12 executable DQ rules running after every ingestion batch with automatic failure quarantine",
            },
            {
                "name": "Currency FX Normalization",
                "detail": "Live and offline foreign exchange conversion standardizing GBP, EUR, and regional currencies into base USD",
            },
            {
                "name": "Deduplication & Entity Resolution",
                "detail": "Exact hash matching combined with fuzzy Levenshtein distance resolving cross-source duplicate listings",
            },
            {
                "name": "Interactive SQL Query Lab",
                "detail": "Browser-based analytical SQL console with syntax highlighting, schema tree, execution timing, and CSV export",
            },
            {
                "name": "Server-Side PDF Reporting",
                "detail": "Headless PDF generation compiling executive summaries, data quality reports, and price movement analyses",
            },
            {
                "name": "Time-Series Forecasting Engine",
                "detail": "Statistical Holt-Winters exponential smoothing forecasting future price trends up to 60 days ahead",
            },
            {
                "name": "Real-Time Streaming SSE",
                "detail": "Server-Sent Events streaming live pipeline execution logs and progress bars directly to the browser",
            },
            {
                "name": "HMAC Webhook Subscriptions",
                "detail": "Event-driven webhook engine delivering signed JSON payloads on price drops, DQ breaches, and pipeline completion",
            },
            {
                "name": "RBAC Security Matrix",
                "detail": "Role-based access control with Admin, Analyst, and Viewer tiers governing granular data manipulation permissions",
            },
            {
                "name": "Two-Factor TOTP Authentication",
                "detail": "RFC 6238 compliant TOTP enrollment with QR code generation, recovery codes, and session invalidation",
            },
            {
                "name": "Sliding-Window Rate Limiting",
                "detail": "Defensive API rate limiting preventing denial-of-service and enforcing fair usage across endpoints",
            },
            {
                "name": "Automated Staging Landing Zone",
                "detail": "Raw JSON payloads preserved in StgRawObservation before transformation, ensuring 100% data auditability",
            },
            {
                "name": "Pre-aggregated Analytical Views",
                "detail": "20+ materialized and SQL views optimizing common reporting queries for sub-second dashboard rendering",
            },
            {
                "name": "Comprehensive Typer CLI",
                "detail": "17 CLI commands covering pipeline runs, warehouse seeding, data quality audits, and dialect verification",
            },
            {
                "name": "Docker Compose Multi-Container Stack",
                "detail": "Fully orchestratable stack running PostgreSQL, MySQL, Airflow Webserver, Airflow Scheduler, API, and Frontend",
            },
            {
                "name": "Cross-Dialect Migration Framework",
                "detail": "Alembic migrations verified against both PostgreSQL 16 and MySQL 8.4 analytical targets",
            },
            {
                "name": "Automated Anomaly Detection",
                "detail": "Z-score and interquartile range (IQR) outlier detection flagging sudden flash price spikes or collapses",
            },
            {
                "name": "Catalog Price Gap Analysis",
                "detail": "Identifies internal products priced above or below market average with actionable margin recommendations",
            },
            {
                "name": "Automated Ingestion Politeness",
                "detail": "Strict enforcement of crawl-delay directives and per-source rate limits preventing target site saturation",
            },
            {
                "name": "Custom View Builder",
                "detail": "Visual drag-and-drop query constructor allowing non-technical analysts to assemble custom warehouse filters",
            },
            {
                "name": "Executive KPI Dashboard",
                "detail": "At-a-glance visualization of product counts, observation volume, daily price change velocity, and pipeline uptime",
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


def feature_groups() -> list[tuple[str, str]]:
    """``(key, title)`` pairs, used to build the features screen's filter chips."""
    return [(group["key"], group["title"]) for group in FEATURE_GROUPS]


__all__ = ["FEATURE_GROUPS", "feature_catalogue", "feature_groups", "feature_names"]
