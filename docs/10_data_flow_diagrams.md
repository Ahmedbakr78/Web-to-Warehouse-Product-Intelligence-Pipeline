# 10 — Data Flow Diagrams

## Purpose

This document describes how data moves through the Web-to-Warehouse Product Intelligence Pipeline.
It contains a context-level (level 0) diagram, a level-1 diagram of the whole system, three level-2
diagrams for the ingestion, transformation and serving processes, and a data dictionary that defines
every data flow and data store by name.

**Notation.** External entities are rectangles, processes are labelled rectangles with a number,
data stores are labelled cylinders, and every arrow is named with the flow it carries. This follows
the classic Gane-Sarson notation as refined in modern practice.

---

## Table of contents

1. [Level 0 — Context diagram](#1-level-0--context-diagram)
2. [Level 1 — System overview](#2-level-1--system-overview)
3. [Level 2a — Ingestion and compliance](#3-level-2a--ingestion-and-compliance)
4. [Level 2b — Preparation, resolution and loading](#4-level-2b--preparation-resolution-and-loading)
5. [Level 2c — Analytics, quality and serving](#5-level-2c--analytics-quality-and-serving)
6. [Data dictionary](#6-data-dictionary)
7. [Data store dictionary](#7-data-store-dictionary)
8. [Control flows](#8-control-flows)

---

## 1. Level 0 — Context diagram

The whole system is a single process. It receives product information from permitted sources and
run instructions from operators, and it produces warehouse content, analytical answers, compliance
evidence and notifications.

```mermaid
flowchart LR
    SRC["External entity 1<br/>Permitted web sources<br/>APIs and sandbox website"]
    OPS["External entity 2<br/>Operators<br/>Data platform lead and scheduler"]
    ANA["External entity 3<br/>Analysts and managers<br/>Dashboard and API consumers"]
    CMP["External entity 4<br/>Compliance officer<br/>Auditor"]

    P0(["Process 0<br/>Web-to-Warehouse Product Intelligence Pipeline"])

    SRC -->|"raw product payloads<br/>HTML and JSON"| P0
    OPS -->|"run configuration<br/>sources, limits, schedule, credentials"| P0
    P0 -->|"refreshed product and price history<br/>analytical answers, alerts, compliance report"| ANA
    P0 -->|"audit evidence<br/>request log, robots decisions, DQ verdicts"| CMP
    ANA -->|"feedback<br/>filters, saved views, alert rules"| P0
    P0 -->|"warnings and run status"| OPS
```

| Flow | Direction | Composition |
| --- | --- | --- |
| Raw product payloads | In | HTML pages, JSON documents, synthetic records |
| Run configuration | In | Source codes, per-source limit, strictness, schedule, database target |
| Analytical answers | Out | Product list/detail, price history, change feeds, leaderboards, SQL results |
| Compliance report | Out | Request counts, robots decisions, cache and retry statistics |
| Warnings and run status | Out | Per-run counters, DQ score, reconciliation summary |
| Feedback | In | Saved views, alert thresholds, manual triggers |

---

## 2. Level 1 — System overview

Six processes, eight data stores. The pipeline is a **closed-loop** system: it writes back into
source metadata (run statistics, sync state) which then influences the next run.

```mermaid
flowchart TB
    SRC["External<br/>Permitted sources"]
    OP["External<br/>Operators and scheduler"]
    USR["External<br/>Analysts, managers,<br/>administrators"]

    subgraph L1["Level 1 processes"]
        P1["1. Collect<br/>robots gate, rate limit,<br/>cache, retry, audit"]
        P2["2. Stage<br/>raw landing zone"]
        P3["3. Prepare<br/>clean, normalise, price"]
        P4["4. Resolve<br/>block and match duplicates"]
        P5["5. Load and analyse<br/>snapshots, changes, aggregates,<br/>catalog reconciliation"]
        P6["6. Measure and serve<br/>DQ rules, analytics, REST API,<br/>dashboard"]
    end

    D1[("D1 stg_raw_observation<br/>raw payloads")]
    D2[("D2 dim_product<br/>canonical products")]
    D3[("D3 fact_price_snapshot<br/>price history")]
    D4[("D4 chg_price_change<br/>chg_product_event")]
    D5[("D5 fact_catalog_snapshot<br/>catalog comparison")]
    D6[("D6 agg_category_daily<br/>category rollup")]
    D7[("D7 etl_run, dq_rule_result,<br/>ingestion_http_log, sync_state")]
    D8[("D8 app_user, app_saved_view,<br/>app_alert_rule, app_notification,<br/>app_audit_log, app_setting")]

    SRC -->|"HTML / JSON / synthetic"| P1
    OP -->|"run configuration"| P1
    P1 -->|"raw records"| P2
    P2 -->|"staged rows"| D1
    D1 -->|"raw payloads"| P3
    P3 -->|"normalised records"| P4
    D2 -->|"existing products"| P4
    P4 -->|"canonical product"| P5
    D2 -->|"product dimension"| P5
    P5 -->|"snapshots"| D3
    P5 -->|"change events"| D4
    P5 -->|"category rollup"| D6
    P5 -->|"reconciliation rows"| D5
    D5 -->|"catalog products"| P5
    P5 -->|"counts and timings"| D7
    P1 -->|"request audit"| D7
    P5 -->|"warehouse content"| P6
    D3 --> P6
    D4 --> P6
    D5 --> P6
    D6 --> P6
    D7 --> P6
    D8 <-->|"identity, preferences, alerts"| P6
    P6 -->|"answers, charts, exports"| USR
    USR -->|"triggers, filters, alert rules"| P6
    P6 -->|"notifications"| D8
    P6 -->|"run status and DQ score"| OP
    D7 -->|"source statistics and cursors"| P1
```

### 2.1 Process dictionary (level 1)

| # | Process | Input flows | Output flows | Code |
| --- | --- | --- | --- | --- |
| 1 | Collect | Raw payloads, run configuration | Raw records, request audit, source statistics | `app/ingestion/http_client.py`, `sources/*` |
| 2 | Stage | Raw records | Staged rows with payload hash and status | `WarehouseLoader.stage()` |
| 3 | Prepare | Staged rows | Normalised records with flags, USD price, fingerprint | `app/ingestion/cleaning.py`, `transform_product()` |
| 4 | Resolve | Normalised records, existing products | Match result, canonical product | `app/ingestion/dedupe.py` |
| 5 | Load and analyse | Canonical product, normalised record | Snapshots, changes, aggregates, reconciliation, run counters | `app/etl/loader.py`, `app/etl/catalog_reconcile.py` |
| 6 | Measure and serve | Warehouse content, user identity, preferences | DQ verdicts, analytical answers, notifications, alerts | `app/etl/dq.py`, `app/analytics/service.py`, `app/api/` |

---

## 3. Level 2a — Ingestion and compliance

```mermaid
flowchart TB
    WEB["Upstream host<br/>robots.txt and pages"]
    SCH["Scheduler / operator"]

    subgraph P1A["1a Extract"]
        A1["Get robots.txt<br/>robots.py cache"]
        A2["Decide allow or deny<br/>RFC 9309 fallback"]
        A3["Acquire token<br/>ratelimit.py"]
        A4["Fetch with retry<br/>http_client.py"]
        A5["Serve from disk cache<br/>TTL 1800 s"]
        A6["Parse HTML or JSON<br/>source adapter"]
    end

    AUD[("ingestion_http_log<br/>audit")]
    SYNC[("sync_state<br/>cursors and health")]
    DIMS[("dim_source<br/>reliability stats")]
    RAW[("D1 staging zone")]

    WEB -->|"robots.txt"| A1
    A1 --> A2
    A2 -->|"allow"| A3
    A3 --> A4
    A4 -->|"cache hit"| A5
    A5 --> A6
    A4 -->|"network response"| A6
    A2 -->|"deny: ComplianceError"| AUD
    A4 -->|"status, latency, bytes, retries"| AUD
    A4 -->|"429 or 5xx"| A3
    A6 --> SCH
    A6 --> RAW
    SCH --> SYNC
    SCH --> DIMS
    AUD --> SCH
```

| Flow | Meaning |
| --- | --- |
| `robots.txt` | Requested once per host per TTL with the crawler's user-agent |
| allow / deny | `RobotsDecision(allowed, rule, crawl_delay, user_agent_matched)` |
| `Crawl-delay` | Applied to the rate limiter; the limiter uses the slowest constraint |
| Fetch with retry | Up to `MAX_RETRIES` retries with exponential back-off; 429/5xx penalise the host |
| Cache hit | A stored response within TTL is served without touching the network |
| Audit row | Written for **every** attempt, including refusals |
| Source statistics | `total_runs`, `success_rate_pct`, `avg_duration_seconds` updated per run |
| Sync state | `last_run_id`, `consecutive_failures`, `status` used for health reporting |

**Compliance invariants:** no request without a robots decision; no write statement; no write to any
store except the audit table, the cache directory and the staging zone.

---

## 4. Level 2b — Preparation, resolution and loading

```mermaid
flowchart TB
    RAW[("D1 staging zone<br/>raw payloads")]

    subgraph P3["3 Prepare"]
        C1["Unicode fold and<br/>promo-noise removal"]
        C2["Category synonym<br/>mapping and hierarchy"]
        C3["Price and currency parse<br/>then USD conversion"]
        C4["Rating rescale to 0-5<br/>availability mapping"]
        C5["Quality flags<br/>and reject reasons"]
        F1["Fingerprint<br/>SHA-1 of name and brand"]
        K1["Blocking key<br/>first 4 characters"]
    end

    subgraph P4["4 Resolve"]
        B1["Exact fingerprint<br/>match"]
        B2["Normalised-name<br/>equality"]
        B3["Blocking candidate<br/>retrieval max 25"]
        B4["Blended similarity<br/>token-set, Jaro-Winkler,<br/>trigram, Levenshtein"]
        B5["Digit-signature<br/>guard and brand term"]
        B6["Decision<br/>threshold 0.90"]
    end

    subgraph P5["5 Load and analyse"]
        L1["Upsert dimension<br/>dim_product, dim_category"]
        L2["Append snapshot<br/>fact_price_snapshot"]
        L3["Emit price change<br/>chg_price_change"]
        L4["Emit lifecycle event<br/>chg_product_event"]
        L5["Detect removals<br/>7-day staleness"]
        L6["Refresh category<br/>aggregate"]
        L7["Reconcile catalog<br/>and compute price gaps"]
    end

    DP[("D2 dim_product")]
    DS[("D3 fact_price_snapshot")]
    DC[("D4 change feeds")]
    DA[("D6 aggregate")]
    DK[("D5 catalog comparison")]
    ERR[("staging rejection<br/>is_valid, reject_reason")]

    RAW --> C1 --> C2 --> C3 --> C4 --> C5
    C5 --> F1
    C5 --> K1
    F1 --> B1
    K1 --> B3
    B1 --> B6
    B2 --> B6
    B3 --> B4 --> B5 --> B6
    DP --> B2
    DP --> B3
    B6 --> L1
    C5 --> L1
    DP --> L1
    L1 --> L2
    DP -->|"previous snapshot"| L2
    L2 --> DS
    L2 --> L3
    L2 --> L4
    L3 --> DC
    L4 --> DC
    L1 --> L5
    L5 --> DC
    L2 --> L6
    DA --> L6
    L6 --> DA
    L1 --> L7
    DS --> L7
    L7 --> DK
    C5 -->|"invalid record"| ERR
```

| Decision | Rule | Flow to the rejected record |
| --- | --- | --- |
| `missing_or_invalid_name` | Canonical name shorter than 2 characters | `stg_raw_observation.is_valid = false` |
| `missing_price` (strict mode only) | Neither `price` nor `list_price` parsed | as above with `reject_reason` |
| `invalid_url` (strict mode only) | URL does not match `^https?://host` | as above |
| `duplicate_source_row` | Same `(source_code, source_product_id)` twice in one run | counted, not staged twice |
| Product skipped for grain | Two rows resolve to the same canonical product | counted in `duplicates_merged` |

---

## 5. Level 2c — Analytics, quality and serving

```mermaid
flowchart TB
    DS[("D3 fact_price_snapshot")]
    DC[("D4 change feeds")]
    DK[("D5 catalog comparison")]
    DA[("D6 aggregate")]
    DP[("D2 dimensions")]
    DR[("D7 operations<br/>etl_run, dq_rule_result,<br/>ingestion_http_log")]

    subgraph P6A["6a Measure quality"]
        Q1["12 rules in SAVEPOINTs"]
        Q2["Severity-weighted score"]
        Q3["Blocking decision<br/>critical failures only"]
    end

    V["20 analytical views<br/>vw_*"]
    AN["Analytics service<br/>21 query functions"]

    subgraph P6B["6c Serve"]
        AU["Authenticate<br/>JWT or API key"]
        RB["Authorise<br/>role to rights"]
        VAL["Validate<br/>Pydantic models"]
        EP["104 REST operations<br/>15 routers"]
        CSV["CSV export"]
    end

    UI["Dashboard<br/>React and Vite"]
    USR["Analysts, managers,<br/>administrators"]

    DS --> Q1
    DC --> Q1
    DA --> Q1
    DP --> Q1
    Q1 --> Q2 --> Q3
    Q3 -->|"verdict"| DR

    DS --> V
    DC --> V
    DK --> V
    DA --> V
    DP --> V
    V --> AN
    AN --> EP
    EP --> CSV

    USR -->|"credentials"| AU
    AU --> RB --> VAL --> EP
    EP -->|"JSON"| UI
    UI -->|"fetch, filter, sort"| USR
    EP -->|"answers"| USR
```

### 5.1 Rule flow through the quality process

| Step | Behaviour |
| --- | --- |
| Open savepoint | `Rule.run()` → `session.begin_nested()` |
| Evaluate | The rule's SQL runs against the run's data |
| Classify | `_status(observed, threshold)`: pass if ≥ threshold (or ≤ for "lower is better"), warn within 5 % of the threshold, otherwise fail |
| Persist | `dq_rule_result` row with observed, expected, threshold, counts and message |
| Score | `Σ(weight × factor) / Σ(weight) × 100`, `weight = 1 + 0.5 × severity_rank` |
| Gate | Only `severity = critical` failures set the run status to `failed` |
| Isolate | A raising rule is rolled back to its savepoint and recorded as `fail` |

---

## 6. Data dictionary

### 6.1 Inbound flows

| # | Flow name | Source | Destination | Structure | Frequency |
| --- | --- | --- | --- | --- | --- |
| IN-01 | Product payload | Upstream source | P1 Collect | HTML document or JSON object with title/price/rating/stock/brand | Per product page |
| IN-02 | `robots.txt` | Upstream host | A1 Robots parser | Group/User-agent, Allow/Disallow, Crawl-delay, Sitemap lines | Once per host per TTL |
| IN-03 | Run configuration | Operator / scheduler | P0/P1 | `{sources[], database, limit_per_source, strict, skip_dq, skip_catalog, trigger}` | Per run |
| IN-04 | Credentials | Operator | P6 Serve | email, password (or `pip_…` API key) | Per session |
| IN-05 | Query / filter request | User | P6 Serve | Paging, sorting, filters, saved view | Per request |
| IN-06 | Alert rule | User | P6 Serve | `{metric, operator, threshold, category, source_code, channel}` | On save |
| IN-07 | Read-only SQL | Analyst | P6 Serve | `{"sql": "SELECT …", "limit": 200}` | On execute |
| IN-08 | `Retry-After` header | Upstream host | Rate limiter | delta-seconds or HTTP-date | On 429/503 |

### 6.2 Internal flows

| # | Flow name | From | To | Structure |
| --- | --- | --- | --- | --- |
| IF-01 | `RawProduct` | Source adapter | Stager | `source_code, source_product_id, name, category, price_text, currency_hint, rating_text, rating_count_text, star_elements, availability_text, in_stock_flag, url, image_url, brand, description, payload, http_status, fetched_at` |
| IF-02 | Staged observation | Stager | `stg_raw_observation` | raw columns + `payload_hash`, `landed_at`, `is_valid`, `reject_reason` |
| IF-03 | `NormalizedProduct` | Preparer | Resolver | canonical and normalised name, fingerprint, blocking key, category path, price, `price_usd`, `fx_rate_to_usd`, rating, availability, `quality_flags`, `is_valid` |
| IF-04 | Match result | Resolver | Loader | `product_id, strategy, score, fingerprint, blocking_key, parts{}, is_duplicate` |
| IF-05 | Snapshot row | Loader | `fact_price_snapshot` | 26 columns (grain: product × source × run) |
| IF-06 | Price change event | Loader | `chg_price_change` | previous/new price, absolute and percentage change, direction, magnitude band, significance |
| IF-07 | Lifecycle event | Loader | `chg_product_event` | `event_type ∈ {new, recurring, removed, category_changed}`, severity, old/new values, `days_missing` |
| IF-08 | Category rollup | Loader | `agg_category_daily` | date × category × source with counts and price statistics |
| IF-09 | Reconciliation row | Reconciler | `fact_catalog_snapshot` | SKU, product, status, strategy, similarity, both prices, gap, brand/category match |
| IF-10 | Rule outcome | Quality engine | `dq_rule_result` | rule code, dimension, severity, status, observed/expected/threshold, counts, message, evidence |
| IF-11 | Audit entry | HTTP client | `ingestion_http_log` | method, url, host, status, latency, bytes, robots decision, cache flag, retries, error |
| IF-12 | Run record | Pipeline | `etl_run` | status, trigger, counters (12), DQ score, duration, warnings, params, `created_by` |
| IF-13 | Source statistics | Pipeline | `dim_source` | totals, running averages, `last_run_at`, `last_run_id` |
| IF-14 | Sync state | Pipeline | `sync_state` | cursors, `consecutive_failures`, status, message |
| IF-15 | Notification | Pipeline / alerts | `app_notification` | level, title, body, entity link, read state |

### 6.3 Outbound flows

| # | Flow name | From | To | Structure |
| --- | --- | --- | --- | --- |
| OUT-01 | Product page | P6 | Dashboard / client | `Page[ProductSummary]` with paging metadata |
| OUT-02 | Product detail | P6 | Dashboard / client | product + `history[]`, `changes[]`, `events[]`, `catalog[]` |
| OUT-03 | Change feed | P6 | Dashboard / client | `Page[PriceChangeRead]` or event rows |
| OUT-04 | KPI summary | P6 | Dashboard | counts, price statistics, change statistics, event mix, DQ and catalog blocks |
| OUT-05 | Trend series | P6 | Dashboard | daily observations, average price, in-stock percentage |
| OUT-06 | Leaderboards | P6 | Dashboard | brand leaderboard, category breakdown, top movers |
| OUT-07 | CSV export | P6 | Analyst | header row + up to 50,000 product rows |
| OUT-08 | Compliance report | P6 | Compliance officer | requests, blocked, cached, retried, bytes, latency percentiles, hosts |
| OUT-09 | Run status | P6 | Operator | status, counters, DQ score, warnings, stage timings |
| OUT-10 | Alert notifications | P6 | User | in-app notification with a deep link to the affected screen |
| OUT-11 | Paging envelope | P6 | Client | `items, total, page, page_size, pages, has_next, has_prev` |
| OUT-12 | Error response | P6 | Client | `error, message, details, path` |

---

## 7. Data store dictionary

| Store | Tables | Contents | Volumetric profile | Retention |
| --- | --- | --- | --- | --- |
| D1 Staging zone | `stg_raw_observation` | Raw payloads exactly as received, with hash, HTTP status, validity and rejection reason | Grows with extraction volume (126 rows for a demo run) | 90 days |
| D2 Product dimension | `dim_product` | Canonical products, identity, match provenance, current state | Small and slow-changing (66 rows) | Indefinite |
| D3 Price history | `fact_price_snapshot` | Every observed price with context and change | Largest table; append-only (8,302 rows) | 730 days |
| D4 Change feeds | `chg_price_change`, `chg_product_event` | Detected movements and lifecycle events | ≈ 1 event per snapshot (16,388 rows) | 730 days |
| D5 Catalog comparison | `fact_catalog_snapshot` | Per-run SKU matching with price gaps | SKU count × runs (285 rows) | 1 year |
| D6 Aggregate | `agg_category_daily` | Daily category rollup for fast dashboards | Days × categories (18 rows in the demo) | With D3 |
| D7 Operations | `etl_run`, `dq_rule_result`, `ingestion_http_log`, `sync_state` | Run history, quality verdicts, request audit, sync checkpoints | Runs × 12 rules; requests per run | 1 year / 90 days / 90 days / indefinite |
| D8 Application | `app_*` (7 tables) | Accounts, keys, saved views, alerts, notifications, audit, settings | Small (≤ 100 rows) | Indefinite / 3 years for audit |
| D9 Dimensions | `dim_category`, `dim_date`, `dim_source`, `dim_currency` | Conformed reference data | 18 + 403 + 5 + 25 rows | Indefinite |
| D10 Reference catalog | `catalog_product` | The retailer's internal SKU list | 60 rows | Indefinite |
| D11 Cache (filesystem) | `var/http-cache/<host>/<sha256>.json` | HTTP responses for 1,800 s | Bounded by TTL | 1,800 s |
| D12 Artifacts (filesystem) | `var/artifacts/report-*.json` | Analytics reports produced by the DAG | One per run | Manual |

---

## 8. Control flows

Control flows decide *when* data flows; they are the reason the pipeline degrades rather than fails.

| Control | Decision | Result |
| --- | --- | --- |
| Robots gate | `decision.allowed` | `true` → fetch; `false` → raise `ComplianceError`, log, skip the URL |
| Circuit breaker | 5 consecutive host failures | Subsequent requests to that host raise `IngestionError` without network I/O |
| Rate limiter | Token bucket + sliding window + crawl delay | The call sleeps until it is legal to proceed |
| Source isolation | Exception inside `_process_source()` | Recorded in `sources_failed`; run continues and becomes `partial` |
| Staleness window | `last_seen_at < captured_at - 7 days` | `removed` event, `is_active = false` |
| Fact grain | `product_id` already written this run | Snapshot skipped, `duplicates_merged` incremented |
| DQ gate | Any `critical` rule failed | Run status `failed`; DAG `data_quality_gate` raises |
| Reconciliation | Catalog empty | Reconciliation skipped, counters zero |
| Query Lab | Statement is not `SELECT`/`WITH`/`EXPLAIN`, or contains a write keyword | `422`, no database call |
| Account lock | 5 consecutive failed logins | `locked_until = now + 15 minutes` |
| API trigger | Role lacks `run_pipeline` | `403 permission_denied` |

```mermaid
flowchart TD
    START(["Run requested"]) --> HEALTH{"Database reachable?"}
    HEALTH -->|"no"| STOP1(["Abort - status failed"])
    HEALTH -->|"yes"| COMPLY{"At least one source<br/>passes robots and terms?"}
    COMPLY -->|"no"| STOP2(["Abort before crawling"])
    COMPLY -->|"yes"| LOOP["For each source"]
    LOOP --> FETCH["Fetch under compliance gate"]
    FETCH --> SRCERR{"Source error?"}
    SRCERR -->|"yes"| WARN["Record warning - mark source failed"]
    SRCERR -->|"no"| LOAD["Stage, prepare, resolve, load"]
    WARN --> NEXT{"More sources?"}
    LOAD --> NEXT
    NEXT -->|"yes"| LOOP
    NEXT -->|"no"| POST["Aggregates and catalog reconciliation"]
    POST --> DQGATE{"Any critical DQ failure?"}
    DQGATE -->|"yes"| FAILED(["Status failed"])
    DQGATE -->|"no"| WARNED{"Any source failed?"}
    WARNED -->|"yes"| PARTIAL(["Status partial"])
    WARNED -->|"no"| OK(["Status success"])
```