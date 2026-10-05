# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [1.4.0] - 2026-10-05

### Added

- **Run comparison** — `GET /api/v1/pipeline/runs/compare?base=&target=` diffs any two pipeline runs:
  12 metric deltas with absolute and percentage change, DQ rules that regressed or were fixed,
  products added and dropped, the largest price moves, and the runtime delta. A zero baseline reports a
  null percentage instead of dividing by zero. Exposed as a **Compare** tab on the Runs screen.
- **Universal dataset export** — a dataset registry (`app/services/exporter.py`) backs
  `GET /api/v1/export/{dataset}.csv|.json` for 12 datasets: products, price changes, new products,
  removed products, runs, quality results, catalog reconciliation, categories, top movers, sources,
  alerts, audit log and HTTP compliance log. Filters are declared per dataset and always bound as query
  parameters, identifiers are validated against a strict pattern, row counts are capped in SQL
  (50,000) and `GET /export/{dataset}` returns a JSON preview. Downloads use the server-generated,
  date-stamped filename, and the dashboard gains CSV/JSON buttons on the data screens.
- **Outbound webhooks** — per-user event subscriptions (`POST/GET/PATCH/DELETE /api/v1/webhooks`) with
  HMAC-SHA256 signed payloads (`X-Webhook-Signature` over `timestamp.body`, so replays are detectable),
  ten pipeline events (`run.completed`, `run.failed`, `run.started`, `dq.failed`, `price.spike`,
  `product.new`, `product.removed`, `catalog.mismatch`, `alert.triggered`, `backfill.completed`),
  exponential-backoff retries (30s, 5m, 30m), a per-attempt delivery log, secret rotation, and automatic
  disabling after repeated failures. Targets are validated before any request is made, so loopback,
  private, link-local and cloud-metadata addresses are refused — a webhook can never be pointed at the
  warehouse host. A failing webhook can never fail a pipeline run. New **Webhooks** screen with
  one-time secret reveal, test delivery and the delivery log.
- **Historical backfill** — `POST /api/v1/pipeline/backfill` replays any date range (up to 31 days per
  job) with one run per day, every run tagged with the job id. Days are isolated, so a single failing
  source records its error and the job continues. `GET /api/v1/pipeline/backfills` and
  `GET /api/v1/pipeline/backfill/{id}` report roll-up progress, per-day results and aggregate DQ.
- **Expanded feature catalogue** — now 118 features in 15 groups, including new *Integrations* and
  *Run comparison & observability* groups, surfaced by `GET /api/v1/meta/features` and the Features screen.

### Documentation

- **Three new reference documents** bring the set from twenty to twenty-three:
  - [docs/21_architecture_deep_dive.md](docs/21_architecture_deep_dive.md) — the design drivers, and
    for each significant decision what was chosen, what was *rejected*, why, and the measured
    consequence; the full request lifecycle; warehouse layering; and a stated list of known
    limitations rather than an implied absence of them.
  - [docs/22_data_dictionary.md](docs/22_data_dictionary.md) — every table with every column, type,
    nullability and meaning, the controlled vocabularies and magnitude bands, the view catalogue, and
    the dialect-portability rules the schema obeys to load on both engines.
  - [docs/23_glossary_and_faq.md](docs/23_glossary_and_faq.md) — the vocabulary defined, then the
    questions that actually come up across setup, the pipeline, data quality, security and
    development, including a six-step recipe for adding a source.
- **A documentation website**, built by `scripts/build_site.py` using only the standard library:
  one page per document, client-side search over a generated index, a dark mode that follows the
  system preference, and all diagrams rendered. It is dependency-free by design — GitHub Pages does
  not serve private repositories on the free plan, so a Pages workflow could never deploy here, while
  a static directory works anywhere. Build with `make site`, preview with `make site-serve`.
- **`SECURITY.md`** — a threat model with a control table for each trust boundary (web to ingestion,
  user to API, API to warehouse), what is implemented today, and how to verify each claim yourself.
- **`.github/CODE_OF_CONDUCT.md`** — Contributor Covenant 2.1 with a four-tier enforcement ladder.
- **Issue and pull request templates** — bug, feature and documentation forms plus a PR template
  carrying the reminders that actually matter here: keep robots enforcement in the transport layer,
  keep SQL parameterised, and prove cross-dialect parity.
- **`.github/dependabot.yml`** for pip, npm and GitHub Actions, and **`.github/CODEOWNERS`**.

### Tooling

Counts quoted in documentation used to be maintained by hand, which is how they drift. They are now
measured from the code:

- **`scripts/project_stats.py`** measures every structural figure — tables, views, routers, route
  decorators, DQ rules, sources, tasks, stages, documents, diagrams, features, tests, smoke checks —
  straight from the source tree, SQLAlchemy metadata and pytest collection.
- **`scripts/check_stats.py`** compares those measurements against a committed snapshot
  (`docs/stats.json`) and fails CI on any difference, printing exactly which figure moved and in which
  direction.
- **The README statistics block is generated** between `<!-- BEGIN:STATS -->` markers and verified in
  CI, so it can never silently disagree with the code. The sync is idempotent: running it twice
  changes nothing.

### Fixed

- Two Mermaid diagrams genuinely failed to parse and were caught by the new diagram gate: a
  semicolon inside a `sequenceDiagram` message, and an edge in `docs/22_data_dictionary.md` that
  gave a node the same identifier as another node, producing a self-parenting cycle.
- Three broken in-page anchors in `docs/19_feature_list.md`, where a hand-written table of contents
  and its section headings had drifted apart on feature counts, plus six section headings whose
  stated totals did not match the rows beneath them.
- `slugify` now reproduces GitHub's `github-slugger` exactly. The previous approximation collapsed
  the double hyphen an em-dash leaves behind, so every such in-document link was broken in the built
  site while still working on GitHub. Verified against the reference implementation across 24 cases,
  including multiple spaces, underscores, leading and trailing hyphens, and non-ASCII headings, and
  pinned by `scripts/check_slugify.py`.
- Test-suite robustness: the table-count assertion now derives from the ORM instead of a hard-coded
  number, and the audit-isolation test compares identities rather than totals, which had made it
  order-dependent and therefore flaky.

### Notes

- `tsc --noEmit` at the repository root is a no-op because `tsconfig.json` uses project references;
  use `npm run typecheck` (`tsc --noEmit -p tsconfig.app.json`), `npm run build:strict` (`tsc -b`) or
  `npx tsc -b --noEmit` to type-check the dashboard.

## [1.3.0] - 2026-10-05

### Added

- **Feature catalogue API + screen** — `GET /api/v1/meta/features` serves a structured catalogue
  (13 areas, 95 shipped features, each with a Lucide icon name) from the new single source of truth
  `app/core/features.py`. The new `/features` dashboard screen renders it as searchable, filterable
  cards; `GET /meta` now derives its `features` list and `feature_groups` count from the same module,
  so the UI, the API and the documentation can never drift apart.
- **Aggregate Query Builder** — `POST /api/v1/builder/query` and `GET /api/v1/builder/schema` expose a
  structured, read-only query surface over 11 analytical entities: group by any whitelisted column,
  apply six aggregate functions (`count`, `count_distinct`, `sum`, `avg`, `min`, `max`), filter with
  fifteen operators (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `not_contains`, `starts_with`,
  `ends_with`, `in`, `not_in`, `between`, `empty`, `not_empty`), sort by group columns or aggregate
  aliases, and receive rows, totals, duration and a generated SQL preview. Every identifier comes from
  a server-side whitelist and every value is a bind parameter, so injection is structurally impossible.
  The Builder screen gains a "Group & aggregate" mode with measure rows, advanced filters, a live bar
  chart, cURL copy and CSV/JSON export.
- **Account self-service** — `GET /api/v1/users/me/export` returns a portable JSON snapshot (profile,
  API-key metadata, saved views, alert rules, notifications, recent activity), and
  `DELETE /api/v1/users/me` deletes the account after password confirmation (personal rows cascade,
  audit history is preserved). The Account screen gains **Activity** and **Data & privacy** tabs.
- **Personal activity feed** — `GET /api/v1/audit/me` returns the caller's own audited actions, so users
  can review what they did without needing the admin-only audit screen.
- **Aggregate DSL validation** on the API — unknown operators, columns, entities, sorts and malformed
  `in`/`between` arguments are rejected before any SQL is composed.
- 19 new automated tests (`tests/test_new_features.py`) and 8 new end-to-end API smoke checks covering
  the catalogue, builder, export, activity and role boundaries.
- Mobile navigation and scrolling polish: the off-canvas drawer now locks background scroll, is
  announced as a modal dialog with an accessible name, respects the safe-area inset, and the document
  reserves a scrollbar gutter so content never jumps sideways as a page grows.
- Modern scrollbars across the app: translucent rounded thumbs, a brand-coloured thumb while
  dragging, slimmer 8px rails inside the sidebar/popovers/code blocks, and `overscroll-behavior:
  contain` so scrolling a panel or table never drags the page behind it.
- `SECURITY.md` with the threat model, the boundary-by-boundary control table, and disclosure
  instructions.
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).
- GitHub issue forms for bugs, features and documentation, plus a pull request template.
- `dependabot.yml` for weekly checks of pip, npm and GitHub Actions.
- A premium single-file project website (`website/index.html`) with light/dark/system themes.

### Changed

- `docs/` and `README.md` figures re-measured against the current code base and corrected: 255
  unit tests (was 236), 61 files clean under mypy (was 59), 113 REST route decorators — 110
  documented in OpenAPI plus 3 internal probes — across 16 routers (was 104 in 15), and 21 dashboard
  screens (was 17).
- Airflow DAG: `build_aggregates` and `reconcile_catalog` again perform real work in-process instead of
  only reporting, `publish_report` persists a JSON KPI artifact under `var/reports/`, and the source
  compliance guard once again honours per-source `enabled`/`terms_allowed` flags.

### Fixed

- **Secret leak**: a live service API key was committed in `.env.example`; it is now a placeholder and
  `.env.example` documents how to mint a key.
- **Docker healthcheck**: the API container probed `/health`, which is served under `/api/v1/health`,
  so `docker compose` permanently reported the service as *unhealthy* even while it served traffic.
- Removed a duplicate `_notify_local` definition in the Airflow DAG (the second copy silently shadowed
  the first).
- Removed an unused context lookup in the Airflow DAG that failed the ruff check.
- Consistent Python formatting applied across the backend.

### Verified

```text
ruff: all checks pass            mypy: no issues in 61 source files
pytest: 255 passed               API smoke: 78/78 checks
frontend: eslint clean, tsc clean, production build ok
```

## [1.2.0] - 2026-10-04

### Added

- Account controls: avatar colour picker (twelve swatches, applied app-wide), "start page after
  sign-in" preference with login redirect and session-restore support, and an account-level
  "reduce motion" override applied before the first paint.
- Builder upgrades: visible-column reordering (move earlier/later buttons), "copy as API request"
  (ready-to-run REST URL for the composed query), and CSV/JSON export of the live preview.
- DEPI project infographic generator: `make infographic` produces the 16:9 roadmap slide as an
  SVG master plus an HTML preview and a PNG raster when cairosvg is available
  (`docs/assets/infographic.*`).
- Diagram extractor: `scripts/render_diagrams.sh` (superseded by `scripts/diagrams.py` in 1.3.0)
  pulled all 51 Mermaid diagrams out of the
  documentation into `docs/diagrams/out/*.mmd` with an index table, ready for `mmdc` rendering.
- Feature inventory section 15: eight new entries (F-227 to F-234), revised total 234.

### Changed

- `UserRead` now exposes the server-side `preferences` JSON so account choices survive new devices.

### Verified

```text
ruff: all checks pass            mypy: no issues in 59 source files
pytest: 236 passed               API smoke: 78/78 checks
frontend: eslint clean, tsc clean, production build ok
infographic: SVG valid (2560x1440) + PNG rendered (2560x1440)
```

## [1.1.0] - 2026-10-04

### Added

- Command palette in the dashboard (`Ctrl/Cmd-K` or `/`): unified search over screens, actions and
  **live product results** with prices; full keyboard navigation (up, down, enter, escape).
- JSON exports on Dashboard, Products, Analytics and Changes alongside the existing CSV exports,
  plus a shared RFC-4180 CSV serialiser for all tabular exports.
- Installable PWA: web app manifest, maskable SVG icon, Apple touch icon and safe-area viewport
  configuration; the dashboard can now be installed on desktop, Android and iOS.
- GitHub Actions CI with two jobs (backend: ruff, mypy, pytest; frontend: eslint, tsc, vite build)
  and an uploaded build artifact.
- API integration test suite (`tests/test_api.py`): 39 checks covering auth, RBAC, the read-only
  query guard, CSV export media type, saved views, alerts, notifications and audit behaviour.
- MIT `LICENSE` file and `CHANGELOG.md`.

### Changed

- The products CSV export endpoint now returns `text/csv` with a `Content-Disposition` attachment
  header instead of a JSON-wrapped string.
- README rewritten into a full project gateway: system overview, pipeline phase anatomy, ERD,
  sequence and deployment diagrams, configuration reference, FAQ and troubleshooting.
- Feature inventory extended to 226 entries with a new dashboard-v1.1 section.
- Docs index updated to cross-reference the new files.

### Fixed

- Strict TypeScript errors in the analytics radar chart props, availability badges and the view
  builder table column types; four lingering ESLint warnings eliminated (`--max-warnings 0`).
- Python lint and type findings across ingestion, dedupe, catalog reconciliation, seed, CLI,
  analytics service and several routers; ruff and mypy now pass with zero findings.
- Deterministic warehouse test lifecycle: the integration suite recreates and seeds the SQLite test
  warehouse on every session start, making runs reproducible (236/236 green).

### Verified in this release

```text
ruff: all checks pass        mypy: no issues in 59 source files
pytest: 236 passed           API smoke: 78/78 checks
frontend: eslint clean (0 warnings), tsc clean, production build ok
cross-dialect: identical model and DQ score (98.26) on PostgreSQL 16 and MySQL 8.4
```

## [1.0.0] - 2026-10-03

### Added

- Five compliant ingestion sources (DummyJSON, FakeStore, Open Library, books.toscrape.com HTML
  scraper, offline synthetic) with robots.txt enforcement, rate limiting, circuit breaker,
  response cache and an HTTP evidence log.
- 29-step cleaning and normalisation engine for product names, categories, prices, currencies,
  ratings and availability.
- Fuzzy duplicate detection with four similarity signals and block-indexed candidate pools.
- Kimball-star warehouse, 23 tables and 20 analytical views, loaded idempotently on both
  PostgreSQL 16 and MySQL 8.4.
- Nine-stage ETL pipeline with stage timings, counters, change detection (price / new / removed /
  category) and internal catalog reconciliation with price-gap analysis.
- Twelve-rule data-quality framework across six dimensions with persisted verdicts per run.
- FastAPI REST API: 104 operations in 15 routers with JWT + API-key auth, RBAC, OpenAPI and ReDoc.
- React 19 analytics dashboard with 17 screens, light/dark themes, saved views, alert rules and
  audit screens.
- Apache Airflow DAG with 13 tasks and a synchronisation-run API endpoint for demonstrations.
- Typer CLI (12 commands), Makefile (30+ targets), six-service Docker Compose stack and a
  78-check API smoke suite.
- Twenty-numbered project documentation set (proposal, plan, design, diagrams, manuals) with
  Mermaid diagrams throughout.