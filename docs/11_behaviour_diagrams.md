# 11 — Behaviour Diagrams

## Purpose

This document describes the dynamic behaviour of the Web-to-Warehouse Product Intelligence Pipeline
with four UML-style diagrams rendered in Mermaid: a **sequence diagram** of one end-to-end pipeline
run, an **activity diagram** of the run's control flow, **state diagrams** for the product lifecycle
and the run status, and a **class diagram** of the principal Python types. Together they answer
"what happens, in what order, under which conditions, and in which objects".

---

## Table of contents

1. [Sequence diagram — one pipeline run](#1-sequence-diagram--one-pipeline-run)
2. [Sequence diagram — an API request](#2-sequence-diagram--an-api-request)
3. [Activity diagram — pipeline run](#3-activity-diagram--pipeline-run)
4. [State diagram — product lifecycle](#4-state-diagram--product-lifecycle)
5. [State diagram — run status](#5-state-diagram--run-status)
6. [State diagram — source health](#6-state-diagram--source-health)
7. [Class diagram](#7-class-diagram)
8. [Interaction notes](#8-interaction-notes)

---

## 1. Sequence diagram — one pipeline run

```mermaid
sequenceDiagram
    autonumber
    participant CLI as CLI or Airflow or API
    participant PIPE as Pipeline
    participant SRC as ProductSource
    participant HTTP as CompliantHttpClient
    participant RB as RobotsCache
    participant LIM as RateLimiter
    participant CACHE as Disk cache
    participant LD as WarehouseLoader
    participant DD as DedupeEngine
    participant DB as Warehouse
    participant RC as CatalogReconciler
    participant DQ as Quality engine

    CLI->>PIPE: PipelineConfig sources, limit, strict
    PIPE->>DB: INSERT etl_run status running
    loop for each enabled source
        PIPE->>LD: preload_dimensions
        PIPE->>DB: sync_dim_source for foreign key integrity
        PIPE->>SRC: fetch limit
        SRC->>HTTP: get url
        HTTP->>RB: can_fetch url, user_agent
        RB-->>HTTP: RobotsDecision allowed, crawl_delay
        alt disallowed by robots.txt
            HTTP-->>SRC: ComplianceError
            HTTP->>DB: audit row robots_allowed false
            PIPE->>PIPE: record warning, source failed
        else allowed
            opt response already cached
                HTTP->>CACHE: read cached payload
                CACHE-->>HTTP: FetchResult from_cache true
            else cache miss
                HTTP->>LIM: acquire host
                LIM-->>HTTP: permit after pacing delay
                HTTP->>HTTP: GET with retry and backoff
                HTTP->>CACHE: store successful response
            end
            HTTP->>DB: INSERT ingestion_http_log
            HTTP-->>SRC: FetchResult text
            SRC-->>PIPE: RawProduct record
            PIPE->>LD: stage raw batch
            LD->>DB: INSERT stg_raw_observation
        end
        loop for each raw record
            PIPE->>PIPE: transform_product
            Note over PIPE: clean name, normalise category,<br/>parse price, convert to USD,<br/>attach quality flags
            PIPE->>DD: find_match name, brand, category
            alt fingerprint known
                DD-->>PIPE: MatchResult strategy exact score 1.0
            else normalised name equal
                DD->>DB: SELECT by normalized_name
                DD-->>PIPE: MatchResult strategy blocked_exact
            else fuzzy search
                DD->>DB: SELECT blocking candidates limit 25
                DB-->>DD: candidate rows
                DD->>DD: combined_similarity with digit guard
                DD-->>PIPE: MatchResult strategy fuzzy or new
            end
            PIPE->>LD: upsert_product record, match
            LD->>DB: UPSERT dim_product and dim_category
            PIPE->>LD: insert_snapshot product, record, previous
            LD->>DB: SELECT latest snapshot for product and source
            LD->>DB: INSERT fact_price_snapshot
            alt price changed
                LD->>DB: INSERT chg_price_change
            end
            LD->>DB: INSERT chg_product_event new or recurring
        end
        PIPE->>LD: detect_removed staleness 7 days
        LD->>DB: INSERT removed events and set is_active false
        PIPE->>LD: update_sync_state source
    end
    PIPE->>LD: refresh_category_daily
    LD->>DB: UPSERT agg_category_daily
    PIPE->>RC: run persist
    RC->>DB: SELECT catalog, candidates, latest prices
    RC->>DB: INSERT fact_catalog_snapshot
    RC-->>PIPE: reconciliation summary
    PIPE->>DQ: evaluate_quality run_id
    loop for each of 12 rules
        DQ->>DB: SAVEPOINT, evaluate, INSERT dq_rule_result, COMMIT
    end
    DQ-->>PIPE: score, pass, warn, fail, blocking
    PIPE->>DB: UPDATE etl_run counters, status, duration
    PIPE-->>CLI: PipelineResult
```

### 1.1 Message classification

| Message | Type | Cardinality | Notes |
| --- | --- | --- | --- |
| `PipelineConfig` | data | 1 → 1 | The only way to start a run |
| `fetch(limit)` | call | 1 per source | Generator: the source yields lazily |
| `can_fetch` | call | 1 per request | Cached per host for `CACHE_TTL_SECONDS` |
| `acquire(host)` | call | 1 per network request | Blocks until the policy allows it |
| `transform_product` | call | 1 per record | Pure function; never raises |
| `find_match` | call | 1 per record | Exact → exact-name → fuzzy cascade |
| `insert_snapshot` | call | ≤ 1 per product per run | Second row for the same product is skipped |
| `evaluate_quality` | call | 1 per run | 12 rule evaluations |
| `PipelineResult` | return | 1 | Counters, timings, quality, reconciliation, warnings |

---

## 2. Sequence diagram — an API request

```mermaid
sequenceDiagram
    autonumber
    participant UI as Dashboard or client
    participant MW as Middleware CORS and gzip and timing
    participant DP as Dependency get_db
    participant SEC as get_current_user
    participant RB as require_rights
    participant RT as Router endpoint
    participant SVC as Analytics service
    participant DB as Warehouse

    UI->>MW: GET /api/v1/products page 1 size 25
    MW->>MW: add X-Process-Time-Ms and X-Database
    MW->>DP: resolve DbSession
    DP->>DB: open session
    MW->>SEC: resolve bearer token or API key
    alt token starts with pip_
        SEC->>DB: SELECT app_api_key by hashed_key
        DB-->>SEC: key row and owner
        SEC->>DB: UPDATE usage_count, last_used_at
    else JWT
        SEC->>SEC: decode token verify iss, exp, type
        SEC->>DB: SELECT app_user by sub
    end
    SEC-->>MW: AppUser
    MW->>RB: check rights for the endpoint
    alt role lacks the right
        RB-->>UI: 403 permission_denied
    else authorised
        RB->>RT: AppUser
        RT->>RT: validate query parameters with Pydantic
        RT->>SVC: build filter clause and paging
        SVC->>DB: SELECT count then SELECT rows LIMIT OFFSET
        DB-->>SVC: rows
        SVC-->>RT: dictionaries
        RT-->>UI: Page items total page page_size pages
    end
```

### 2.1 Error paths in the same request

```mermaid
sequenceDiagram
    participant UI as Client
    participant MW as Error handlers
    participant RT as Router
    participant DB as Warehouse

    UI->>RT: GET /api/v1/products/999999
    RT->>DB: SELECT from vw_product_index
    DB-->>RT: no rows
    RT->>RT: raise ProductNotFoundError
    RT->>MW: PipelineError status 404
    MW-->>UI: 404 {"error":"product_not_found","message":"product 999999 not found","details":{"product_id":999999}}
    UI->>RT: POST /api/v1/queries/execute with DELETE statement
    RT->>RT: QueryRequest validator rejects the statement
    RT->>MW: RequestValidationError
    MW-->>UI: 422 validation_error with field, message, type
    UI->>RT: GET /api/v1/products without a token
    RT->>MW: AuthenticationError
    MW-->>UI: 401 authentication_failed with a hint header
```

---

## 3. Activity diagram — pipeline run

```mermaid
flowchart TD
    A(["Run requested by CLI, Airflow or API"]) --> B["Create etl_run row: status running, trigger, params"]
    B --> C["Resolve the source list: enabled and terms_allowed"]
    C --> D{"Any source?"}
    D -->|"no"| Z(["Status failed: no usable source"])
    D -->|"yes"| E["Preload dimension caches and ensure dim_source rows"]

    E --> F["Extract: fetch limit records under the compliance gate"]
    F --> G{"Robots decision?"}
    G -->|"deny"| H["Log refusal, raise ComplianceError, warn"] --> I
    G -->|"allow"| I["Cache lookup"]
    I -->|"hit"| J["Reuse stored response"]
    I -->|"miss"| K["Rate-limit acquire, GET with retry and backoff"]
    K --> L{"HTTP status?"}
    L -->|"2xx"| M["Store in cache, write audit row"]
    L -->|"429 or 5xx"| N["Penalise host, retry or raise"] --> K
    L -->|"other 4xx"| O["Record error, stop this source"] --> I

    M --> P["Parse payload into RawProduct"]
    J --> P
    P --> Q["Stage raw payloads into the landing zone"]
    Q --> R["Clean name, category, price, currency, rating, availability"]
    R --> S{"Record valid?"}
    S -->|"no"| T["Mark invalid with reject_reason, count as rejected"] --> Y
    S -->|"yes"| U["Compute fingerprint and blocking key"]
    U --> V{"Match found?"}
    V -->|"exact"| W["Reuse canonical product"]
    V -->|"fuzzy"| X["Update canonical product and count the merge"]
    V -->|"none"| Y["Insert new dim_product and emit new event"]
    W --> Z1["Append fact_price_snapshot for this product and run"]
    X --> Z1
    Y --> Z1
    Z1 --> ZA{"Price changed?"}
    ZA -->|"yes"| ZB["Insert chg_price_change with band and significance"]
    ZA -->|"no"| ZC["Emit recurring event"]
    ZB --> ZD["Update dim_product current and previous price"]
    ZC --> ZD
    T --> Y
    ZD --> ZE["Product already loaded in this run?"]
    ZE -->|"yes"| ZF["Skip snapshot, count as duplicate merge"]
    ZE -->|"no"| ZG["Continue with the next record"]

    ZG --> ZH{"More records?"}
    ZF --> ZH
    ZH -->|"yes"| U
    ZH -->|"no"| ZI{"More sources?"}
    ZI -->|"yes"| F
    ZI -->|"no"| ZJ["Detect products unseen for the staleness window"]
    ZJ --> ZK["Refresh the category-day aggregate"]
    ZK --> ZL{"Catalog populated and reconciliation enabled?"}
    ZL -->|"yes"| ZM["Match SKUs, compute price gaps, persist"]
    ZL -->|"no"| ZN["Skip reconciliation"]
    ZM --> ZO{"DQ enabled?"}
    ZN --> ZO
    ZO -->|"yes"| ZP["Evaluate 12 rules in savepoints, persist outcomes"]
    ZO -->|"no"| ZQ["Skip quality evaluation"]
    ZP --> ZR["Compute the severity-weighted score"]
    ZQ --> ZS["Finalise: counters, duration, warnings"]
    ZR --> ZS
    ZS --> ZT{"Blocking critical failure?"}
    ZT -->|"yes"| ZU(["Status failed"])
    ZT -->|"no"| ZV{"Any source failed?"}
    ZV -->|"yes"| ZW(["Status partial"])
    ZV -->|"no"| ZX(["Status success"])
    ZX --> ZY(["Return PipelineResult to the caller"])
```

### 3.1 Activity phases and durations (measured)

| Phase | Stage name | Measured duration (multi-source demo run) |
| --- | --- | --- |
| Compliance-gated extraction | `extract` | Dominated by rate limiting; cached runs ≈ 0 |
| Landing | `stage` | Batch inserts of `PIPELINE_BATCH_SIZE` rows |
| Preparation | `transform` | Pure CPU work; the fastest stage |
| Resolution | `resolve` | Exact hits dominate; blocked candidates capped at 25 |
| Loading | `load` | One insert per product plus change events |
| Change detection | `detect` | Single query per source for removal detection |
| Aggregation | `aggregate` | One grouped query per run |
| Reconciliation | `reconcile` | 39/57 matched, ≈ 104–182 ms |
| Quality | `quality` | 12 rule queries |
| **Total** | — | **≈ 3.5 s (3,481 ms) for the delivered run** |

---

## 4. State diagram — product lifecycle

```mermaid
stateDiagram-v2
    [*] --> Candidate: record staged
    Candidate --> Active: first sighting<br/>event new
    Candidate --> Rejected: name too short<br/>reject_reason recorded
    Rejected --> [*]: retained in the staging zone only

    Active --> Active: recurring observation<br/>price and rating refreshed
    Active --> Suspended: unseen for the staleness window<br/>event removed
    Active --> Active: recategorised<br/>event category_changed

    Suspended --> Active: seen again<br/>event recurring
    Suspended --> Retired: still unseen after the review window
    Retired --> Active: returned to the source

    note right of Active
        is_active = true
        observation_count increments
        first_seen_at fixed
        last_seen_at updated
    end note

    note right of Suspended
        is_active = false
        is still queryable with is_active filter
        last_seen_at frozen
    end note
```

### 4.1 Event mapping

| Transition | Event written | Table | Condition in code |
| --- | --- | --- | --- |
| Candidate → Active | `new` | `chg_product_event` | `previous is None` in `insert_snapshot()` |
| Active → Active | `recurring` | `chg_product_event` | `previous is not None` and no price change |
| Active → Active (price) | `chg_price_change` | `chg_price_change` | `change_pct not in (None, 0.0)` |
| Active → Active (category) | `category_changed` | `chg_product_event` | `previous_category_id != new_category_id` |
| Active → Suspended | `removed` | `chg_product_event` | `last_seen_at < captured_at - staleness_days` |
| Suspended → Active | `recurring` | `chg_product_event` | Observed again; `is_active` set back to true |
| Candidate → Rejected | — | `stg_raw_observation` | `is_valid = false`, `reject_reason` set |
| Merged product | `match_strategy = merged` | `dim_product` | `DedupeEngine.merge_into()`; absorbed row keeps `matched_product_id` |

---

## 5. State diagram — run status

```mermaid
stateDiagram-v2
    [*] --> pending: Pipeline created
    pending --> running: etl_run row written
    running --> running: sources processed one by one
    running --> partial: at least one source failed
    running --> failed: source error with strict mode<br/>or pipeline_fail_fast
    running --> failed: critical DQ rule failed
    running --> success: all sources ok and no blocking rule
    partial --> running: re-run of the failing source
    success --> [*]
    partial --> [*]
    failed --> [*]
    failed --> running: manual retry creates a new run_id
```

### 5.1 Status assignment rules

| Status | Assigned when | Consumers |
| --- | --- | --- |
| `running` | `_run_row()` writes the row at the start | Pipeline screen shows an in-progress run |
| `success` | No source failed and the blocking list is empty | KPI-01 counts it as success |
| `partial` | `sources_failed` is non-empty but the run completed | Warning column in the run list |
| `failed` | `PipelineError` propagated, or a **critical** DQ rule failed (`DQ006`, `DQ011`) | Exit code 1 from the CLI; the DAG fails |

---

## 6. State diagram — source health

```mermaid
stateDiagram-v2
    [*] --> Idle: source registered
    Idle --> Probing: run selected
    Probing --> Healthy: robots allowed and records returned
    Probing --> Failing: exception or no records
    Healthy --> Degraded: extraction succeeded but some pages were skipped
    Healthy --> Failing: exception during extraction
    Degraded --> Healthy: next run completes without errors
    Failing --> Retrying: consecutive_failures below 3
    Failing --> Disabled: three consecutive failures
    Retrying --> Healthy: successful run
    Retrying --> Disabled: still failing
    Disabled --> Idle: operator re-enables the source
    Disabled --> [*]: terms withdrawn
```

| State | Field values | Effect |
| --- | --- | --- |
| Healthy | `sync_state.status = 'healthy'`, `consecutive_failures = 0` | Included in scheduled runs |
| Degraded | `success_rate_pct` dropping, `errors` on the source object | Run continues; warnings recorded |
| Failing | `sync_state.status = 'failing'`, `consecutive_failures ≥ 1` | Surfaced on the Sources screen |
| Disabled | `dim_source.enabled = false` (set by `sync_dim_source()` when terms are not allowed) | Excluded by `Pipeline._source_codes()` |

---

## 7. Class diagram

```mermaid
classDiagram
    class ProductSource {
        <<abstract>>
        +str code
        +str name
        +str kind
        +str base_url
        +str terms_url
        +int rate_limit_per_minute
        +float min_delay_seconds
        +bool terms_allowed
        +fetch(limit) Iterator~RawProduct~
        +health_check() dict
        +close()
    }

    class RawProduct {
        +str source_code
        +str source_product_id
        +str name
        +str category
        +str price_text
        +str currency_hint
        +str rating_text
        +str availability_text
        +str url
        +str brand
        +dict payload
        +content_hash str
    }

    class NormalizedProduct {
        +str canonical_name
        +str normalized_name
        +str fingerprint
        +str blocking_key
        +str category
        +float price
        +float price_usd
        +float fx_rate_to_usd
        +float rating
        +str availability
        +list quality_flags
        +bool is_valid
        +str reject_reason
        +flag(code)
    }

    class DedupeEngine {
        +Session session
        +float threshold
        +int blocking_length
        +int candidate_limit
        +DedupeStats stats
        +find_match(name, brand, category) MatchResult
        +merge_into(product, other) DimProduct
        +register(product)
        +resolve_batch(candidates) list
        +duplicates_in_iterable(names) list
    }

    class MatchResult {
        +int product_id
        +str strategy
        +float score
        +str fingerprint
        +str blocking_key
        +dict parts
        +is_duplicate bool
    }

    class WarehouseLoader {
        +Session session
        +str run_id
        +datetime captured_at
        +LoadStats stats
        +preload_dimensions()
        +resolve_category(record) DimCategory
        +stage(records) int
        +upsert_product(record, match) tuple
        +preload_latest(ids, source) dict
        +insert_snapshot(product, record, previous)
        +detect_removed(source, seen, staleness_days) int
        +refresh_category_daily() int
        +update_sync_state(source, extracted, success)
    }

    class Pipeline {
        +PipelineConfig config
        +PipelineResult result
        +run() PipelineResult
        -execute(session, run_id)
        -process_source(session, run_id, source, dedupe) LoadStats
        -register_source_dim(session, source, stats, duration, success)
    }

    class Rule {
        <<dataclass frozen>>
        +str code
        +str name
        +str dimension
        +str severity
        +str description
        +run(session, context) RuleOutcome
    }

    class RuleOutcome {
        +str rule_code
        +str dimension
        +str severity
        +str status
        +float observed_value
        +float expected_value
        +float threshold
        +int records_checked
        +int records_failed
        +str message
        +dict evidence
        +pass_rate_pct float
    }

    class QualityReport {
        +str run_id
        +list outcomes
        +passed int
        +warned int
        +failed int
        +score float
        +blocking_failures list
        +summary() dict
    }

    class CatalogReconciler {
        +Session session
        +str run_id
        +float threshold
        +int block_length
        +int min_pool
        +int max_pool
        +run(persist) list
        +match_one(row, candidates, latest_prices) CatalogMatchResult
        +build_indexes(candidates)
        +narrow_candidates(row, key, candidates) list
    }

    class CatalogMatchResult {
        +str catalog_sku
        +int product_id
        +str match_status
        +str strategy
        +float similarity
        +float price_gap_abs
        +float price_gap_pct
        +bool category_match
        +bool brand_match
        +is_price_mismatch bool
    }

    class CompliantHttpClient {
        +str source_code
        +str run_id
        +RateLimiter limiter
        +CircuitBreaker breaker
        +RobotsCache robots
        +get(url, params) FetchResult
        +get_json(url) any
        +get_soup(url) Document
        +audit_rows() list
    }

    class ApiRouter {
        <<fastapi APIRouter>>
        +prefix
        +tags
        +include_router(prefix)
    }

    ProductSource <|.. DummyJsonProductsSource
    ProductSource <|.. FakeStoreProductsSource
    ProductSource <|.. OpenLibraryBooksSource
    ProductSource <|.. BooksToScrapeSource
    ProductSource <|.. LocalFixtureSource

    ProductSource ..> CompliantHttpClient : creates lazily
    ProductSource ..> RawProduct : yields
    ProductSource ..> NormalizedProduct : transform_product
    CompliantHttpClient --> Rule : no
    DedupeEngine ..> MatchResult : returns
    DedupeEngine ..> NormalizedProduct : compares names and brands
    Pipeline --> DedupeEngine : creates
    Pipeline --> WarehouseLoader : creates per source
    Pipeline ..> ProductSource : get_source
    Pipeline ..> Rule : no
    Pipeline --> CatalogReconciler : runs after loading
    Pipeline --> QualityReport : evaluate_quality
    Rule --> RuleOutcome : produces
    QualityReport o-- RuleOutcome : aggregates
    WarehouseLoader ..> NormalizedProduct : consumes
    CatalogReconciler ..> CatalogMatchResult : produces
    ApiRouter ..> WarehouseLoader : no
    ApiRouter ..> CompliantHttpClient : no
```

### 7.1 Relationship notes

| Relationship | Cardinality | Where |
| --- | --- | --- |
| `ProductSource` → `RawProduct` | 1 → many (lazy) | The source contract yields records |
| `ProductSource` → `NormalizedProduct` | 1 → 1 | `transform_product(raw)` |
| `ProductSource` → `CompliantHttpClient` | 1 → 0..1 | Created on first use, closed by `close()` |
| `Pipeline` → `DedupeEngine` | 1 → 1 per run | Shared across sources so the fingerprint cache is reused |
| `Pipeline` → `WarehouseLoader` | 1 → 1 per source | Counters merged with `LoadStats.merge()` |
| `WarehouseLoader` → `NormalizedProduct` | 1 → many | One snapshot per record |
| `CatalogReconciler` → `CatalogMatchResult` | 1 → many | One per active catalog SKU |
| `Rule` → `RuleOutcome` | 1 → 1 | Inside a savepoint |
| `QualityReport` → `RuleOutcome` | 1 → many | 12 per run |
| `ApiRouter` → models | 1 → many | Routers select from models; the class diagram shows no `DedupeEngine` dependency in the serving layer, which is deliberate |

---

## 8. Interaction notes

| Note | Detail |
| --- | --- |
| **Lazy extraction** | Sources are generators; the pipeline materialises them once per source with `_safe_take()`, so a misbehaving source cannot hang the run |
| **Cache-first politeness** | The second run of the same source performs no HTTP requests at all, which is why repeat demonstrations are instantaneous |
| **Session scope** | One `session_scope(database)` wraps the entire run: everything commits together, and any escaping exception rolls the run back |
| **Savepoint isolation** | Each DQ rule and each rule-result insert is wrapped in `session.begin_nested()` so a failure is contained |
| **Idempotent stage boundaries** | `etl_run` is written first (so a crashed run is visible), facts are appended per source, and the finalisation block writes the counters last |
| **Re-entrancy** | Two concurrent runs get different `run_id` values, so their facts never collide; `MAX_ACTIVE_RUNS = 1` in the DAG prevents overlap by schedule |
| **Dialect-neutral transactions** | `bootstrap.apply_views()` opens one connection per view statement because MySQL's implicit DDL commit invalidates savepoints |