# 19 — Feature Inventory

## Purpose

This document is the complete feature inventory of the Web-to-Warehouse Product Intelligence
Pipeline: 410 features grouped into twenty-three areas, each with a one-line description and a reference
to the file that implements it. Every entry corresponds to shipped behaviour — a function, a table, an
endpoint, a CLI command or a documented design decision. Nothing here is aspirational.

**Scale of the system, measured:** 5 ingestion sources · 27 physical tables · 20 analytical views ·
12 data-quality rules across 6 dimensions · 131 REST route decorators (128 documented in OpenAPI plus
3 internal probes) in 18 routers · 9 pipeline stages · 14 Airflow tasks · 6 Docker Compose services ·
23 numbered documents · 66 Mermaid diagrams · 321 automated tests · 86 end-to-end API smoke checks.

Regenerate the numbers above with `python3 scripts/project_stats.py`.

---

## Table of contents

1. [Ingestion and web compliance (24)](#1-ingestion-and-web-compliance-24)
2. [Cleaning and normalisation (29)](#2-cleaning-and-normalisation-29)
3. [Duplicate resolution (17)](#3-duplicate-resolution-17)
4. [Warehouse model (20)](#4-warehouse-model-20)
5. [ETL pipeline (15)](#5-etl-pipeline-15)
6. [Change detection (6)](#6-change-detection-6)
7. [Catalog reconciliation (7)](#7-catalog-reconciliation-7)
8. [Data quality (10)](#8-data-quality-10)
9. [Analytics and SQL reporting (18)](#9-analytics-and-sql-reporting-18)
10. [REST API (26)](#10-rest-api-26)
11. [Security and access control (10)](#11-security-and-access-control-10)
12. [Dashboard and user experience (12)](#12-dashboard-and-user-experience-12)
13. [Operations, orchestration and DX (24)](#13-operations-orchestration-and-dx-24)

Platform increments: [v1.1 (8)](#14-dashboard-v11-additions-8) ·
[v1.2 (8)](#15-platform-v12-additions-8) · [v1.3 (37)](#16-platform-v13-additions-37) ·
[v1.4 (40)](#17-platform-v14-additions-40)

---

## 1. Ingestion and web compliance (24)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-001 | Source contract | Abstract base class every source implements, with one abstract `fetch(limit)` method | `app/ingestion/base.py` `ProductSource` |
| F-002 | Source registry | `@register_source` decorator plus `get_source`, `get_source_class`, `list_sources`, `all_source_codes` | `app/ingestion/base.py` |
| F-003 | Lazy extraction | Sources are generators, so a run stops as soon as the limit is reached | `app/ingestion/sources/*.py` |
| F-004 | Declarative compliance metadata per source | `terms_url`, `license_note`, `terms_allowed`, `rate_limit_per_minute`, `min_delay_seconds`, `supports_paging` | `app/ingestion/base.py` class variables |
| F-005 | robots.txt parsing | Standard-library parser with a per-host cache and thread-safe locking | `app/ingestion/robots.py` `RobotsCache` |
| F-006 | RFC 9309 fallback semantics | 4xx → allow all; 401/403 → disallow; 5xx/network → cached failure | `app/ingestion/robots.py` `_load` |
| F-007 | Crawl-delay extraction | `Crawl-delay` read from the matched group and returned in the decision | `app/ingestion/robots.py` `RobotsDecision` |
| F-008 | Sitemap discovery | `Sitemap:` lines collected per host | `app/ingestion/robots.py` `sitemaps` |
| F-009 | Robots gate in the transport layer | Every request is checked before it is made; a refusal raises `ComplianceError` and is logged | `app/ingestion/http_client.py` `get` |
| F-010 | Token-bucket rate limiting | Smoothed average rate per host with a burst allowance | `app/ingestion/ratelimit.py` `RateLimiter` |
| F-011 | Sliding-window ceiling | Hard per-minute cap even when bursts are allowed | `app/ingestion/ratelimit.py` `_prune_window` |
| F-012 | Effective delay | The slowest of the global delay, the per-minute budget and the crawl delay wins | `app/ingestion/ratelimit.py` `HostState.effective_delay` |
| F-013 | `Retry-After` support | Both delta-seconds and HTTP-date forms parsed and honoured | `app/ingestion/http_client.py` `_parse_retry_after` |
| F-014 | Exponential backoff with jitter-free doubling | `retry_backoff × 2^attempt` for retryable statuses and network exceptions | `app/ingestion/http_client.py` |
| F-015 | Circuit breaker | A host that fails five times in a row is skipped without network I/O | `app/ingestion/ratelimit.py` `CircuitBreaker` |
| F-016 | Disk response cache | Responses cached by URL hash with a TTL, so a repeat run performs zero requests | `app/ingestion/http_client.py` `_read_cache` / `_write_cache` |
| F-017 | Per-request audit trail | One row per outbound attempt with status, latency, bytes, robots decision, cache flag and retries | `app/ingestion/http_client.py` `HttpAuditEntry` → `ingestion_http_log` |
| F-018 | Honest crawler identity | User agent names the bot and publishes a contact address | `app/core/config.py` `ingest_user_agent` |
| F-019 | Source failure isolation | An exception in one source becomes a warning; the run continues as `partial` | `app/etl/pipeline.py` `_process_source` |
| F-020 | Bounded extraction | `--limit` plus `_safe_take` prevents a misbehaving source from hanging a run | `app/etl/pipeline.py` |
| F-021 | Five source adapters | DummyJSON, FakeStore, Open Library (APIs), books.toscrape.com (HTML), local demo (synthetic) | `app/ingestion/sources/` |
| F-022 | BeautifulSoup + lxml scraper | Listing → detail crawl, breadcrumb categories, price, stock count, star rating, UPC, image | `app/ingestion/sources/books_to_scrape.py` |
| F-023 | Deterministic offline source | Seeded generator used for demos, tests and CI, with deliberate quality defects injected | `app/ingestion/sources/local_fixture.py` |
| F-024 | Source transparency endpoint | Fetch a few raw records and see them side by side with the cleaned result | `GET /api/v1/sources/{code}/preview` |

---

## 2. Cleaning and normalisation (29)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-025 | Unicode folding | NFKC normalisation plus smart-quote, dash, ellipsis and zero-width translation | `cleaning.normalise_unicode` |
| F-026 | HTML stripping | Tags removed and entities unescaped | `cleaning.strip_html` |
| F-027 | Promotional noise removal | 17 prefix patterns (`SALE:`, `HOT SALE`, `CLEARANCE`, …) and 9 suffix patterns (`(new)`, `- free shipping`, `50% off`) | `cleaning.PROMO_PREFIXES` / `_PROMO_SUFFIXES` |
| F-028 | Marketing-tag removal | Bracketed qualifiers up to 40 characters are dropped | `cleaning._BRACKETED_RE` |
| F-029 | Smart title casing | Applied only when a title is entirely lower case; known acronyms (`USB`, `4K`, `OLED`) are preserved | `cleaning._smart_title` |
| F-030 | Word-boundary truncation | Long names are cut at the last complete word and marked with an ellipsis | `cleaning.clean_product_name` |
| F-031 | Brand cleaning | `by` / `brand:` prefixes removed; stop-word brands rejected; capped at 128 characters | `cleaning.clean_brand` |
| F-032 | Normalised comparison key | Lower-case alphanumerics, 60 stop-words removed, tokens sorted and de-duplicated | `cleaning.normalise_name_key` |
| F-033 | Product fingerprint | `sha1(brand_key + "|" + name_key)[:32]` — the exact-match key | `cleaning.name_fingerprint` |
| F-034 | Blocking key | First four characters of the normalised key; the candidate-generation mechanism | `cleaning.blocking_key` |
| F-035 | Category synonym map | ~140 mappings to a canonical hierarchy such as `tech → Electronics`, `jewellery → Accessories > Jewellery` | `cleaning.CATEGORY_SYNONYMS` |
| F-036 | Breadcrumb normalisation | `/`, `\|`, `»`, `›`, `->`, `=>` all become `>` and each segment is canonicalised | `cleaning.normalise_category` |
| F-037 | Category slug and level | URL-safe slug for a path; depth counter for the hierarchy | `cleaning.category_slug`, `category_levels` |
| F-038 | Locale-aware number parsing | Resolves `1,234.56` vs `1.234,56` and the single-separator ambiguity | `cleaning.parse_number` |
| F-039 | Competing price patterns | Five patterns scored by confidence (ISO code 0.95 → bare number 0.60); the strongest candidate wins | `cleaning.parse_price`, `_PATTERN_CONFIDENCE` |
| F-040 | Price-range handling | `$10 – $20` yields the midpoint plus both bounds and `is_range=True` | `cleaning.parse_price` |
| F-041 | Was/now handling | `Was $49.99 Now $39.99` resolves to the current price with pattern `was_now` | `cleaning.parse_price` |
| F-042 | Unavailable markers | `free`, `N/A`, `poa`, `call for price`, `tbd` produce a null price and the `unparseable_price` flag | `cleaning._UNAVAILABLE_RE` |
| F-043 | Currency resolution | 60 symbol/code mappings plus a dominant-symbol heuristic for long blobs | `cleaning.normalise_currency` |
| F-044 | Locale currency detection | Host suffix (`.co.uk`, `.de`, `.co.jp`…), microdata markers, symbol frequency | `cleaning.detect_currency_locale` |
| F-045 | FX normalisation | Static 25-currency reference table; the applied rate is stored with the observation | `cleaning.convert_to_usd`, `STATIC_FX_RATES` |
| F-046 | Rating rescaling | `4.2 out of 5`, `84 percent`, `8.5/10`, star counts and bare numbers all rescale to 0–5 and are clamped | `cleaning.parse_rating` |
| F-047 | Availability mapping | Six token families resolved with a documented precedence to a five-value vocabulary | `cleaning.normalise_availability` |
| F-048 | Quality flags | `unparseable_price`, `missing_rating`, `unknown_availability`, `invalid_url`, `name_equals_category`, `missing_price` | `app/ingestion/base.py` `transform_product` |
| F-049 | Validation gates | Short names are always rejected; missing price or an invalid URL reject in strict mode, with a reason | `app/ingestion/base.py` |
| F-050 | URL validation | `^https?://host` only | `cleaning.validate_url` |
| F-051 | Payload content hash | Deterministic SHA-256 over source, id, name, price and availability for re-ingestion checks | `cleaning.content_hash` |
| F-052 | Human price formatting | Symbol-aware formatting with thousands separators for reports and the CLI | `cleaning.format_price` |
| F-053 | Percentage change | `None`-safe, symmetric against negative prices, division by zero handled | `cleaning.percent_change` |

---

## 3. Duplicate resolution (17)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-054 | Levenshtein distance | Two-row dynamic programme with early abandonment above a maximum distance | `dedupe.levenshtein` |
| F-055 | Jaro similarity | Transposition- and typo-robust, normalised by string length | `dedupe.jaro` |
| F-056 | Jaro-Winkler | Prefix bonus (`0.1`, max 4 characters) applied only when the base score exceeds 0.7 | `dedupe.jaro_winkler` |
| F-057 | Token-sort ratio | Order-insensitive comparison of two token sequences | `dedupe.token_sort_ratio` |
| F-058 | Token-set ratio | Best of three comparisons, mirroring the established fuzzywuzzy algorithm | `dedupe.token_set_ratio` |
| F-059 | Trigram Dice coefficient | Padded character trigrams with a 50,000-entry LRU cache | `dedupe.trigram_similarity` |
| F-060 | Digit-signature guard | Ordered digit runs compared; one difference multiplies the score by 0.85, more by 0.60 | `dedupe.digit_signature`, `digit_signature_factor` |
| F-061 | Blended similarity | Weighted blend of six measures (0.20/0.15/0.10/0.05/0.20/0.30) plus per-measure parts | `dedupe.combined_similarity` |
| F-062 | Character-evidence short circuit | Near-identical strings that differ only in punctuation bypass the blend at a 3 % discount | `dedupe.combined_similarity` |
| F-063 | Brand term | `score × 0.88 + brand_similarity × 0.12` when both brands are known | `dedupe.combined_similarity` |
| F-064 | Category bonus | Up to +0.03 for an equal or containing category | `dedupe.combined_similarity` |
| F-065 | Three-stage matching cascade | Fingerprint exact → normalised-name equality → fuzzy above the threshold | `DedupeEngine.find_match` |
| F-066 | Blocking candidate retrieval | Prefix `LIKE` on `normalized_name` and `canonical_name`, capped at 25, refined by brand | `DedupeEngine._blocking_candidates` |
| F-067 | Fingerprint cache | Loaded once per run, updated on register and on merge; removes a query per record | `DedupeEngine._load_fingerprints` |
| F-068 | Merge bookkeeping | Survivor chosen by observation count; absorbed row gets `matched_product_id` and `match_strategy='merged'` | `DedupeEngine.merge_into` |
| F-069 | Match provenance stored | Strategy, score and the per-measure breakdown persisted on `dim_product` | `dim_product.match_strategy` / `match_score` |
| F-070 | Batch and offline resolution | `resolve_batch` for bulk resolution; `duplicates_in_iterable` for offline inspection | `DedupeEngine` |

---

## 4. Warehouse model (20)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-071 | Dimensional model | Five conformed dimensions shared by three facts and two change feeds | `app/models/dimensions.py`, `facts.py` |
| F-072 | Append-only price fact | One row per product per source per run, enforced by a unique constraint | `fact_price_snapshot`, `uq_fact_price_product_run` |
| F-073 | Change-feed tables | `chg_price_change` and `chg_product_event` as an immutable event ledger | `app/models/facts.py` |
| F-074 | Category hierarchy | Self-referencing `parent_id` with `level` and a materialised `path` | `dim_category` |
| F-075 | Pre-populated calendar | `YYYYMMDD` surrogate key, 400 days back and 2 forward by default, idempotent | `dim_date`, `bootstrap.ensure_date_range` |
| F-076 | Currency reference | Code, name, symbol, rate to USD, rate source and as-of date | `dim_currency` |
| F-077 | Portable JSON columns | `JSON(none_as_null=True)` so `IS NULL` behaves identically on all dialects | `app/models/base.py` `JSONType` |
| F-078 | Timezone-safe timestamps | `UTCDateTime` converts on write and re-tags on read | `app/models/base.py` |
| F-079 | Exact money type | `NUMERIC(18, 4)` for every monetary column | `app/models/base.py` `NumericMixin` |
| F-080 | Consistent object naming | Metadata naming convention for indexes, unique constraints, checks, foreign keys and primary keys | `app/models/base.py` `Base.metadata` |
| F-081 | Staging landing zone | Raw payloads with hash, HTTP status, validity and rejection reason | `stg_raw_observation` |
| F-082 | Sync checkpoints | Per-source last run, last success, failure streak, cursors and status | `sync_state` |
| F-083 | Materialised aggregate | Category-day counts, price statistics, new/removed counts and change counts | `agg_category_daily` |
| F-084 | Source reference with reliability | Kind, robots/terms URLs, licence note, run counters, success rate and average duration | `dim_source` |
| F-085 | Internal catalogue store | The retailer's SKUs with cost, list price, supplier, stock and status | `catalog_product` |
| F-086 | Application tables | Accounts, API keys, saved views, alerts, notifications, audit and settings | `app/models/app_users.py` |
| F-087 | One-command bootstrap | Schema, reference data and views for any target | `app/etl/bootstrap.py` `bootstrap` |
| F-088 | Portable view application | Each view statement runs in its own transaction with dialect-correct quoting | `app/etl/bootstrap.py` `apply_views` |
| F-089 | Schema verification | Compares the physical schema with the ORM and reports missing tables | `app/cli/main.py` `check-schema` |
| F-090 | Row-count reporting | Per-table counts used by `status`, `verify` and the health endpoint | `app/etl/bootstrap.py` `table_report` |

---

## 5. ETL pipeline (15)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-091 | Declarative run configuration | Sources, target database, limit, strictness, skips, staleness, trigger, identity | `PipelineConfig` |
| F-092 | Rich run result | Counters, quality summary, reconciliation summary, stage timings, warnings, processed and failed sources | `PipelineResult` |
| F-093 | Nine instrumented stages | extract, stage, transform, resolve, load, detect, reconcile, quality, aggregate — each timed with row counts | `STAGE_NAMES`, `Pipeline._timer` |
| F-094 | Source dimension registration | `dim_source` ensured before any fact references it (foreign-key integrity) | `Pipeline._process_source` |
| F-095 | Running source statistics | Total records, run count, rolling success rate and rolling average duration | `Pipeline._register_source_dim` |
| F-096 | Dimension cache warm-up | One query per dimension instead of one per record | `WarehouseLoader.preload_dimensions` |
| F-097 | Category materialisation | Each path segment becomes a row with the correct parent and level | `WarehouseLoader.resolve_category` |
| F-098 | Product upsert | Creates or updates the canonical row, maintains prices, observation count and quality flags | `WarehouseLoader.upsert_product` |
| F-099 | Batch loading | Staging and fact inserts batched by `PIPELINE_BATCH_SIZE` | `WarehouseLoader.stage`, `insert_snapshot` |
| F-100 | N+1 elimination | The previous snapshot for every product of a source is fetched in one ordered query | `WarehouseLoader.preload_latest` |
| F-101 | Intra-run grain protection | A second record resolving to the same product is skipped and counted as a merge | `Pipeline._process_source` |
| F-102 | Aggregate refresh | Category-day aggregates rebuilt for the dates a run touched, idempotently | `WarehouseLoader.refresh_category_daily` |
| F-103 | Status logic | `failed` on blocking DQ failure, `partial` when a source failed, otherwise `success` | `Pipeline._execute` |
| F-104 | Fail-fast mode | Optional strict behaviour for CI and unattended runs | `settings.pipeline_fail_fast` |
| F-105 | Sync-state updates | Source cursors and failure streaks maintained after every run | `WarehouseLoader.update_sync_state` |

---

## 6. Change detection (6)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-106 | Price change events | Absolute and percentage change with direction, magnitude band and significance | `WarehouseLoader.insert_snapshot` |
| F-107 | Magnitude banding | minor (< 1 %), small (< 5 %), moderate (< 15 %), large (< 30 %), major (≥ 30 %) | `loader.magnitude_band` |
| F-108 | First sighting detection | A product with no previous snapshot emits a `new` event and sets `is_first_sighting` | `WarehouseLoader.insert_snapshot` |
| F-109 | Recurring sightings | Later observations emit a `recurring` event carrying the previous and current price | `WarehouseLoader.insert_snapshot` |
| F-110 | Removal detection | Products unseen beyond the staleness window (default 7 days) are deactivated with a `removed` event | `WarehouseLoader.detect_removed` |
| F-111 | Category change detection | A different resolved category emits `category_changed` with the old and new category ids | `WarehouseLoader.upsert_product` |

---

## 7. Catalog reconciliation (7)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-112 | Three-stage match cascade | SKU identifier, then normalised name, then fuzzy above 0.86 | `CatalogReconciler.match_one` |
| F-113 | Blocking index | 4-character block index plus a rare-token fallback index, so each SKU sees a handful of candidates | `CatalogReconciler._build_indexes` |
| F-114 | Candidate pool floor | When the prefix pool is smaller than `min_pool`, the pool widens rather than narrowing | `CatalogReconciler._narrow_candidates` |
| F-115 | Price-gap analysis | Absolute and percentage gap between the market and our list price | `CatalogReconciler.match_one` |
| F-116 | Mismatch flagging | Gaps of 1 % or more are flagged as a pricing opportunity | `PRICE_GAP_THRESHOLD_PCT` |
| F-117 | Market position | `we_are_cheaper` or `we_are_dearer` derived from the gap sign | `GET /api/v1/catalog/opportunities` |
| F-118 | Match evidence | Brand and category match flags, similarity, supplier, scraped category and candidate count persisted as JSON | `fact_catalog_snapshot.details` |

---

## 8. Data quality (10)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-119 | Twelve rules, six dimensions | Completeness ×4, validity ×3, uniqueness ×2, consistency ×1, accuracy ×1, timeliness ×1 | `app/etl/dq.py` `RULES` |
| F-120 | Declarative rules | Frozen dataclasses with a code, name, dimension, severity, description and evaluator | `dq.Rule` |
| F-121 | Three-band classification | pass / warn (within 5 % of the threshold) / fail | `dq._status` |
| F-122 | Severity-weighted score | 0–100, `weight = 1 + 0.5 × severity_rank` | `QualityReport.score` |
| F-123 | Critical-only blocking | Only `critical` failures can fail a run | `QualityReport.blocking_failures` |
| F-124 | Rule isolation | Each rule evaluates inside a savepoint; failures are recorded, not raised | `Rule.run` |
| F-125 | Per-run persistence | Every outcome stored with observed/expected values, counts, message and evidence | `dq_rule_result` |
| F-126 | Rule catalogue endpoint | The 12 rules with descriptions and no evaluator payload | `GET /api/v1/quality/rules` |
| F-127 | Quality history and trend | Paginated history plus a per-run score trend with a threshold line | `GET /api/v1/quality/results`, `/trend` |
| F-128 | Quality posture summary | Counts by dimension and status plus the ten worst findings | `GET /api/v1/quality/summary` |

---

## 9. Analytics and SQL reporting (18)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-129 | Twenty analytical views | The semantic layer over the star schema, portable across three engines | `db/views.sql` |
| F-130 | KPI summary | Products, sources, average/min/max price, average rating, in-stock count, change statistics, event mix, quality, catalog | `analytics.kpi_summary` |
| F-131 | Daily trend | Observations, products, average price, average rating and in-stock percentage per day | `analytics.daily_trend` → `vw_daily_kpis` |
| F-132 | Price-change timeline | Daily increase/decrease counts with mean and maximum absolute change | `analytics.price_change_timeline` |
| F-133 | Top movers | Largest absolute movements with an optional direction filter | `analytics.top_movers` → `vw_top_movers` |
| F-134 | Category breakdown | Observations, price range, rating, new products and changes per category | `analytics.category_breakdown` |
| F-135 | Brand leaderboard | Product count, price range, rating and in-stock observations per brand | `analytics.brand_leaderboard` |
| F-136 | Availability summary | In-stock percentage and out-of-stock counts per category | `analytics.availability_summary` |
| F-137 | Category tree with live counts | Hierarchy with active product counts and average price | `analytics.category_tree` |
| F-138 | Lifecycle feeds | New products, removed products with days missing, category changes | `analytics.new_products`, `removed_products`, `category_changes` |
| F-139 | Category drift report | Added, removed, recategorised and net change per category | `analytics.category_drift_report` |
| F-140 | Category price index with portable variance | Average, min, max, rating and a `SQRT(E[x²]−E[x]²)` standard deviation | `vw_category_price_index` |
| F-141 | Compliance report | Requests, blocked, cached, retried, bytes, latency and hosts | `analytics.compliance_report` |
| F-142 | HTTP audit feed | Every request flattened for the compliance screen | `vw_http_audit` |
| F-143 | Price history series | Per-product time series with the change context | `analytics.price_history` |
| F-144 | Query plan explorer | Dialect-aware `EXPLAIN` for any view | `analytics.query_explain` |
| F-145 | CSV export | The current product list as CSV, capped at 50,000 rows | `GET /api/v1/analytics/export/products.csv` |
| F-146 | Table inventory API | 23 tables grouped into the six logical groups | `GET /api/v1/meta/tables` |

---

## 10. REST API (26)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-147 | Sixteen routers, 113 operations | Every analytical and operational capability exposed and documented | `app/api/routers/` |
| F-148 | Health, readiness and metadata | Liveness with the database probe, readiness with a schema check, `/meta`, `/version`, `/stats/tables` | `app/api/routers/health.py` |
| F-149 | Login, refresh, logout | Credential exchange with lockout handling and an audit row | `app/api/routers/auth.py` |
| F-150 | Session introspection | The shell reads role, permissions, theme, accent, density, rows per page and token lifetime | `GET /api/v1/auth/session` |
| F-151 | Product catalogue endpoints | List with 14 filters, facets, category tree, type-ahead, compare, detail, history, duplicates, catalog links | `app/api/routers/products.py` |
| F-152 | Change-feed endpoints | Price changes, top movers, events, new, removed, category changes, drift, summary | `app/api/routers/changes.py` |
| F-153 | Analytics endpoints | KPI, trend, price trend, categories, brands, availability, sources, category index and four reports | `app/api/routers/analytics.py` |
| F-154 | Pipeline endpoints | Run history, latest run, run detail, DQ and HTTP audit per run, stages, schedule | `app/api/routers/pipeline.py` |
| F-155 | Background run trigger | `POST /pipeline/run` queues a run and creates a notification | `routers/pipeline.py` `trigger` |
| F-156 | Synchronous run trigger | `POST /pipeline/run/sync` returns the full `PipelineResult` | `routers/pipeline.py` `trigger_sync` |
| F-157 | Quality endpoints | Latest, per run, catalogue, history, trend, posture | `app/api/routers/quality.py` |
| F-158 | Catalog endpoints | Reconciliation with filters, internal SKUs, summary by strategy and supplier, opportunities | `app/api/routers/catalog.py` |
| F-159 | Source endpoints | Registry with compliance metadata, robots cache statistics, single source, raw preview | `app/api/routers/sources.py` |
| F-160 | Read-only query console | Validated `SELECT`/`WITH`/`EXPLAIN` with a 5,000-row cap and truncation flag | `app/api/routers/queries.py` |
| F-161 | Query discovery | View list, table groups and five starter queries | `/queries/views`, `/tables`, `/examples` |
| F-162 | Saved views | Create, list (own + shared), favourite, delete and usage counter | `app/api/routers/saved_views.py` |
| F-163 | Alerts | CRUD over five metrics with five operators plus a live evaluation endpoint | `app/api/routers/notifications.py` |
| F-164 | Notifications | Paged feed, unread filter, mark one and mark all as read | `app/api/routers/notifications.py` |
| F-165 | Settings | Grouped list, admin upsert and delete, public-flag visibility | `app/api/routers/settings.py` |
| F-166 | Audit endpoints | Paged audit log with action/user/window filters plus a distinct-action summary | `app/api/routers/audit.py` |
| F-167 | User administration | List, create, update, deactivate, statistics, own-profile endpoints | `app/api/routers/users.py` |
| F-168 | API key endpoints | Create (shown once), list and revoke | `/users/{id}/api-keys` |
| F-169 | Pagination convention | `page`, `page_size ≤ 200`, whitelisted sorting, exact totals, seven-field envelope | `app/api/deps.py` `Pagination`, `schemas.Page` |
| F-170 | Consistent error envelope | `error`, `message`, `details`, `path` for every failure class | `app/api/main.py` handlers, `app/core/errors.py` |
| F-171 | Performance headers | `X-Process-Time-Ms` and `X-Database` on every response; slow requests logged | `app/api/main.py` timing middleware |
| F-172 | CORS and compression | Configurable allow-list; GZip above 1 KB | `app/api/main.py` middleware |

---

## 11. Security and access control (10)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-173 | Argon2id password hashing | `time_cost=2`, `memory_cost=64 MiB`, `parallelism=2`, with automatic rehash | `app/api/security.py` |
| F-174 | Password strength gate | Length, upper, lower, digit and symbol enforced server-side and surfaced in the UI | `security.password_strength`, `schemas.PasswordChangeRequest` |
| F-175 | Account lockout | Five consecutive failures lock the account for 15 minutes | `routers/auth.py` `MAX_FAILED_LOGINS` |
| F-176 | JWT access and refresh tokens | HS256 with `sub`, `role`, `email`, `iat`, `exp`, `type` and `iss`; type confusion rejected | `security.create_access_token` / `decode_token` |
| F-177 | Scoped, hashed API keys | `pip_` prefix, SHA-256 with a server pepper, expiry, usage counter, revocation | `security.generate_api_key` |
| F-178 | Role-based authorisation | Three roles, ten rights, enforced by a dependency factory | `security.ROLE_RIGHTS`, `deps.require_rights` |
| F-179 | Read-only query guard | Write keywords, comments and multi-statement payloads rejected before execution | `schemas.QueryRequest._readonly` |
| F-180 | Audit trail | Login, logout, failed login, password change, user management, pipeline trigger and settings writes | `app/models/app_users.py` `AppAuditLog` |
| F-181 | Secret redaction | Connection strings masked as `scheme://***:***@host` in every log line | `app/core/config.py` `describe_target` |
| F-182 | Field-level response control | `hashed_password` never appears in a response model | `app/api/schemas.py` `UserRead` |

---

## 12. Dashboard and user experience (12)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-183 | Twelve screens specified | Dashboard, Products, Product detail, Changes (6 tabs), Analytics, Pipeline, Run detail, Quality, Catalog, Sources, Query Lab, Account, Admin | `docs/12_ui_ux_design.md` |
| F-184 | Light and dark themes | `system`, `light` and `dark` persisted per user; measured contrast ratios for every token pair | `app_user.theme`, doc 12 §6 |
| F-185 | Accent and density preferences | Five accents and three row densities, applied without a reload | `app_user.accent`, `app_user.density` |
| F-186 | Filter, sort and paging on every list | Filter state lives in the URL so a view is shareable | doc 12 §5.3 |
| F-187 | Saved filter views | Per-user or shared presets with favourites and usage counters | `app_saved_view` |
| F-188 | Type-ahead search | Suggestions after two characters, normalised on the server | `GET /api/v1/products/search/suggest` |
| F-189 | Side-by-side comparison | Up to six products in one drawer | `GET /api/v1/products/compare/ids` |
| F-190 | Exports | CSV for the product list and filtered reports | `analytics/export/products.csv` |
| F-191 | WCAG 2.1 AA design system | Contrast-verified palette, visible focus, keyboard operation, ARIA live regions, 200 % zoom, 320 px reflow | doc 12 §7 |
| F-192 | Responsive from 320 px | Three breakpoints; cards replace grids on mobile; the filter rail becomes a sheet | doc 12 §8 |
| F-193 | Silent motion policy | No decorative animation, no spinners, no transitions; `prefers-reduced-motion` respected | doc 12 §9 |
| F-194 | Transparency panel | Raw-versus-cleaned source preview as a first-class feature | `GET /api/v1/sources/{code}/preview` |

---

## 13. Operations, orchestration and DX (24)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-195 | Eleven CLI commands | Eleven commands (`init-db`, `bootstrap`, `seed-demo`, `run-pipeline`, `report`, `quality`, `verify`, `serve`, `status`, `check-schema`, `version`) plus two command groups (`sources list|preview|check`, `user list|create|token`) | `app/cli/main.py` |
| F-196 | Rich terminal reports | Tables, panels and colour-coded status for runs, movers, drift, quality and sources | `app/cli/main.py` |
| F-197 | Cross-dialect verification | Compares structural counts and the DQ score across targets and reports drift | `pip-cli verify` |
| F-198 | Thirty-plus Make targets | One-command install, databases, bootstrap, demo, pipeline, API, tests, frontend, Airflow, docs | `Makefile` |
| F-199 | Airflow DAG with 13 tasks | Two short-circuit guards, extraction, change detection, DQ gate, aggregates, reconciliation, branch, notification and report | `dags/product_intelligence_pipeline.py` |
| F-200 | Recoverable orchestration | Two retries with exponential back-off, 45-minute execution timeout, `max_active_runs=1` | DAG `DEFAULT_ARGS` |
| F-201 | Change-aware branching | Notifications run only when the run actually produced changes (XCom branch) | DAG `branch_on_changes` |
| F-202 | Report artefact | The analytics report is written to `var/artifacts/report-*.json` by the DAG | DAG `publish_report` |
| F-203 | Airflow-optional imports | The DAG module imports without Airflow installed, so tests and the CLI still work | `dags/…` try/except with `AIRFLOW_AVAILABLE` |
| F-204 | Six-service Compose stack | PostgreSQL 16, MySQL 8.4, API, Airflow, Airflow scheduler, frontend | `docker-compose.yml` |
| F-205 | Health-gated startup | The API waits for both databases to be healthy | Compose `depends_on: condition: service_healthy` |
| F-206 | Read-only code mounts | `./app` and `./db` are mounted read-only into the API and Airflow containers | `docker-compose.yml` |
| F-207 | Validated configuration | One typed `Settings` object with validators, reloadable, documented variable by variable | `app/core/config.py`, doc 17 §7 |
| F-208 | Seeded demo dataset | Users, internal catalog, saved views, alerts, 150 days of price history with realistic promotions | `app/etl/seed.py` |
| F-209 | API smoke suite | 78 checks covering every router, including 401 and 403 paths | `scripts/api_smoke.py` |
| F-210 | Cross-dialect verification command | `make verify-dialects` in CI and locally | `Makefile`, `app/cli/main.py` |
| F-211 | Typed error taxonomy | 13 domain exceptions mapped to HTTP status codes | `app/core/errors.py` |
| F-212 | Structured logging | ANSI console, JSON for shippers, rotating file handler, third-party log quieting | `app/core/logging.py` |
| F-213 | Lint, format and type checking | ruff (E,F,W,I,UP,B,C4,SIM) and mypy configured with a 110-character line limit | `pyproject.toml`, `make lint`, `make typecheck` |
| F-214 | Six-step source extension | Documented procedure with a worked adapter template | doc 17 §8 |
| F-215 | Regenerable diagrams | The ERD and the API catalogue are generated from the code, so they cannot drift | doc 9 §11.2, doc 14 §5 |
| F-216 | Twenty-document documentation set | Proposal through feedback, all with Mermaid diagrams and measurable claims | `docs/01` … `docs/20` |
| F-217 | Measured KPIs | Sixteen KPIs with SQL, commands and target-versus-measured tables | `docs/05_kpis.md` |
| F-218 | Health probes for orchestration | Liveness and readiness endpoints consumed by the container health check and the DAG guard | `app/api/routers/health.py` |

---

## Feature count by area

| Area | Features |
| --- | ---: |
| Ingestion and web compliance | 24 |
| Cleaning and normalisation | 29 |
| Duplicate resolution | 17 |
| Warehouse model | 20 |
| ETL pipeline | 15 |
| Change detection | 6 |
| Catalog reconciliation | 7 |
| Data quality | 10 |
| Analytics and SQL reporting | 18 |
| REST API | 26 |
| Security and access control | 10 |
| Dashboard and user experience | 12 |
| Operations, orchestration and DX | 24 |
| Dashboard v1.1 additions | 8 |
| Platform v1.2 additions | 8 |
| Platform v1.3 additions | 37 |
| Platform v1.4 additions | 40 |
| Platform v1.6 additions | 6 |
| Builder Max additions | 22 |
| Account Max additions | 22 |
| Design, mobile and motion Max | 22 |
| Platform and release Max | 20 |
| GUI source onboarding | 7 |
| Catalog import additions | 8 |
| Builder entities + export additions | 4 |
| History + activity export additions | 4 |
| Excel export additions | 2 |
| Proxy + ops additions | 3 |
| Watchlist + personal tracking Max | 9 |
| Export-everywhere Max | 3 |
| Compare + export-all Max | 3 |
| Self-registration Max | 3 |
| Sources + projection export Max | 2 |
| Local runner Max | 1 |
| Export-button sweep Max | 2 |
| **Total** | **454** |

The numbering is continuous from F-001 to F-454 with no duplicate or missing identifier. Counts are measured from the rows themselves by `scripts/project_stats.py`, and each section heading states the same figure, so the three cannot quietly disagree. Sections 14–35 continue below with the same running sequence.

---

## 14. Dashboard v1.1 additions (8)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-219 | Command palette | Ctrl/Cmd-K or "/" opens a searchable palette: screens **and live product results** with prices, plus quick actions (theme toggle, sidebar toggle, sign out); ↑↓/↵/esc keyboard navigation | `frontend/src/components/AppShell.tsx` `CommandPalette` |
| F-220 | JSON exports | One-click JSON download of the dashboard snapshot, product list, analytics bundle and change feed (alongside the existing CSV exports) | `frontend/src/lib/format.ts` `downloadJson` + Dashboard/Products/Analytics/Changes |
| F-221 | RFC-4180 CSV builder | Shared CSV serialiser with proper quoting used by every export button | `frontend/src/lib/format.ts` `toCsv`/`csvCell` |
| F-222 | Installable PWA | Web app manifest, maskable SVG icon, iOS `apple-touch-icon`, safe-area viewport; installable on desktop/Android/iOS | `frontend/public/manifest.webmanifest`, `frontend/index.html` |
| F-223 | Zero-warning quality gates | ESLint runs with `--max-warnings 0`; strict TypeScript compile is part of every build; mirrored in CI | `frontend/package.json`, `.github/workflows/ci.yml` |
| F-224 | GitHub Actions CI | Two jobs (backend: ruff + mypy + pytest; frontend: eslint + tsc + vite build) with artefact upload | `.github/workflows/ci.yml` |
| F-225 | Iconography pass | Every screen action, empty state and navigation item carries a Lucide icon; aria-labels on all icon-only controls | `frontend/src/**` |
| F-226 | Modern slim scrollbars (removed - see F-378) | Thin rounded theme-aware scrollbars app-wide via `scrollbar-width`/`::-webkit-scrollbar` tokens | `frontend/src/styles/index.css` |


---

## 15. Platform v1.2 additions (8)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-227 | Avatar colour picker | Twelve-swatch picker on the profile header; the choice is stored per user and drives the sidebar, account menu and profiles via `avatar_color` | `frontend/src/pages/Account.tsx`, `app/api/schemas.py` `UserUpdate.avatar_color` |
| F-228 | Start-page preference | "Start page after sign-in" select over every permitted screen; stored locally and in server `preferences`, honoured by the login redirect and session restore | `frontend/src/pages/Account.tsx`, `frontend/src/pages/Login.tsx` |
| F-229 | Motion preference | Account-level "reduce motion" override applied before first paint (`data-motion` on `<html>`), complementing the operating-system setting | `frontend/src/lib/theme.ts`, `frontend/src/styles/index.css`, `frontend/index.html` |
| F-230 | Builder column reordering | Arrow buttons move any visible column earlier or later; order persists with the saved view | `frontend/src/pages/Builder.tsx` `moveColumn` |
| F-231 | Builder copy-as-API-request | Copies the composed query as a ready-to-run REST URL with the correct endpoint path and query-string for each entity | `frontend/src/pages/Builder.tsx` `copyApiRequest` |
| F-232 | Builder preview export | CSV and JSON export of the live preview using the visible columns and plain-text mapping per entity | `frontend/src/pages/Builder.tsx` `exportPreview` |
| F-233 | Project infographic generator | Reusable script producing the DEPI 16:9 roadmap slide (SVG master, HTML preview, PNG when cairosvg is installed) straight from the documented facts | `scripts/make_infographic.py`, `docs/assets/infographic.svg` |
| F-234 | Diagram extractor | Extracts every Mermaid block from the documentation set into `docs/diagrams/out/*.mmd` with an index table; optional `mmdc` rendering | `scripts/diagrams.py`, `docs/diagrams/out/index.md` |

missing identifiers) — superseded by section 17 below. Each section heading states its own count, and those counts match the rows
beneath them.
---

## 16. Platform v1.3 additions (37)

| ID | Feature | Description | Where |
| --- | --- | --- | --- |
| F-235 | Feature catalogue module | Single source of truth for platform capabilities: 13 areas, 95 features, each with a Lucide icon name; consumed by the API, the dashboard and the website so they cannot drift | `app/core/features.py` |
| F-236 | Structured feature catalogue endpoint | `GET /meta/features` returns the catalogue with per-group counts and totals; unauthenticated like `/meta` | `app/api/routers/health.py` `meta_features` |
| F-237 | Feature catalogue in `/meta` | `/meta` derives `features` (flat names) and the new `feature_groups` count from the catalogue module instead of a hand-maintained list | `app/api/routers/health.py` |
| F-238 | Feature catalogue screen | New `/features` dashboard screen rendering the catalogue as icon-headed cards with a search box, group chips, copy-to-clipboard per feature and a source-of-truth footer | `frontend/src/pages/Features.tsx` |
| F-239 | Catalogue search and filtering | Live filter over feature names, details and group titles; chip row switches areas; an empty state guides the user to broader terms | `frontend/src/pages/Features.tsx` |
| F-240 | Builder schema endpoint | `GET /builder/schema` publishes 11 entities, their columns with types and groupable flags, 15 operators with value types, and the aggregate list; drives the builder UI | `app/api/routers/builder.py` `schema` |
| F-241 | Aggregate query endpoint | `POST /builder/query` runs a structured read-only query: group-by, six aggregate functions, filters, sort, paging; returns rows, total, duration and the generated SQL | `app/api/routers/builder.py` `run_query` |
| F-242 | Whitelisted identifier SQL assembly | Every identifier reaching the SQL text comes from the server-side `ENTITIES` whitelist; every value is a bind parameter, making injection structurally impossible | `app/api/routers/builder.py` `_build_sql` |
| F-243 | Fifteen filter operators | `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `not_contains`, `starts_with`, `ends_with`, `in`, `not_in`, `between`, `empty`, `not_empty` with per-operator input handling | `app/api/routers/builder.py` `OPERATORS` |
| F-244 | Six aggregate functions | `count`, `count_distinct`, `sum`, `avg`, `min`, `max` with optional aliases and validation (aggregates without a column must be `count`) | `app/api/routers/builder.py` `AGGREGATES` |
| F-245 | Aggregate sort validation | Grouped queries may sort by grouping columns and aggregate aliases only; ungrouped queries by entity columns, preventing invalid `GROUP BY` SQL | `app/api/routers/builder.py` `_validate_sort` |
| F-246 | Aggregate builder mode | The Builder screen gains a "Group & aggregate" mode with dataset, grouping, measure rows (add/remove), advanced filter rows, sort measure, direction and row count | `frontend/src/pages/AggregateBuilder.tsx` |
| F-247 | Aggregate chart preview | Horizontal bar chart of the grouped result with a toggle, truncated to the top 20 groups | `frontend/src/pages/AggregateBuilder.tsx`, `frontend/src/components/charts.tsx` |
| F-248 | Generated SQL preview | Every aggregate run displays the exact SQL the server executed, with values bound as parameters | `frontend/src/pages/AggregateBuilder.tsx` |
| F-249 | Aggregate copy-as-cURL | Copies a ready-to-run `curl` command including the bearer-token header and the JSON body | `frontend/src/pages/AggregateBuilder.tsx` `copyCurl` |
| F-250 | Aggregate export | CSV and JSON export of the aggregated rows, and a JSON bundle containing the composed query alongside the result | `frontend/src/pages/AggregateBuilder.tsx` `exportResult` |
| F-251 | Account data export | `GET /users/me/export` returns a portable JSON snapshot: profile, preferences, API-key metadata (never secrets), saved views, alert rules, notifications and 90 days of activity | `app/api/routers/users.py` `export_me` |
| F-252 | Account self-deletion | `DELETE /users/me` with password confirmation; personal rows cascade via foreign keys, audit history is preserved with the email recorded and the user link nulled | `app/api/routers/users.py` `delete_me` |
| F-253 | Self-deletion audit trail | The deletion writes an `app_audit_log` entry before removing the user, so the event survives the foreign-key `SET NULL` | `app/api/routers/users.py` `delete_me` |
| F-254 | Personal activity feed | `GET /audit/me` returns the caller's own audited actions with paging and a day window — no admin permission needed | `app/api/routers/audit.py` `my_activity` |
| F-255 | Account activity tab | New Account tab listing recent sign-ins, key changes and settings updates with action, target, status, IP and relative time | `frontend/src/pages/Account.tsx` |
| F-256 | Account data & privacy tab | New Account tab with a data-export card and a danger-zone card; deletion requires the password and typing `DELETE` | `frontend/src/pages/Account.tsx` |
| F-257 | Change-event summary service | Lifecycle counters plus the price-change timeline moved out of the router into `analytics.change_event_summary`, reused by the API and the Airflow report task | `app/analytics/service.py` |
| F-258 | Stable scrollbar gutter | `scrollbar-gutter: stable` reserves the rail so content never shifts sideways when a page grows past the viewport | `frontend/src/styles/index.css` |
| F-259 | Refined scrollbar system (removed - see F-378) | Translucent rounded thumbs, a brand-coloured thumb while dragging, slimmer 8px rails inside the sidebar, popovers and code blocks, all theme-aware via `color-mix` | `frontend/src/styles/index.css` |
| F-260 | Scroll containment | `overscroll-behavior: contain` on the shell, sidebar nav, tables and scroll regions so scrolling a panel never drags the page behind it | `frontend/src/styles/index.css` |
| F-261 | Mobile drawer scroll lock | Opening the off-canvas drawer locks background scrolling and restores the previous overflow on close | `frontend/src/components/AppShell.tsx` |
| F-262 | Drawer accessibility | The mobile drawer is exposed as a modal dialog with an accessible name and respects the bottom safe-area inset for notched devices | `frontend/src/components/AppShell.tsx` |
| F-263 | Static project website | A dependency-free landing page (`website/index.html`) with light/dark/system themes applied before first paint, inline SVG icons and no build step | `website/index.html` |
| F-264 | API smoke coverage for v1.3 | The smoke suite grew from 78 to 86 checks, now covering the catalogue, builder schema, aggregate query, rejection of unknown entities, the viewer/analyst builder boundary, account export and personal activity | `scripts/api_smoke.py` |
| F-265 | Analyst coverage in smoke tests | The smoke runner logs in as the analyst as well as the viewer, so role boundaries are exercised for both non-admin roles | `scripts/api_smoke.py` |
| F-266 | Correct API container healthcheck | The compose healthcheck probed `/health` instead of `/api/v1/health`, so the service was permanently reported unhealthy; corrected | `docker-compose.yml` |
| F-267 | Secret hygiene in templates | `.env.example` ships a placeholder service key and documents how to mint a real one; no live credential is committed | `.env.example` |
| F-268 | DAG aggregate + reconciliation work | `build_aggregates` and `reconcile_catalog` perform their real in-process work again (rollup refresh and SKU matching) instead of only reporting state | `dags/product_intelligence_pipeline.py` |
| F-269 | DAG compliance guard restored | The source-compliance guard once again honours per-source `enabled` and `terms_allowed` flags, and the REST fallback validates the registry response it receives | `dags/product_intelligence_pipeline.py` `source_enabled` |
| F-270 | DAG report artifacts | `publish_report` writes a timestamped JSON KPI artifact to `var/reports/`, falling back to the repository root when the Airflow home is read-only | `dags/product_intelligence_pipeline.py` `_write_report_artifact` |
| F-271 | v1.3 regression tests | 19 new tests covering the catalogue, the personal activity feed, account export and deletion, and every builder code path including validation failures | `tests/test_new_features.py` |

---

## 17. Platform v1.4 additions (40)

Integrations (export, webhooks, backfill) and run comparison. Every row ships behind a test.

| F-272 | Dataset export registry | Twelve datasets declared once and served as CSV or JSON with bound filters and a 50,000-row SQL cap | `app/services/exporter.py` `DATASETS` |
| F-273 | Filter-aware export | Every dataset declares its filters; unsupported names and non-boolean flags are rejected with 400 | `app/services/exporter.py` `_build_where` |
| F-274 | Injection-safe identifiers | Exported filter columns must match a strict pattern before reaching SQL | `app/services/exporter.py` `SAFE_IDENTIFIER` |
| F-275 | Portable export search | Free-text search uses `LOWER(col) LIKE`, working on SQLite, PostgreSQL and MySQL alike | `app/services/exporter.py` `_build_where` |
| F-276 | Export catalogue and preview | `GET /export/datasets` lists datasets, formats and caps; `GET /export/{dataset}` previews rows | `app/api/routers/exports.py` |
| F-277 | CSV and JSON serialisers | CSV with a header row and empty cells for nulls; JSON with dataset, timestamp, limits and columns | `app/services/exporter.py` `to_csv`/`to_json` |
| F-278 | Server-generated filenames | Downloads are named `<dataset>-<YYYYMMDD>.<ext>` from the server | `app/services/exporter.py` `filename_for` |
| F-279 | Webhook subscriptions | Per-user outbound subscriptions filtered by event, with wildcard support | `app/services/webhooks.py` `subscriptions_for_event` |
| F-280 | HMAC-SHA256 signing | Payloads signed over `timestamp.body` so receivers can verify authenticity and detect replays | `app/services/webhooks.py` `sign_payload`/`verify_signature` |
| F-281 | Ten pipeline events | `run.completed`, `run.failed`, `run.started`, `dq.failed`, `price.spike`, `product.new`, `product.removed`, `catalog.mismatch`, `alert.triggered`, `backfill.completed` | `app/services/webhooks.py` `WEBHOOK_EVENTS` |
| F-282 | Retry with backoff | Failed deliveries re-attempt after 30s, 5m and 30m up to the subscription's attempt limit | `app/services/webhooks.py` `retry_due` |
| F-283 | Delivery log | Status code, duration, response excerpt, error and attempt count stored per delivery | `app/models/app_users.py` `AppWebhookDelivery` |
| F-284 | Secret rotation | Per-subscription signing secret shown once and rotatable in place | `app/api/routers/webhooks.py` `rotate_secret` |
| F-285 | SSRF-safe targets | Only public http(s) URLs accepted; loopback, private, link-local, metadata and credentialed URLs blocked | `app/services/webhooks.py` `validate_target_url` |
| F-286 | Auto-disable on failure | A subscription disables itself after repeated consecutive failures so it cannot slow the pipeline | `app/services/webhooks.py` `deliver` |
| F-287 | Failure isolation | A broken webhook can never fail the run that emitted the event | `app/services/webhooks.py` `emit` |
| F-288 | Webhooks screen | Create, enable, test, rotate and delete subscriptions; one-time secret reveal; delivery log modal | `frontend/src/pages/Webhooks.tsx` |
| F-289 | Historical backfill | Replay any date range with one run per day, up to 31 days per job | `app/services/backfill.py` `plan_backfill`/`execute_backfill` |
| F-290 | Backfill validation | Reversed ranges, oversized jobs, future dates and unparseable dates are rejected before any run | `app/services/backfill.py` `_as_date` |
| F-291 | Backfill job tracking | Runs tagged `<job id>:<date>`, with roll-up progress and per-day results | `app/services/backfill.py` `backfill_progress`/`list_backfills` |
| F-292 | Day-level isolation | A failing day is recorded and the job continues, so one bad source cannot abandon the range | `app/services/backfill.py` `execute_backfill` |
| F-293 | Run comparison | Diff any two runs: 12 metric deltas, DQ regressions and fixes, catalogue movement, price moves, runtime | `app/analytics/service.py` `compare_runs` |
| F-294 | Compare screen tab | Pick a base and target run; see deltas, quality movement and the largest repricing | `frontend/src/pages/Pipeline.tsx` `RunCompare` |
| F-295 | Shared export button | Reusable CSV/JSON download control that reads its capabilities from the export catalogue | `frontend/src/components/ExportButton.tsx` |
| F-296 | Dependency-free documentation website | `scripts/build_site.py` turns the documentation set into a browsable site with client-side search, system-aware dark mode and 50+ rendered diagrams, using only the standard library — MkDocs would add a large dependency tree for the same result | `scripts/build_site.py` |
| F-297 | GitHub-fidelity heading anchors | `slugify` reproduces `github-slugger` exactly, including the double hyphen an em-dash leaves behind and the one-hyphen-per-space rule, so hand-written in-document anchors resolve in the built site just as they do on GitHub | `scripts/build_site.py` `slugify` |
| F-298 | Anchor regression suite | 24 captured slug cases plus a sweep verifying every hand-written `#anchor` in the README and all documents resolves to a real heading | `scripts/check_slugify.py` |
| F-299 | Mermaid syntax gate | Every diagram is extracted and parsed before merge, turning a broken diagram from a silent rendering error into a build failure; it caught two real defects — a semicolon in a sequence message and a self-parenting edge | `scripts/diagrams.py` |
| F-300 | Internal link and anchor checker | Validates that every generated page link, in-page anchor, image reference and static asset resolves, and that no control characters survive Markdown conversion | `scripts/check_links.py` |
| F-301 | Security policy and threat model | Boundary-by-boundary control table covering web-to-ingestion, user-to-API and API-to-warehouse threats, with disclosure targets and the commands that verify each claim | `SECURITY.md` |
| F-302 | Contributor Covenant | Community health standards with a four-tier enforcement ladder | `.github/CODE_OF_CONDUCT.md` |
| F-303 | Structured issue and pull request forms | Bug, feature and documentation forms plus a PR template carrying repository-specific reminders — robots enforcement, parameterised SQL, cross-dialect parity — and a verification section asking for pasted output | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` |
| F-304 | Automated dependency updates | Weekly pull requests for pip, npm and GitHub Actions, grouped by ecosystem | `.github/dependabot.yml` |
| F-305 | Documentation CI job | A dedicated job validates all diagrams, extracts them, fails on a stale extraction, builds the site and checks its links — the documentation can no longer rot unnoticed | `.github/workflows/ci.yml` `docs` |
| F-306 | Review ownership | Explicit code ownership so every change has a named reviewer | `.github/CODEOWNERS` |
| F-307 | Measurement provenance | The README and docs index state which figures are structural and re-verifiable and which are measurements that vary with data volume and hardware, so a number is never presented as a constant when it is not one | `README.md`, `docs/README.md` |
| F-308 | Architecture rationale with rejected alternatives | Every significant decision records what was chosen, what was rejected, why, and the measured consequence — including the 29× reconciliation optimisation that preserved identical output | `docs/21_architecture_deep_dive.md` |
| F-309 | Complete data dictionary | All 23 tables with every column, type, nullability and meaning, plus controlled vocabularies, magnitude bands, the view catalogue and a dialect-portability table | `docs/22_data_dictionary.md` |
| F-310 | Glossary and FAQ | Defined terms and questions across setup, the pipeline, data quality, security and development — including how to add a source in six steps | `docs/23_glossary_and_faq.md` |
| F-311 | Demo runbook | Screen-by-screen live demo script with exact URLs, the sentence worth saying at each step, time-boxed 3/5/8-minute variants, a pre-flight checklist, the five questions that always get asked, and a failure playbook that falls back to `curl` when the browser dies | `docs/24_demo_runbook.md` |

**Final total: 295 features across 17 areas** (F-001 to F-295). Section 17 adds the
export, webhook, backfill and run-comparison capabilities shipped in v1.4.

**Revised total at F-311: 311 features across 17 areas**, contiguous with no duplicate or missing identifier. Later sections continue the same sequence; the count table above carries the current totals.

---

## 18. Platform v1.6 additions (6)

Navigation discoverability, flash-free appearance and generated artefacts with drift gates.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-312 | Header collapse control | Collapse or expand the sidebar rail from the top bar, with the state shared across tabs | `frontend/src/components/AppShell.tsx` |
| F-313 | Shortcut reference dialog | Press `?` anywhere for every shortcut on one screen, also reachable from the command palette | `frontend/src/components/AppShell.tsx` `ShortcutsDialog` |
| F-314 | Accent pre-paint | The accent palette resolves before first paint, so reload never flashes the default colour | `frontend/index.html` `frontend/src/lib/theme.ts` |
| F-315 | Infographic freshness gate | `make_infographic.py --check` fails when the committed SVG differs from the generator | `scripts/make_infographic.py` |
| F-316 | Presentation deck generator | `make deck` builds a 12-slide PDF from measured counts in the DEPI palette | `scripts/make_deck.py` `make deck` |
| F-317 | Deck freshness gate | `make_deck.py --check` fails when the committed HTML differs from the generator | `scripts/make_deck.py` |

## 19. Builder Max additions (22)

Self-service analytics without raw SQL.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-318 | 11 builder entities | products, price_changes, new/removed, category_index, brand_summary, source_coverage, top_movers, availability, quality_latest, catalog_reconciliation | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-319 | Rows mode filters | search, category, brand, source, availability, price/rating/change ranges, in-stock, significant-only | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-320 | 15 filter operators | eq, ne, gt, gte, lt, lte, contains, not_contains, starts/ends_with, in, not_in, between, empty, not_empty | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-321 | 6 aggregate functions | count, count_distinct, sum, avg, min, max with up to 8 measures per query | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-322 | Group-by + having | Server-side grouping with aggregate-aware ordering and result capping | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-323 | Whitelist-assembled SQL | Entity/column whitelist plus bind parameters — structurally incapable of injection | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-324 | Live SQL preview | POST /builder/query returns sql_preview beside columns, rows and duration_ms | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-325 | cURL copy button | One click copies an authenticated curl for the exact builder state | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-326 | Chart preview | Bar chart renders the first grouped measure instantly | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-327 | Saved views | Name any builder state, reuse it from Products/Changes screens, usage-counted | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-328 | View sharing scope | Private views plus usage counts; admin can audit all views | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-329 | CSV export | builder-{entity}.csv generated client-side from visible columns | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-330 | JSON export | Same rows as JSON with entity plus applied filters envelope | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-331 | Column picker | Per-entity column sets with sticky, sortable headers | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-332 | Sort everywhere | asc/desc on any whitelisted column, default sort per entity | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-333 | Pagination control | Page-size selector persisted to profile, total + duration shown | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-334 | Debounced search | 300ms debounce so typing never hammers the API | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-335 | Stale-while-revalidate | Cached preview first, silent refetch, no spinners on revisit | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-336 | Join guidance | Cross-entity recipes (products x changes x catalog) documented with example SQL | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-337 | Builder schema endpoint | GET /builder/schema drives entity/column/operator pickers — no hardcoded lists | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-338 | Error envelope | Unknown entity/column returns {error,message,details.available} with 422 | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |
| F-339 | Builder docs page | docs plus QueryLab examples mirror the same whitelist | `app/api/routers/builder.py` `frontend/src/pages/Builder.tsx` |

## 20. Account Max additions (22)

Nine tabs of self-service control.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-340 | 9 account tabs | Profile, Appearance, Security, Devices & 2FA, API keys, Alerts, Activity, Data & privacy, Preferences | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-341 | Avatar picker | 12 theme-aware colours with initials fallback, shown in topbar and sidebar | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-342 | Full-name editing | Validated, audited, reflected in JWT display name immediately | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-343 | Password strength meter | Length, variety and breach-hint feedback before submit | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-344 | Rows-per-page control | Persisted default page size used by every table screen | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-345 | Default landing page | Choose Dashboard, Analytics, Products or Pipeline as post-login route | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-346 | Weekly digest toggle | Opt in to Monday price-movement summary via notifications channel | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-347 | Alert threshold slider | Per-user % movement that raises a notification, default 5% | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-348 | Keyboard shortcut reference | Press ? anywhere: palette, sidebar, rail, overlay shortcuts on one screen | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-349 | Session timeout display | Idle and absolute lifetimes visible beside each device row | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-350 | Sign out everywhere | One call revokes every refresh token except the current session | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-351 | Recovery code download | One-click .txt export at enrol time, hashed at rest, single-use | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-352 | API key scopes UI | read/query/run/admin checkboxes capped by owner role, shown per key | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-353 | Key last-used display | Relative time plus total calls — leaked credentials get noticed | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-354 | Personal activity feed | GET /audit/me powers the Activity tab with IP and user-agent | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-355 | Portable data export | GET /users/me/export downloads profile, prefs, keys metadata and activity as JSON | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-356 | Danger-zone confirm | DELETE /users/me needs password, cascades, writes audit, signs out | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-357 | Alert rules inline | Create, pause and test alert rules without leaving Account | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-358 | Preference sync | Appearance plus prefs saved server-side, inherited by new devices | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-359 | Cross-tab live sync | storage event keeps two open tabs visually identical | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-360 | Accessible forms | Labels, focus rings, ARIA descriptions and keyboard-only operation | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |
| F-361 | Toast confirmations | Every mutation confirms with undo hint where safe | `frontend/src/pages/Account.tsx` `frontend/src/components/AccountPanels.tsx` |

## 21. Design, mobile and motion Max (22)

Perfect white and dark, silent reloads, mobile.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-362 | Perfect white mode | Warm paper surfaces, indigo brand ramp, AAA body text on white | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-363 | Perfect dark mode | Navy surfaces, lifted borders, recoloured charts with zero pure-black crush | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-364 | Midnight OLED theme | True-black surfaces for phones and OLED laptops | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-365 | High-contrast theme | 2px borders, 3px focus rings, AAA text in both bases | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-366 | System follows OS | prefers-color-scheme resolved through the same path, no forced light | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-367 | No flash on reload | Inline pre-paint script resolves theme plus accent before React mounts | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-368 | 12 accent colours | Indigo to violet applied via CSS vars without a rebuild | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-369 | 3 densities + 5 font scales | Compact/comfortable/spacious independent of 13–19px text | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-370 | 3 motion levels | Full/reduced/none; none also stops spinners and progress bars | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-371 | Silent reload policy | No route transitions, no smooth scroll, 120ms functional transitions only | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-372 | Scroll restoration | Back restores offset, forward starts at top, focus moves to h1 | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-373 | Three-state sidebar | Expanded, icon rail, off-canvas drawer; choice shared across tabs. Floating rounded card; content reserves its width | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` `frontend/src/components/Navigation.tsx` |
| F-374 | Phone bottom tab bar | Five primary destinations under 640px with safe-area padding | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-375 | Card-view tables | Dense tables become stacked cards below 640px — no horizontal blowout | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-376 | Drawer scroll lock | Body locked while drawer/modal open, focus trapped, Esc closes | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-377 | Lucide icons everywhere | Nav, tabs, stats, empty states and toasts — no emoji, aria-hidden decorative | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-378 | No scrollbars | Removed everywhere via scrollbar-width:none + webkit display:none; shadows carry position | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-379 | Scroll shadows | Top/bottom fades driven by scrollTop vs scrollHeight via data-scroll-shadow | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-380 | No scroll chaining | overscroll-behavior:contain on main, nav, table-wrap and scroll areas | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-381 | Stable gutter | scrollbar-gutter:stable stops sideways jumps when pages grow | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-382 | PWA installable | Manifest, maskable icons, offline fallback, safe-area viewport from 320px | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |
| F-383 | Command palette | Ctrl/Cmd-K or /: screens, live products and actions with full keyboard nav | `frontend/src/styles/index.css` `frontend/src/components/AppShell.tsx` |

## 22. Platform and release Max (20)

Free unlimited operations and releases.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-384 | 44 Make targets | make everything/check/up/bootstrap/demo/analysis/deck/verify-dialects and more | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-385 | One-command everything | install, env, databases, schema, demo data, pipeline, tests, frontend build | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-386 | Single canonical version | VERSION feeds API, CLI, pyproject and dashboard via sync_version.py | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-387 | Stats sync gate | project_stats.py rewrites README block; check_stats.py fails CI on drift | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-388 | 30 numbered docs | Proposal through access-control, each with purpose plus Mermaid | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-389 | 80 Mermaid diagrams | Context, stack, sequences, DAG, ER, DFD, deployment — rendered to SVG | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-390 | Infographic 2560x1440 | One 16:9 DEPI Data Engineering slide, freshness-gated by generator | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-391 | 12-slide deck | make deck builds PDF from measured counts in the DEPI palette | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-392 | Multi-section website | Hero, features from live OpenAPI, docs, quickstart, About — light/dark/system | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-393 | SEO + OG tags | Description, og:title/description/type, color-scheme, favicon | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-394 | Private-by-default repo | gh repo edit --private; secrets never committed, .env.example only | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-395 | Topic taxonomy | etl, airflow, fastapi, react, postgres, mysql, data-quality, scraping, warehouse, dashboard | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-396 | Release notes | Tag v1.x with changelog, counts, demo accounts and verify steps | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-397 | 4-job CI | backend, databases PG+MySQL, api-smoke, frontend type+lint+build | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-398 | 6-service Compose | api, postgres, mysql, airflow webserver/scheduler, frontend nginx with /api proxy | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-399 | Nginx frontend | Static build plus API proxy, gzip, cache headers | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-400 | Health probes | Liveness plus real DB readiness used by Compose and Airflow | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-401 | Structured logs | structlog with run_id, stage, duration and slow-request warnings | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-402 | Timing headers | X-Process-Time-Ms plus X-Database on every response | `Makefile` `scripts/project_stats.py` `website/index.html` |
| F-403 | Free forever stack | No paid APIs: offline FX, seeded demo, SQLite-runnable tests | `Makefile` `scripts/project_stats.py` `website/index.html` |

---

## 23. GUI source onboarding (7)

Add a JSON feed from the dashboard, with compliance proven before anything is saved.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-404 | Add-source dialog | Name, code, endpoint, mapping and politeness on the Sources screen | `frontend/src/pages/Sources.tsx` |
| F-405 | Endpoint presets | DummyJSON, FakeStore, Shopify, Open Food Facts, Open Library in one click | `app/ingestion/sources/generic_json.py` `PRESETS` |
| F-406 | Compliance pre-check | SSRF guard plus a live robots.txt verdict before saving | `app/api/routers/sources.py` `POST /sources/check` |
| F-407 | JSON shape sniff | One bounded GET reports item keys and counts for the mapping | `app/api/routers/sources.py` `_sniff_shape` |
| F-408 | Generic JSON adapter | Dot-path fields, three pagination styles, URL templates | `app/ingestion/sources/generic_json.py` |
| F-409 | Dynamic resolution | Registry first, dashboard rows second; pipeline auto-selects enabled rows | `app/ingestion/dynamic.py` `app/etl/pipeline.py` |
| F-410 | Source lifecycle controls | Enable, disable, history-guarded delete; bundled rows read-only | `frontend/src/pages/Sources.tsx` `app/api/routers/sources.py` |

**Revised total: 410 features across 23 areas** (F-001 to F-410 at this checkpoint; the running total continues below).

## 24. Catalog import additions (8)

Bulk-load the internal catalog from any spreadsheet, with the same validation the API enforces.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-411 | CSV catalog import | Bulk upsert of 5,000 SKUs per file keyed by sku | `app/api/routers/catalog.py` `POST /catalog/import` |
| F-412 | Import CSV template | Header plus two example rows downloadable for spreadsheets | `app/api/routers/catalog.py` `GET /catalog/template` |
| F-413 | Row-level import validation | Required sku/name, 3-letter currency, status vocabulary, non-negative prices | `app/api/routers/catalog.py` `_parse_optional_*` |
| F-414 | All-or-nothing import | Any invalid row rejects the file with the first 50 errors listed | `app/api/routers/catalog.py` `import_products` |
| F-415 | Import size caps | 5 MB file cap and 5,000-row cap enforced before any write | `app/api/routers/catalog.py` `IMPORT_MAX_*` |
| F-416 | Import audit entry | catalog.import with created/updated counts, file name and actor | `app/models/app_users.py` `AppAuditLog` |
| F-417 | Catalog upload UI | Template + Import CSV buttons on the SKUs tab with toasts and refresh | `frontend/src/pages/Catalog.tsx` `uploadCatalogCsv` |
| F-418 | Import permission gate | Analyst/admin may import; viewers refused server-side with 403 | `app/api/deps.py` `WriteUser` `tests/test_catalog_import.py` |

**Revised total: 418 features across 24 areas** (F-001 to F-418).

## 25. Builder entities + export additions (4)

Two more self-service entities and a closed import/export loop for the catalog.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-419 | Pipeline-runs builder entity | Group and aggregate etl_run: status, trigger, counters, DQ score | `app/api/routers/builder.py` `pipeline_runs` |
| F-420 | Alert-rules builder entity | Group and aggregate app_alert_rule: metric, channel, trigger counts | `app/api/routers/builder.py` `alert_rules` |
| F-421 | CSV catalog export | Every SKU in import-compatible columns, 10k cap, dated filename | `app/api/routers/catalog.py` `GET /catalog/export.csv` |
| F-422 | Export button on Catalog | One-click download beside Template and Import with toasts | `frontend/src/pages/Catalog.tsx` `downloadBinary` |

**Revised total: 422 features across 25 areas** (F-001 to F-422).

## 26. History + activity export additions (4)

Every personal and product-level dataset leaves the app as a file, not just the warehouse exports.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-423 | Per-product history CSV | Every snapshot with USD prices and changes, 5k cap, dated filename | `app/api/routers/products.py` `GET /products/{id}/history.csv` |
| F-424 | Named file downloads | Content-Disposition filenames on CSV, PDF and template exports | `app/api/routers/products.py` `app/api/routers/catalog.py` |
| F-425 | History Export button | One-click CSV on the product page snapshots tab | `frontend/src/pages/ProductDetail.tsx` `downloadBinary` |
| F-426 | Activity CSV export | Account feed to CSV with the table columns, toast confirmation | `frontend/src/pages/Account.tsx` `downloadCsv` |

**Revised total: 426 features across 26 areas** (F-001 to F-426).

## 27. Excel export additions (2)

Native spreadsheets for every dataset, alongside CSV and JSON.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-427 | Excel (.xlsx) dataset downloads | Native dates/decimals, bold header, freeze panes, autofilter, 10k naming | `app/services/exporter.py` `to_xlsx` `GET /export/{dataset}.xlsx` |
| F-428 | Export format picker | CSV, Excel and JSON from one button on every dataset screen | `frontend/src/components/ExportButton.tsx` `downloadExport` |

**Revised total: 428 features across 27 areas** (F-001 to F-428).

## 28. Proxy + ops additions (3)

Egress control for restricted networks plus commit-time and backup safety nets.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-429 | Egress proxy support | Optional INGEST_PROXY_URL with INGEST_NO_PROXY bypass, validated http(s) only | `app/core/config.py` `app/ingestion/http_client.py` `resolve_proxy` |
| F-430 | Pre-commit hooks | Ruff, whitespace and the stats drift gate at commit time | `.pre-commit-config.yaml` `make precommit` |
| F-431 | One-command backup | Timestamped pg_dump, mysqldump and sqlite copies via make backup | `scripts/backup.sh` `Makefile` |

**Revised total: 431 features across 28 areas** (F-001 to F-431).

## 29. Watchlist + personal tracking Max (9)

Star products into a migration-free personal watchlist, plus compliance-log export and dark presentation artefacts.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-432 | Migration-free watchlist | Stored in profile preferences JSON: no schema change, syncs per device | `app/api/routers/users.py` `WATCHLIST_KEY` |
| F-433 | Watchlist API trio | GET plus idempotent POST and DELETE per product id | `app/api/routers/users.py` `/me/watchlist` |
| F-434 | Star column on Products | One-click star per row with filled state, toasts and live count | `frontend/src/pages/Products.tsx` `toggleWatch` |
| F-435 | Watched-only filter | Toolbar toggle narrows to starred products with own empty state | `frontend/src/pages/Products.tsx` `watchedOnly` |
| F-436 | Watch button on detail | Header Watch/Watched toggle with instant feedback | `frontend/src/pages/ProductDetail.tsx` `toggleWatch` |
| F-437 | Live product summaries | Ids resolved against vw_product_current with price/rating/stock | `app/api/routers/users.py` `_watchlist_products` |
| F-438 | 200-item cap + validation | Unknown ids 404, malformed skipped, oldest trimmed past cap | `app/api/routers/users.py` `WATCHLIST_MAX_ITEMS` |
| F-439 | HTTP-log CSV export | One-click CSV of compliance log with robots/cache/timing columns | `frontend/src/pages/Audit.tsx` `http-compliance-log.csv` |
| F-440 | Dark infographic artefacts | 2560x1440 dark SVG plus PNG and PDF, freshness-gated | `docs/assets/infographic-dark.svg` `scripts/make_infographic.py` |

**Revised total: 440 features across 29 areas** (F-001 to F-440).

## 30. Export-everywhere Max (3)

Every remaining table leaves the app as a file, and filtered views export what is shown.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-441 | Audit-trail CSV export | Application audit tab to CSV with user, action and timing columns | `frontend/src/pages/Audit.tsx` `application-audit-log.csv` |
| F-442 | Backtest CSV export | Forecast accuracy to CSV with MAPE, MAE and RMSE per product | `frontend/src/pages/Forecast.tsx` `forecast-backtest.csv` |
| F-443 | Watchlist-aware product export | Products CSV/JSON follows the Watched filter with watchlist filenames | `frontend/src/pages/Products.tsx` `displayRows` |

**Revised total: 443 features across 30 areas** (F-001 to F-443).

## 31. Compare + export-all Max (3)

Compare across pages and export beyond the visible page, with one-click watchlist reset.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-444 | Side-by-side product comparison | Up to 4 products in a live server-side attribute matrix modal | `frontend/src/pages/Products.tsx` `GET /products/compare/ids` |
| F-445 | Server-side full export | Export-all downloads every filtered product via /export/products.csv | `frontend/src/pages/Products.tsx` `downloadExport` |
| F-446 | One-click watchlist clear | Clear button plus DELETE /users/me/watchlist with removed count | `app/api/routers/users.py` `clear_watchlist` |

**Revised total: 446 features across 31 areas** (F-001 to F-446).

## 32. Self-registration Max (3)

Public sign-up with server-enforced roles, a deployment kill-switch and a matching Login mode.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-447 | Public self-registration | POST /auth/register creates a viewer and returns tokens; 409 on duplicates | `app/api/routers/auth.py` `register` |
| F-448 | Registration kill-switch | REGISTRATION_ENABLED=false refuses sign-ups with 403, covered by a dedicated test | `app/core/config.py` `registration_enabled` |
| F-449 | Create-account screen | Sign-in / sign-up switch on Login with full-name validation and instant sign-in | `frontend/src/pages/Login.tsx` `useAuth.register` |

**Revised total: 449 features across 32 areas** (F-001 to F-449).

## 33. Sources + projection export Max (2)

The last two screens without a download get one: sources coverage and per-product projections.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-450 | Sources ExportButton | CSV, Excel and JSON of the source coverage dataset on the Sources screen | `frontend/src/pages/Sources.tsx` `ExportButton` |
| F-451 | Projection CSV export | Per-product forecast points with confidence bounds from the projection card | `frontend/src/pages/Forecast.tsx` `forecast-product-*.csv` |

**Revised total: 451 features across 33 areas** (F-001 to F-451).

## 34. Local runner Max (1)

One command to run everything locally, hardened for real machines.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-452 | Hardened run-local.sh | Version-gated preflight, foreign port-conflict guard, no-rebuild re-runs, logs/status/open actions, Airflow check | `run-local.sh` |

**Revised total: 452 features across 34 areas** (F-001 to F-452).

## 35. Export-button sweep Max (2)

The last two toolbars without a download get one: alerts and run history.

| ID | Feature | What it does | Where |
| --- | --- | --- | --- |
| F-453 | Alerts ExportButton | CSV, Excel and JSON of every alert rule on the Alerts toolbar | `frontend/src/pages/Alerts.tsx` `ExportButton` |
| F-454 | Runs ExportButton | CSV, Excel and JSON of run history beside the status filter | `frontend/src/pages/Pipeline.tsx` `ExportButton` |

**Revised total: 454 features across 35 areas** (F-001 to F-454).
