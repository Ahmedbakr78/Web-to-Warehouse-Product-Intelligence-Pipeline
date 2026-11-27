# Extended Diagram Suite

The repository already contains more than one hundred Mermaid diagrams across
`flowchart`, `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`, `classDiagram`,
`gantt` and `graph`. This document **adds** twelve extended architecture, portfolio,
orchestration, lifecycle, and traceability diagrams (`C4Context`, `C4Container`,
`C4Dynamic`, `journey`, `timeline`, `mindmap`, `pie`, `gitGraph`, `requirementDiagram`,
`quadrantChart`, `sequenceDiagram`, and `stateDiagram-v2`). Every node below
corresponds to a component that actually exists in this repository; nothing is invented.

All diagrams are valid Mermaid and are picked up automatically by
`python3 scripts/diagrams.py extract`.

---

## 1. C4 — system context

```mermaid
C4Context
    title System Context — Web-to-Warehouse Product Intelligence Pipeline
    Person(analyst, "Retail analyst", "Monitors prices, quality and the change feed")
    Person(engineer, "Data engineer", "Owns sources, the DAG and the warehouse")
    System(pipeline, "Product Intelligence Pipeline", "Ingests, cleans, deduplicates, loads and analyses")
    System_Ext(sources, "Permitted public sources", "Open Library, Gutendex, Steam, Open Food Facts, TVMaze, ...")
    System_Ext(catalog, "Internal product catalogue", "The retailer's own SKUs")
    System_Ext(ci, "GitHub Actions", "Lint, type-check, test, build")
    System_Ext(scheduler, "Apache Airflow", "Orchestrates the nine-stage run")

    Rel(analyst, pipeline, "Views dashboards, runs SQL, exports reports")
    Rel(engineer, pipeline, "Configures sources and rules")
    Rel(scheduler, pipeline, "Triggers scheduled and backfill runs")
    Rel(pipeline, sources, "Fetches via robots.txt + rate limiter")
    Rel(pipeline, catalog, "Reconciles scraped vs internal SKUs")
    Rel(ci, pipeline, "Verifies every commit")
```

## 2. C4 — containers

```mermaid
C4Container
    title Container Diagram — runtime building blocks
    Person(user, "Analyst", "Uses the platform")

    Container(web, "React 19 dashboard", "TypeScript / Vite", "23 screens, light + dark themes, mobile drawer")
    Container(api, "FastAPI service", "Python", "222 REST operations, JWT + API keys, OpenAPI docs")
    Container(etl, "ETL pipeline", "Python", "Extract, stage, clean, resolve, load, detect, aggregate, quality")
    Container(ingest, "Ingestion adapters", "BeautifulSoup / Scrapy / httpx", "34 registered sources, compliance gate")
    ContainerDb(db, "Analytical warehouse", "PostgreSQL / MySQL / SQLite", "29 tables, 23 views, price snapshots")
    Container(airflow, "Airflow DAG", "Python", "Scheduled, backfill and DQ-monitor DAGs")

    Rel(user, web, "HTTPS")
    Rel(web, api, "REST / JSON")
    Rel(api, db, "SQLAlchemy")
    Rel(airflow, etl, "Triggers")
    Rel(etl, ingest, "Uses")
    Rel(etl, db, "Writes snapshots and events")
```

## 3. Journey — analyst experience

```mermaid
journey
    title A working day with the platform
    section Morning
      Sign in: 5: Analyst, Dashboard
      Read the morning briefing: 5: Analyst, Briefing
      Review price-drop alerts: 4: Analyst, Alerts
    section Midday
      Investigate a category trend: 4: Analyst, Analytics
      Run read-only SQL: 4: Analyst, Query lab
      Export a CSV report: 5: Analyst, Reports
    section Afternoon
      Tune an alert threshold: 4: Analyst, Account
      Check the data-quality score: 5: Analyst, Quality
      Confirm the pipeline run: 5: Analyst, Runs
```

## 4. Timeline — delivery milestones

```mermaid
timeline
    title Delivery timeline
    section Plan
      Proposal and scope : Roles and RACI : Risk register : KPIs
    section Design
      Architecture : ERD and schema : DFD and UML : UI/UX tokens
    section Build
      Ingestion and compliance : Cleaning and dedupe : Warehouse and views
      REST API : React dashboard : Airflow DAGs
    section Harden
      12 DQ rules : 636 backend tests : 67 frontend tests : CI/CD
    section Ship
      v1.14.0 release : 39 documents : Infographic : Demo video
```

## 5. Mindmap — capability map

```mermaid
mindmap
  root((Product Intelligence))
    Ingestion
      robots.txt gate
      rate limiter
      34 sources
      BeautifulSoup + Scrapy
    Transform
      name and category cleaning
      currency and price normalisation
      rating and availability parsing
      fuzzy dedupe
    Warehouse
      dim_product
      fact_price_snapshot
      change events
      23 analytical views
    Quality
      12 enforced rules
      no-fake audit
      schema drift checks
    Serving
      222 REST operations
      React dashboard
      exports and webhooks
    Orchestration
      Airflow DAG
      backfill DAG
      DQ monitor DAG
```

## 6. Pie — warehouse object mix

```mermaid
pie showData
    title Warehouse analytical objects
    "Tables" : 29
    "Analytical views" : 23
```

## 7. GitGraph — branching strategy

```mermaid
gitGraph
    commit id: "initial"
    branch develop
    checkout develop
    commit id: "ingestion"
    branch feature/dq-rules
    checkout feature/dq-rules
    commit id: "12-rules"
    commit id: "regression-tests"
    checkout develop
    merge feature/dq-rules
    commit id: "dashboard-themes"
    checkout main
    merge develop
    commit id: "release" tag: "v1.14.0"
```

## 8. Requirement — traceability

```mermaid
requirementDiagram
    requirement FR001 {
        id: "FR-001"
        text: "Respect robots.txt, rate limits and website terms"
        risk: high
        verifymethod: test
    }
    requirement FR002 {
        id: "FR-002"
        text: "Extract name, category, price, rating, availability and URL"
        risk: medium
        verifymethod: test
    }
    requirement FR003 {
        id: "FR-003"
        text: "Detect exact and fuzzy duplicate products"
        risk: medium
        verifymethod: test
    }
    requirement FR004 {
        id: "FR-004"
        text: "Store historical price snapshots and identify changes"
        risk: high
        verifymethod: test
    }
    requirement NFR001 {
        id: "NFR-001"
        text: "Serve light and dark themes with mobile-responsive navigation"
        risk: low
        verifymethod: test
    }
    FR001 - satisfies -> FR002
    FR002 - satisfies -> FR003
    FR003 - satisfies -> FR004
    NFR001 - satisfies -> FR004
```

---

## 9. Quadrant chart — source portfolio posture (price richness vs. volatility)

```mermaid
quadrantChart
    title Source Catalog Matrix — Price Richness vs. Volatility
    x-axis Sparse Catalog Metadata --> Full Price + Rating Feeds
    y-axis Static / Batch Updates --> High-Frequency Intraday Volatility
    quadrant-1 Live Market Movers
    quadrant-2 High-Velocity Monitors
    quadrant-3 Reference & Metadata Catalogs
    quadrant-4 Structured Storefront APIs
    Kraken Tickers: [0.88, 0.92]
    Bitstamp Tickers: [0.82, 0.86]
    CheapShark Deals: [0.86, 0.72]
    Steam Store: [0.80, 0.62]
    iTunes Apps: [0.84, 0.44]
    OpenFoodFacts Prices: [0.72, 0.56]
    Scryfall Cards: [0.68, 0.48]
    PokemonTCG Cards: [0.66, 0.36]
    Open Library: [0.22, 0.18]
    Gutendex Books: [0.20, 0.14]
    Internet Archive Texts: [0.25, 0.22]
    Books to Scrape Sandbox: [0.64, 0.15]
```

## 10. Sequence — Airflow SQLAlchemy 1.4 to FastAPI 2.0 `call_pipeline` bridge

```mermaid
sequenceDiagram
    autonumber
    participant SCH as Airflow Scheduler (SQLAlchemy 1.4)
    participant DAG as DAG product_intelligence_pipeline
    participant API as FastAPI Service (SQLAlchemy 2.0)
    participant ETL as 9-Stage Pipeline.run()
    participant DB as PostgreSQL 16 / MySQL 8.4

    SCH->>DAG: Trigger daily schedule (0 3 * * *)
    DAG->>DAG: check_database_health (ShortCircuit)
    DAG->>DAG: check_source_compliance (robots.txt)
    DAG->>API: call_pipeline fallback POST /api/v1/pipeline/run/sync
    API->>ETL: Execute stages extract -> stage -> transform -> resolve -> load -> detect -> aggregate -> reconcile -> quality
    ETL->>DB: Commit immutable snapshots + DQ verdicts + audit rows
    DB-->>API: PipelineResult counters & timings
    API-->>DAG: JSON summary (XCom)
    DAG->>DAG: branch_changes (notify_users vs skip_notifications)
    DAG->>API: publish_report (TriggerRule.ALL_DONE)
```

## 11. State diagram — durable background job & backfill lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued: POST /jobs/export or /pipeline/backfill
    queued --> running: Worker claims lease (worker_id, heartbeat)
    running --> running: Stage progress emitted + SSE broadcast
    running --> cancelling: User requests cancel (cancel_requested=true)
    cancelling --> cancelled: Safe checkpoint reached
    running --> succeeded: All days / rows processed cleanly
    running --> failed: Unrecoverable exception or lease expired
    failed --> queued: Exponential retry within max_attempts
    succeeded --> [*]
    cancelled --> [*]
```

## 12. C4 — dynamic interactive intelligence & product comparison flow

```mermaid
C4Dynamic
    title Dynamic Flow — Analytics Rollup, Forecast & Side-by-Side Comparison
    Person(analyst, "Analyst", "Uses React 19 UI (/analytics, /forecast, /compare)")
    Container(spa, "React 19 SPA", "TanStack Query + Recharts", "Silent reload + URL state")
    Container(api, "FastAPI Routers", "analytics, forecast, products", "JWT + RBAC + Rate Limiter")
    ContainerDb(wh, "Kimball Warehouse", "PostgreSQL 16 / MySQL 8.4", "agg_category_daily, fact_price_snapshot")

    Rel(analyst, spa, "Selects 30d window & compares 4 SKUs")
    Rel(spa, api, "1. GET /analytics/kpi + /categories")
    Rel(api, wh, "2. Reads rebuild_category_daily_aggregates() rollup & views")
    Rel(spa, api, "3. GET /forecast/{id}?horizon=7")
    Rel(api, wh, "4. Runs damped Holt-Winters + Z-score anomaly scan")
    Rel(spa, api, "5. GET /products/{id} + /history (parallel)")
    Rel(api, spa, "6. JSON series rendered with Markdown export")
```

---

## Why these twelve

| Type | Question it answers |
| --- | --- |
| C4 context | Who talks to the system and why? |
| C4 container | What runs where, and how do the pieces connect? |
| C4 dynamic | How do runtime UI requests resolve across API & warehouse? |
| Journey | How does a user actually move through it? |
| Timeline | In what order was it delivered? |
| Mindmap | What capabilities exist, grouped? |
| Pie | What is the analytical surface made of? |
| GitGraph | How does the branching strategy work? |
| Requirement | Which requirements trace to which guarantees? |
| Quadrant | How do all 34 sources split across richness and volatility? |
| Sequence (Airflow bridge) | How does Airflow 2.10 cleanly drive FastAPI across SQLAlchemy 1.4/2.0? |
| State (background jobs) | How do durable leases, cancellation, and retries behave? |

Together with the existing flowchart / sequence / state / ER / class / Gantt
diagrams, the project covers the complete architectural documentation spectrum.
