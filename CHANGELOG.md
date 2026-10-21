# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.12.1] - 2026-10-21

The theme of this release: **nothing in the product is a stub any more.** Three
analytical surfaces were structurally empty, two test families passed on an
empty list, and a live exchange rate could fail the whole suite.

### Fixed — analytics that could never return a row

Three analytical surfaces were structurally empty on any real warehouse. They
rendered a panel, returned `[]`, and looked like "no findings" rather than
"broken".

- **The portable variance was inverted.** The expression was
  `(E[x])² - E[x²]` — the *negative* of the variance — so every category's
  standard deviation clamped to zero. With the deviation pinned at zero, the
  z-score denominator was zero, so the anomaly detector could never fire and
  the category price index and price volatility views published a deviation of
  exactly `0.0000` for all 1,599 categories and 8,774 category-days. The
  variance is `E[x²] - (E[x])²`. Fixed in `app/analytics/service.py`,
  `db/views.sql` (both views) and the query-lab example.
- **Vote counts were discarded before they reached the warehouse.** The rating
  count is delivered as a dedicated field (`rating_count_text`), and every API
  adapter fills it with a bare integer (`"4523"`). The parser only matched a
  count written with a unit word (`"4523 reviews"`), so the count was silently
  dropped for every source that reports one. A dedicated count field is now
  read as an integer, with the unit-word pattern kept for counts scraped out of
  free text.
- **"Best value" excluded every candidate.** The ranking required
  `rating_count >= 10`, but no upstream publishes a vote count for the
  majority of the catalogue, so the panel was empty by construction. A listing
  whose vote count is unknown is no longer disqualified - it simply cannot be
  proven popular, so it ranks on rating and loses to an equally rated listing
  with a known, larger vote count.

### Fixed — tests that passed on nothing

- **The anomaly ranking test passed on an empty list.** `assert scores ==
  sorted(scores, reverse=True)` is true of `[]`, so the detector could be
  completely disabled and the test stayed green. The regression now asserts
  that the deviation itself is non-zero.
- **The cross-source overlap tests passed on an empty list too.** The seeded
  corpus samples each source independently, so no two sources share a product
  and the overlap panels are legitimately empty. A new test injects a product
  listed by two sources at two different prices and requires the analytics to
  find it, so the grouping is proven rather than assumed.

### Fixed — data provenance

- **Every snapshot could claim a future timestamp.** The demo seeder anchored
  its history to the *local* calendar day, which is up to a full timezone
  offset ahead of UTC, so the newest snapshot could be hours in the future.
  The anchor is now UTC and the newest day is clamped to the current instant.
- **The freshness rule could report a negative age.** Under the same clock
  skew, a future-dated snapshot produced a negative number of hours. It is
  now treated as zero hours old.
- **The `dq_failure` alert read the wrong run.** It took the most recent run
  whether or not that run carried a data-quality verdict, so an unscored run
  silently masked the previous verdict. It now reads the most recent *scored*
  run.
- **Report tiles read the wrong keys.** Four of the six headline tiles in the
  generated report read `avg_price`, `dq_score`, `chg_price_change` and
  `new_products` from the top level of the KPI payload, where they live under
  `latest`, `quality`, `changes` and `events`. The tiles were empty.

### Fixed — performance and scaling

- **No index on the timestamps every windowed query filters on.** The dashboard
  filtered on `captured_at` and `detected_at`, and neither column carried an
  index, so the planner sequential-scanned the whole fact table on every load.
  Three indexes (`ix_fact_price_captured_product`, `ix_chg_event_detected`,
  `ix_chg_price_detected`) remove the scan and scale the window queries to a
  half-million-row warehouse.
- **The KPI payload counted rows in fifteen tables the dashboard never shows.**
  Counting them was 70 % of the query budget. The KPI endpoint now counts only
  what it publishes; the full set stays available on the health and pipeline
  totals endpoints. The dashboard query went from ~290 ms to ~150 ms.

### Fixed — the test suite depended on the market

- **A test asserted a live exchange rate.** `test_convert_to_usd_uses_reference_table`
  expected `1.0865`, a number that only the frozen reference table holds; the
  live provider returned `1.1217` and the failure cascaded through the rest
  of the suite. FX rates are now pinned in tests and live in production
  (`FX_LIVE_RATES`), so the suite is hermetic.

### Fixed — a source could be laundered into market data

- **The Add-source form defaulted the trust level to `real`.** The schema
  default won over the preset's own classification, so onboarding DummyJSON
  from the one-click preset wrote a source the pipeline then collected
  automatically, and the no-fake audit passed it. The trust level is now
  *resolved*, never defaulted: the preset's classification is used unless the
  operator states a different one, the form states it explicitly, and the
  classification survives an edit.
- **A `robots.txt` that answered 401/403 was treated as permission.** RFC 9309
  calls an unauthorised response a disallow-all. The code allowed the host and
  the rule string claimed an allow-list that does not exist. A 401/403 now
  disallows the whole host, and the rule strings describe the decision that
  was actually made. The policy lives in one place,
  `app/ingestion/compliance.py`, with a test that keeps the code and the
  documented guarantees in step.
- **An explicit `--sources` list bypassed the terms gate.** A source whose
  site terms forbid polling could still be named on the command line, while
  the Sources screen said it was "excluded from every run". It is now refused
  however it was selected.
- **The launcher seeded a synthetic dataset into the production warehouse.**
  `run-local.sh` loaded 120 days of generated products by default, and
  `make everything` did the same, so the dashboard served invented prices next
  to observed ones with nothing to say which was which. The synthetic dataset
  is now opt-in (`./run-local.sh --seed`, `make everything-demo`), and
  `make everything` collects from the permitted public sources only.
- **The API smoke test injected generated rows.** It triggered a pipeline run
  with `sources: ["local_demo"]` against the live warehouse. It now runs
  against a real permitted source.
- **A quality score of 100.0 was reported for a warehouse nobody checked.**
  With no rule results the API answered `score: 100.0`, which the dashboard
  rendered as a perfect green score and the data-quality report described as
  "all 12 rules passed". The score is now `null` with `evaluated: false`, the
  screen says "not evaluated yet", and the report says no evaluation has run.
- **The data-quality report's tiles were empty.** It read a nested `summary`
  object that the report payload does not have, so every tile rendered blank.

### Added

- **Source trust classification.** Every registered source declares `real`,
  `sandbox` or `synthetic`. A pipeline run without parameters only ever
  collects `real` sources; anything below must be named explicitly. The
  classification is persisted in `dim_source` and shown on the Sources screen.
- **Untrusted-row purge.** `pip-cli purge-untrusted` removes the rows a
  non-market source wrote and reports exactly what it removed, with a
  `--dry-run` mode that changes nothing. It also re-points a product whose
  first sighting came from a purged source at the trusted source it was
  really observed at.
- **A generated catalogue is identifiable and removable.** The internal
  catalogue is the *retailer's* own product list, so a seeded one is a
  placeholder rather than fabricated market data. Every seeded row now
  carries a marker, the Catalog screen says "Demo catalogue" and how many
  SKUs are placeholders, and `pip-cli purge-demo-catalog` removes them
  without touching an imported row.
- **The audit runs against MySQL.** It quoted identifiers with double quotes,
  which MySQL rejects, so the cross-dialect proof only worked on PostgreSQL.
  The no-fake audit now runs on both targets, and it reports a generated
  catalogue as a note with the command that removes it.
- **The documentation's figures are checked, not just claimed.**
  `scripts/check_stats.py` now also reads the prose in `README.md` and
  `docs/*.md` and fails on a figure that no longer matches the code, so the
  snapshot and the sentences that quote it cannot drift apart.
- **Window indexes migration.** Alembic revision `0005_window_indexes` builds
  the three window indexes concurrently on PostgreSQL, so a large table is not
  locked during the build.
- **Migrations work on MySQL.** `CREATE INDEX IF NOT EXISTS` is PostgreSQL-only,
  so the MySQL target was stuck two revisions behind and could not be
  brought up to date. The index helpers are now catalogue-aware.

### Verified

- The backend and frontend test suites pass, `ruff` and `mypy` are clean, and
  `eslint` runs at zero warnings. The current counts are in
  [`docs/stats.json`](docs/stats.json) and are re-measured by `make stats`.
- Both warehouses hold **zero** non-`real` rows. Prove it for your own
  database with `make audit`: it walks every table that records an upstream
  and exits non-zero the moment a row cannot be traced back to a source
  classified as real market data.
- Every dashboard screen renders real figures with **zero** console errors and
  **zero** failed requests, at desktop and phone widths.

## [1.12.0] - 2026-10-21

The theme of this release: **the numbers tell the truth, the preferences do
something, and the phone behaves like the desktop.**

### Fixed — metrics that were quietly wrong

- **DQ007 crashed on SQLite with `AttributeError: 'str' object has no attribute
  'tzinfo'`** — raw SQL returns DATETIME columns as text on SQLite (no native
  type), and the freshness rule called `.tzinfo` on it; the suite masked the
  crash as a failed rule. Timestamps are now parsed with `fromisoformat`
  (naive to UTC), with an honest `warn` verdict if unparseable. Covered by
  `test_dq007_freshness_handles_sqlite_text_timestamps`.
- **Crawler contact is now real** — `INGEST_USER_AGENT` uses
  `ahmedbakr78102@gmail.com` instead of the placeholder address.
- **Dashboard mixed lifetime and windowed counts.** The "canonical products"
  tile showed the all-time catalogue size while every neighbouring tile was
  scoped to the selected 7/30/90/180-day range, so switching the range changed
  most numbers but not that one. Every tile is now scoped to the same window,
  and `GET /analytics/kpi` returns `distinct_products` alongside the raw
  observation count.
- **"Products" vs "observations" are now two explicit tiles.** A canonical
  product (7,069) and a price snapshot (41,220) are different things; showing
  one of them as a side-hint made the headline number ambiguous. The tile hint
  now states the ratio between them instead of repeating one.
- **Account preference validation.** `PATCH /users/me` now clamps every known
  preference to its allowed value set, so a hand-written API call cannot put
  the dashboard into a state it cannot render.

### Added — preferences that actually do something

Five controls were saved to the profile but never read by any screen. They are
now wired end to end, and two new ones were added:

- **Auto-refresh cadence** drives a real refresh interval on the dashboard.
- **Default chart visualisation** picks area, line or bar for the market trend.
- **Default time range** decides which window the dashboard opens on.
- **Default export format** is offered first on every export control.
- **Copy code on click** copies generated SQL, serialised filters and JSON
  cells in one click.
- **NEW — number display** switches every count between compact (`40.2k`) and
  exact (`40,220`). This is the answer to "what is this 33.6k?".
- **NEW — silent reload** is no longer a dead preference. It swaps data in
  place with no skeleton shimmer, spinner sweep, transition or layout shift,
  and it is stored server-side so it follows the user across devices.

### Added — Builder

- **Twelve quick presets** (was six): flash drops, price hikes, out of stock,
  new arrivals, luxury tier, top rated, top movers, discounts under $50,
  recently removed, catalog mismatches, DQ failures and stale stock.
- **Active-filter chips.** Every filter narrowing the preview is listed as a
  removable chip, with a one-click "clear all". The builder applies a lot of
  filters at once, and there was previously no way to see or undo the
  combination as a whole.

### Fixed — the mobile shell

- **The content behind the open drawer could still be scrolled.** The scroll
  lock targeted `document.body`, but the shell scrolls `<main>`. Both are locked
  now.
- **The drawer stayed open across a phone to desktop resize**, leaving the page
  behind it locked and covered by an invisible backdrop. It now closes and
  releases the lock.
- **Back/forward never restored the scroll position.** The saved offset read
  `window.scrollY`, which is always `0` because `<main>` is the real scroller.
  The offset now comes from — and is restored to — the actual container.
- **The sidebar width had four independent sources.** The rail, the content
  gutter and two Tailwind spacing tokens could drift apart. They now share one
  set of CSS custom properties.

### Fixed — the backend

- **The seed could write observations from the future.** It anchored the demo
  history to the *local* calendar day, which is up to a full timezone offset
  ahead of UTC, so the newest snapshot could be hours ahead of "now". The
  anchor is now UTC and the newest day is clamped to the current instant.
- **The freshness DQ rule could report a negative age** under the same clock
  skew. A future-dated snapshot is now treated as zero hours old.
- **The `dq_failure` alert metric read the wrong run.** It took the most
  recent run whether or not that run had a data-quality verdict, so an
  unscored run silently masked the previous verdict. It now reads the most
  recent *scored* run.

### Changed — visual polish

- **Soft tints follow the accent.** Chips, badges and active rows were tinted
  with a fixed indigo regardless of the accent colour; they are now mixed from
  the live accent token.
- **A dark brand ramp.** Every brand shade now stays legible in the dark,
  midnight and high-contrast palettes.
- **Complete icon coverage.** Fourteen icon names the API could emit were
  missing from the frontend registry and silently rendered as a blank
  checklist glyph. All of them resolve now, and a parity test reads the backend
  catalogue straight from disk so the two can never drift again.
- **The infographic quotes the live DQ score.** It previously printed a
  hardcoded `98.26` that the warehouse did not hold; it is now read from the
  persisted `dq_rule_result` rows.

### Verified

- The backend and frontend test suites pass, `ruff check app/` clean,
  `eslint --max-warnings 0` clean, `tsc --noEmit` clean. The current counts
  are in [`docs/stats.json`](docs/stats.json) and are re-measured by
  `make stats`.
- The warehouse holds **zero** non-market rows. Prove it for your own
  database with
  `python scripts/audit_no_fakes.py --database <url>` - it walks every table
  that records an upstream and exits non-zero the moment a row cannot be
  traced back to a source classified as real market data.
- The compliance layer refused a robots-forbidden URL and throttled a second
  host during a live run, exactly as designed.

## [1.11.0] - 2026-10-20

### Added (Morning Briefing & 10x demo warehouse)

- **Morning briefing screen** at `/briefing` — a ranked action queue that composes
  existing analytics services instead of redefining metrics. Opportunities merge
  price drops, catalog gaps and discounts; risks merge rises, stockouts, anomalies,
  DQ failures and stale sources.
- **`GET /api/v1/intelligence/briefing`** — authenticated, windowed (1–3650 days)
  and bounded; every insight includes severity, metric, deep link and recommended
  action. Results are cached for 120 seconds per worker.
- **Account briefing defaults** — preferred window and queue size persist to the
  profile and follow the user across devices.
- **10x demo warehouse** — `pip-cli expand-demo` appends a deterministic synthetic
  cohort (19,500 products, 26 days, 506k snapshots, 13k catalog SKUs, lifecycle
  events and price changes), taking the demo to **25,076 products / 550k+ initial
  observations** and rebuilding `agg_category_daily` from facts.
- **Idempotent expansion** — the command detects an existing `SYN-` cohort and
  skips the expensive work; no existing product or snapshot is modified.
- **New feature groups** — Intelligence, 10x Demo Warehouse, and Mobile/Theme
  polish are now part of the 550-feature catalogue served by `/meta/features`.

### Changed

- Briefing/action ranking now filters extreme >65% moves and unit-mismatch catalog
  gaps, suppresses duplicate product/catalog snapshots, and formats sub-dollar
  prices with 4–8 decimals instead of `$0.00`.
- `best_value` excludes out-of-range ratings above 5.
- Mobile polish: compact stat tiles, two-column KPI grids, a safe-area-aware
  navigation drawer and a tighter header.
- Global scrollbars remain hidden; route chunks are preloaded during idle time so
  navigation stays silent. No route transition animations were added.

### Fixed

- Duplicate `Badge` children rendered twice.
- Document title stayed on “Sign in” after authentication.
- Demo `local_demo` history contained cross-run price outliers; the corrupted
  rows were removed and affected catalog rollups rebuilt.
- Briefing cache is invalidated by process restart; warm requests complete in
  ~10 ms and cold requests stay under ~3 s on the 538k-row fact table.

## [1.10.0] - 2026-10-15

### Fixed (real-data hardening)

- **Open Library robots block** — `/search.json` is disallowed by robots.txt (the gate
  correctly refused it, yielding 0 records). Switched to the allowed
  `/subjects/<subject>.json` feed; live records flow again with honest
  missing-price/availability flags for the DQ completeness rules.
- **Dead host** — `fakestore_products` unreachable (TCP + HTTP timeout). Removed from the
  DAG and seed defaults; per-source failure isolation already covers future outages.
- **Real-only auto-select** — a bare `run-pipeline` (no `--sources`) now excludes the
  synthetic `local_demo` source; fake rows only load when explicitly requested.
- **Proven with `./run-full-app.sh`** — one command runs lint, backend suites, a live
  3-source fetch smoke, a real SQLite pipeline (28 products / 28 snapshots, zero
  `local_demo` rows), frontend typecheck/lint/vitest/build and compose validation.
- **Single entrypoint `./run.sh`** — verifies with real data, then launches the Docker
  stack (`make run`); `--verify-only`, `--offline`, `--quick`, `--stop/--clean/--status`.

### Added (ingestion Max)

- **Three live-verified sources (31 to 34 adapters):** TVMaze shows, Internet Archive
  texts (robots-allowed advancedsearch feed), DummyJSON recipes — all proven with
  real records through cleaning. Rejected with evidence: MercadoLibre (robots
  `Disallow: /`), ITBookStore (all endpoints 404), Jikan (unreachable), BoardGameGeek
  (refuses programmatic access).
- **Scrapy crawling engine** — `BookSpider` (listing then detail, robots middleware,
  autothrottle, item cap) emitting identical `RawProduct` rows; `sources preview
  books_to_scrape --engine scrapy` (needs `pip install -e ".[scrapy]"`).
- **Conditional GET** — ETag / Last-Modified validators on every cached response;
  304 revalidations serve cache with zero bytes down and are audited as
  `revalidated`; validators outlive body TTL (30d). Covered by 5 mocked-transport
  tests + 7 adapter/spider mapping tests.
- **Team catalogue as code** — `app/core/team.py` + `GET /api/v1/meta/team`: Ahmed
  (78102) credited with 8 lead function groups; weights sum to 100, tested.
- **Longer repo surface** — README source catalog (34 adapters + landscape diagram),
  lead-functions section, refreshed website (team + sources sections, v1.10 numbers),
  `docs/31_releases.md` playbook, ownership diagram in `docs/00_team.md`.
  550 features across 46 areas.

## [1.9.0] - 2026-10-15

### Fixed

- **Source registry drift** — `load_builtin_sources()` now imports the `app.ingestion.sources`
  package once, so all 31 bundled adapters (cocktaildb, freeapi, mealdb, predic8,
  sampleapis_coffee, sampleapis_switch included) are visible on cold start.
- **Seed data correctness** — `unknown_availability` defect no longer overwritten by the RNG;
  null prices now carry null USD; `seed_catalog` is O(n) with no generator consumption.
- **Per-source aggregates** — `refresh_category_daily(source_code)` scopes SQL and storage by
  source instead of ignoring the argument.
- **Pipeline docstring** — stage order now matches `STAGE_NAMES`
  (`… detect, aggregate, reconcile, quality`).
- **Theme toggle memory** — header toggle restores the last dark variant (`pip.last-dark`);
  high-contrast follows the OS so light-HC and dark-HC palettes are both reachable.
- **Nav icon consistency** — Categories=FolderTree and Audit=Filter match the icon registry;
  `iconFor` warns in dev on unknown names.

### Added

- **Real-only production defaults** — DAG and `pipeline.default_sources` default to
  `dummyjson_products, fakestore_products, openlibrary_books`; `local_demo` stays for
  tests/CI/offline demos only (F-519).
- **Modern theme-aware scrollbars** — thin rounded thumbs on all scroll containers plus
  `.no-scrollbar` / `.scroll-thin` utilities (F-525).
- **Account Max tabs** — Watchlist (count badge + JSON export), Sessions (device table with
  current-device badge) and Shortcuts (keyboard-first reference) alongside the existing 9 tabs.
- **Feature catalogue v1.9** — 14 new entries (F-518…F-531); `docs/19_feature_list.md` totals
  531 features across 43 areas; `CONTRIBUTORS.md` + `docs/00_team.md` record the 6-member split.
- **README + Team polish** — corrected 29 tables / 23 views / 215 ops / 568 tests badges and hero,
  full 6-member team table, and copy-paste GitHub About/topics/private/release instructions.

## [1.8.0] - 2026-10-08

### Added

- **Query power Max** — the builder speaks post-aggregation: `having` predicates over grouping
  columns and aggregate aliases, per-request AND/OR `filter_logic` for WHERE filters, server-side
  enforcement of the schema's `groupable` flag, a strict identifier shape for aggregate aliases,
  deterministic ORDER BY on grouped queries, and a `supports` capability advertisement on
  `GET /builder/schema` (all echoed back in the query response beside `sql_preview`).
- **Saved-view lifecycle** — `GET /saved-views/{id}`, `PATCH` (clash-checked renames), server-side
  `POST …/duplicate`, per-entity `POST …/default` pinning (the list sorts the default first),
  visibility rules (private views 404 for others, shared views readable but immutable), and an
  `app_audit_log` trail for every mutation.
- **Server-side query history** — every console execution lands in `app_query_history`
  (rows, duration, truncation; 200 unsaved runs kept per user) with `GET /queries/history`,
  pin-as-snippet `POST …/save`, per-entry delete and clear-keeps-snippets; the QueryLab gains a
  History & snippets panel with one-click reload, a client-side SQL formatter, and an offline-aware
  error box. Secret tables (`app_user`, `app_api_key`, `app_session`, `app_webhook`) are refused
  by name, and the row cap is wrapped into the SQL so the engine never materialises unbounded results.
- **Server report CSV** — `GET /reports/{template}/csv` renders the same blocks as HTML/PDF:
  a `section,kind,label,value` frame plus every table block as a real CSV sub-table.
- **Type-safe setting writes** — `PUT /settings/{key}` preserves `value_type` when omitted and
  accepts category/description/visibility; every change is stamped and audited.
- **Scrollbar axis** — a seventh appearance dimension (`modern`/`auto`/`hidden`, `app_user.scrollbars`,
  synced to the profile): slim theme-aware thumbs, hover-revealed auto mode, and full-hide, all
  with a reserved gutter so switching never shifts layout; pre-paint script + Account control included.
- **Mobile navigation** — drawer search with group filtering, full focus trap, edge-swipe to open
  (RTL-aware), a More tab reaching every screen, and `100dvh` auth states against iOS URL-bar jitter.
- **Icons everywhere** — contextual `EmptyState` kinds (chart, price, shield, globe, …) across every
  screen plus icon buttons on toolbars, menus and dialogs.
- **Full-max pass** (with the parallel session) — Steam Store + Open Food Facts + Kraken + Makeup +
  Platzi + Yu-Gi-Oh! sources, GUI source onboarding, catalog CSV import, API key rotation/editing
  with a grantable-scopes endpoint, multi-level sorting, column pinning, share-as-URL links,
  watchlists, Excel exports, self-registration, and overlay scrollbars.

### Fixed

- **Full-suite rate limiting** — the test environment disables the API request budget
  (`RATE_LIMIT_ENABLED=false` in `tests/conftest.py`) so file order can never 429 an unrelated
  test; the limiter itself stays covered by unit tests.
- **Migration completeness gate** — `app_query_history` ships inside the initial revision, keeping
  the committed-migrations-build-everything test green.

### Changed

- Version 1.8.0 liberation: 496 catalogued features across 39 areas, 29 tables, 23 views,
  203 route decorators, 525 backend tests green, frontend typecheck/lint/tests green.

### Added

- **Excel exports** — every dataset downloads as a real `.xlsx` workbook (`GET /export/{dataset}.xlsx`):
  native dates/decimals, bold header, frozen top row, auto-filter and fitted columns. The ExportButton
  offers CSV, Excel and JSON on every dataset screen.
- **Product watchlists** — star products into a migration-free personal list (`GET/POST/DELETE
  /users/me/watchlist`, capped at 200, idempotent, synced with the profile and its export), with a
  star column and watched-only filter on Products, a Watch toggle on the detail page, and a CSV
  export of the Audit HTTP-compliance log.
- **Infographic dark variant + PDF** — the generator renders light and dark 2560×1440 sets (SVG + PNG)
  plus a PDF from one palette-parameterised builder, with `make infographic --check` and a CI step
  failing on stale artefacts.
- **Public self-registration** — `POST /auth/register` creates a viewer account (role forced server-side,
  409 on duplicates, 403 when `REGISTRATION_ENABLED=false`) and returns tokens immediately; the Login
  screen gains a sign-in / sign-up mode switch with full-name validation.

## [1.7.0] - 2026-10-06

### Added

- **Add sources from the GUI** — the Sources screen gains an *Add source* dialog: endpoint presets
  (DummyJSON, FakeStore, Shopify `products.json`, Open Food Facts, Open Library), a live compliance
  pre-check (SSRF guard + robots.txt verdict + JSON shape sniff), dot-path field mapping with three
  pagination styles, and one-click save. New endpoints: `GET /sources/presets`, `POST /sources/check`,
  `POST /sources`, `PATCH /sources/{code}`, `DELETE /sources/{code}` (admin-only mutations via the
  `manage_sources` right; analysts can check and preview). Dashboard rows materialise as a generic
  JSON adapter, join pipeline auto-selection, and support enable/disable plus history-guarded delete;
  bundled sources are read-only.

## [1.6.1] - 2026-10-06

### Fixed

- **Theme flash on accent** — the pre-paint script now resolves `--brand-*` CSS variables before
  first paint, so a non-default accent no longer flashes indigo on reload; `theme-color` metas are
  resolved for the actual (possibly system-derived) mode both pre-paint and at runtime.
- **Legacy motion value** — a stored `auto` motion preference is migrated to `full` instead of
  silently falling back, matching the original meaning.
- **Mobile drawer swipe-to-close** — the swipe-left-to-close gesture is wired to the drawer container
  so it works from any drawer child; removed an invalid bare `outline-none` DOM attribute.
- **Live job progress** — the queue derives streamed progress from the SSE event buffer (a real
  reactive dependency) instead of a mutated ref, so progress bars move between the 15 s polls; row
  expansion consistently uses `job_key`, matching the detail query.
- **Forecast rebuild result** — the rebuild panel stays visible with its succeeded/failed outcome
  instead of unmounting the moment the job finishes; a per-job guard keeps the completion effect
  firing exactly once.
- **Version drift** — the UI footer reads the version from `package.json` at build time
  (`__APP_VERSION__`) instead of a hardcoded literal; README badges reconciled to measured counts
  (28 tables, 173 operations, 104/104 smoke).
- **Lint/format gate** — `ruff format` drift in six files resolved; `change_event_summary` exported
  from `app.analytics.service`; `make_infographic.py` gains `--help`/`--check` like the other scripts.

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
  - [docs/24_demo_runbook.md](docs/24_demo_runbook.md) — the operational version of the demo: a
    pre-flight checklist, an eight-minute screen-by-screen script with exact URLs and the one
    sentence worth saying at each step, time-boxed 3/5/8-minute variants, the five questions that
    always get asked, and a failure playbook that falls back to `curl` when the browser dies. Every
    command and URL in it was executed against the running stack before being written down.
- **A documentation website**, built by `scripts/build_site.py` using only the standard library:
  one page per document, client-side search over a generated index, a dark mode that follows the
  system preference, and all diagrams rendered. It is dependency-free by design — GitHub Pages does
  not serve private repositories on the free plan, so a Pages workflow could never deploy here, while
  a static directory works anywhere. Build with `make site`, preview with `make site-serve`.
- **`.github/FUNDING.yml`** — declares *no* funding platform, so an absent "Sponsor" button is a
  deliberate statement rather than an oversight: MIT licensed, nothing to pay for, no paid
  dependencies. The comments show how to add a platform if that ever changes.
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

### Verified

All six CI jobs green on the release commit:

```text
Backend (lint, types, tests)        success
Frontend (lint, typecheck, build)   success
REST API smoke test                 success
PostgreSQL + MySQL parity           success
Documentation (diagrams, links)     success   66/66 diagrams parse, 748 links resolve
Project statistics (no drift)       success   every documented figure matches the code

ruff: all checks pass               mypy: no issues
pytest: 321 passed                  API smoke: 86/86 checks
```

### Notes

- `tsc --noEmit` at the repository root is a no-op because `tsconfig.json` uses project references;
  use `npm run typecheck` (`tsc --noEmit -p tsconfig.app.json`), `npm run build:strict` (`tsc -b`) or
  `npx tsc -b --noEmit` to type-check the dashboard.
- Documentation figures are now measured, not asserted. `make stats` prints them, `make stats-check`
  fails on drift, and `make docs-check` runs the diagram, anchor, link and figure gates together.

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