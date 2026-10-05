# 19 — Feature Inventory

## Purpose

This document is the complete feature inventory of the Web-to-Warehouse Product Intelligence
Pipeline: 271 features grouped into sixteen areas, each with a one-line description and a reference
to the file that implements it. Every entry corresponds to shipped behaviour — a function, a table, an
endpoint, a CLI command or a documented design decision. Nothing here is aspirational.

**Scale of the system, measured:** 5 ingestion sources · 23 physical tables · 20 analytical views ·
12 data-quality rules across 6 dimensions · 113 REST route decorators (110 documented in OpenAPI plus
3 internal probes) in 16 routers · 9 pipeline stages · 14 Airflow tasks · 12 CLI commands · 30+ Makefile
targets · 6 Docker Compose services · 20 documentation documents · 255 automated tests ·
86 end-to-end API smoke checks.

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
13. [Operations, orchestration and DX (23)](#13-operations-orchestration-and-dx-23)

Platform increments: [v1.1 (8)](#14-dashboard-v11-additions-8) ·
[v1.2 (8)](#15-platform-v12-additions-8) · [v1.3 (34)](#16-platform-v13-additions-34)

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

## 4. Warehouse model (18)

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

## 9. Analytics and SQL reporting (16)

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

## 10. REST API (23)

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

## 13. Operations, orchestration and DX (23)

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
| --- | --- |
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
| **Total** | **218** |

The numbering is continuous from F-001 to F-218; the counts above reflect features that are
independently demonstrable (a function, an endpoint, a table, a command or a documented design
decision) rather than individual lines of code.

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
| F-226 | Modern slim scrollbars | Thin rounded theme-aware scrollbars app-wide via `scrollbar-width`/`::-webkit-scrollbar` tokens | `frontend/src/styles/index.css` |

**Revised total: 226 features.**

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
| F-234 | Diagram extractor | Extracts every Mermaid block from the documentation set into `docs/diagrams/out/*.mmd` with an index table; optional `mmdc` rendering | `scripts/render_diagrams.sh`, `docs/diagrams/out/index.md` |

**Revised total: 234 features.**
---

## 16. Platform v1.3 additions (34)

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
| F-259 | Refined scrollbar system | Translucent rounded thumbs, a brand-coloured thumb while dragging, slimmer 8px rails inside the sidebar, popovers and code blocks, all theme-aware via `color-mix` | `frontend/src/styles/index.css` |
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

**Revised total: 271 features.**
