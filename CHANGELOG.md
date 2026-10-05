# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [1.3.0] - 2026-10-05

### Added

- **Aggregate Query Builder** — a server-side aggregate analysis endpoint plus a dedicated
  dashboard screen: group any dataset by one or more dimensions, apply measures and aggregate
  functions, add advanced filters, sort, and read the live result as a table or a chart, with a
  generated SQL preview and CSV/JSON export.
- **Aggregate DSL** on the API — whitelisted operators, functions and directions validated before
  any SQL is composed, so the builder cannot emit anything the read-only guard would reject.
- Mobile navigation and scrolling polish: the off-canvas drawer now locks background scroll, is
  announced as a modal dialog with an accessible name, respects the safe-area inset, and the
  document reserves a scrollbar gutter so content never jumps sideways as a page grows.
- `SECURITY.md` with the threat model, the boundary-by-boundary control table, and disclosure
  instructions.
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).
- GitHub issue forms for bugs, features and documentation, plus a pull request template.
- `dependabot.yml` for weekly checks of pip, npm and GitHub Actions.

### Changed

- `docs/` and `README.md` figures re-measured against the current code base and corrected: 255
  unit tests (was 236), 61 files clean under mypy (was 59), 113 REST operations in 16 routers
  (was 104 in 15), and 20 dashboard screens (was 17).

### Fixed

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
- Diagram extractor: `scripts/render_diagrams.sh` pulls all 51 Mermaid diagrams out of the
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