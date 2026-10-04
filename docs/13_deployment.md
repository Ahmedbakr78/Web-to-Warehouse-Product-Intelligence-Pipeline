# 13 — Deployment

## Purpose

This document describes how the Web-to-Warehouse Product Intelligence Pipeline is built, configured,
run and operated. It lists the technology stack, shows the deployment and component diagrams,
defines the environment matrix (development / testing / production), documents every Docker Compose
service and port, describes secrets management, backup and restore, the scaling and high-availability
options, and the CI/CD pipeline.

---

## Table of contents

1. [Technology stack](#1-technology-stack)
2. [Deployment diagram](#2-deployment-diagram)
3. [Component and dependency diagram](#3-component-and-dependency-diagram)
4. [Environment matrix](#4-environment-matrix)
5. [Docker Compose services](#5-docker-compose-services)
6. [Ports and endpoints](#6-ports-and-endpoints)
7. [Installation and run order](#7-installation-and-run-order)
8. [Secrets management](#8-secrets-management)
9. [Backup and restore](#9-backup-and-restore)
10. [Scaling and high availability](#10-scaling-and-high-availability)
11. [Monitoring and operations](#11-monitoring-and-operations)
12. [CI/CD](#12-cicd)
13. [Deployment caveats](#13-deployment-caveats)

---

## 1. Technology stack

### 1.1 Application stack

| Layer | Technology | Version | Role in the project |
| --- | --- | --- | --- |
| Language | Python | 3.12 (floor 3.10) | Whole backend, ETL and API |
| Web framework | FastAPI | ≥ 0.115 | REST API, OpenAPI, dependency injection |
| ASGI server | Uvicorn | ≥ 0.30 | Serves the app (`make serve`, `make serve-prod`, Compose `api`) |
| Data validation | Pydantic | ≥ 2.7 | Request/response models, `Settings` |
| Settings | pydantic-settings | ≥ 2.3 | Validated environment configuration |
| ORM | SQLAlchemy | ≥ 2.0.30 | Models, sessions, engines, portable SQL |
| PostgreSQL driver | psycopg2-binary | ≥ 2.9 | Primary warehouse |
| MySQL driver | PyMySQL (+ cryptography) | ≥ 1.1 | Secondary warehouse target |
| HTTP client | httpx | ≥ 0.27 | Compliant outbound requests |
| HTML parsing | BeautifulSoup4 + lxml (+ lxml-html-clean) | ≥ 4.12 / ≥ 5.2 | The books.toscrape.com scraper |
| Scheduling | Apache Airflow | 2.10.5, LocalExecutor | DAG orchestration |
| Auth tokens | PyJWT | ≥ 2.8 | HS256 access/refresh tokens |
| Password hashing | argon2-cffi | ≥ 23.1 | Argon2id (memory-hard) |
| CLI | Typer + Rich | ≥ 0.12 / ≥ 13.7 | Operator interface with formatted tables |
| Retry | tenacity | ≥ 8.3 | Reserved for extension points |
| Logging | stdlib logging + custom formatters | — | ANSI console and JSON output |
| Serialisation | orjson | ≥ 3.10 | Fast JSON responses (available for deployment tuning) |
| Containerisation | Docker + Docker Compose | v2 | Databases, API, Airflow, frontend |
| Tests | pytest, pytest-cov | ≥ 8.0 / ≥ 5.0 | Test harness (`make test`, `make test-cov`) |
| Lint / types | ruff, mypy | ≥ 0.5 / ≥ 1.10 | `make lint`, `make typecheck` |

### 1.2 Front-end stack

| Technology | Version | Role |
| --- | --- | --- |
| React | 19 | Component model |
| Vite | 5+ | Dev server and production bundle |
| TypeScript | 5+ | Static typing of API payloads |
| Tailwind CSS | 3+ | Utility styling driven by the colour tokens in doc 12 |
| TanStack Query | 5 | Server-state caching, invalidation after a run |
| Recharts | 2+ | Line, bar, stacked-bar and diverging charts |
| lucide-react | latest | Icon set (16 px, stroke 1.75) |
| nginx (alpine) | stable | Static hosting of the production bundle |

### 1.3 Data and storage stack

| Technology | Version | Role |
| --- | --- | --- |
| PostgreSQL | 16-alpine | Primary analytical warehouse |
| MySQL | 8.4 | Secondary warehouse target for cross-dialect verification |
| SQLite | 3.35+ | Optional local fallback (`var/pipeline.sqlite3`) |
| Airflow metadata DB | PostgreSQL | Scheduler state, run history in the Airflow UI |

### 1.4 External data sources

| Source | Endpoint | Licence / terms | Budget |
| --- | --- | --- | --- |
| DummyJSON | `https://dummyjson.com/products` | Public test API | Free |
| FakeStore | `https://fakestoreapi.com/products` | Public demo API | Free |
| Open Library | `https://openlibrary.org/search.json` | Open bibliographic data | Free |
| books.toscrape.com | `https://books.toscrape.com/` | Sandbox published for scraping practice; non-commercial | Free |
| Local demo catalogue | `local://demo-catalogue` | Generated in-process | Free |

---

## 2. Deployment diagram

```mermaid
flowchart TB
    subgraph EDGE["Edge"]
        B["Browser<br/>React SPA served by nginx :80"]
        CLI["Operator shell<br/>curl / Python / CLI"]
    end

    subgraph HOST["Single application host"]
        direction TB
        subgraph SERVE["Serving tier"]
            NG["nginx<br/>static bundle + /api proxy"]
            API1["uvicorn worker 1<br/>FastAPI :8000"]
            API2["uvicorn worker 2<br/>FastAPI :8000"]
        end
        subgraph SCHED["Scheduling tier"]
            AFB["airflow webserver :8080"]
            AFS["airflow scheduler"]
            AFX["task processes LocalExecutor"]
        end
        subgraph JOBS["Batch tier"]
            JOB["python -m app.cli.main<br/>run-pipeline / bootstrap / seed"]
        end
        FS[("Filesystem var/<br/>http-cache, logs, artifacts")]
    end

    subgraph DATA["Data tier"]
        PG[("PostgreSQL 16<br/>:5432")]
        MY[("MySQL 8.4<br/>:3306")]
        VOL[("Docker volumes<br/>pg_data, mysql_data,<br/>airflow_logs")]
    end

    EXT["External sources<br/>DummyJSON, FakeStore,<br/>Open Library, books.toscrape.com"]

    B --> NG
    NG --> API1
    NG --> API2
    CLI --> API1
    AFB --> AFS
    AFS --> AFX
    AFX --> JOB
    API1 --> PG
    API2 --> PG
    API1 -.-> MY
    API2 -.-> MY
    AFB --> PG
    AFX --> PG
    JOB --> PG
    JOB -.-> MY
    PG --> VOL
    MY --> VOL
    API1 <--> FS
    API2 <--> FS
    JOB <--> FS
    AFX --> EXT
    JOB --> EXT
```

### 2.1 Deployment tiers and their responsibilities

| Tier | Process | Scaling unit | State |
| --- | --- | --- | --- |
| Edge | nginx serving the built SPA | Static, horizontally scalable | None |
| Serving | uvicorn workers running `app.api.main:app` | Process count (`--workers`) | Stateless; JWT is self-contained |
| Scheduling | Airflow webserver + scheduler + task processes | Executor choice | Airflow metadata DB |
| Batch | One-shot CLI invocations | Job queue (Airflow) or manual | Filesystem cache |
| Data | PostgreSQL / MySQL | Vertical, then read replicas | Durable volumes |

---

## 3. Component and dependency diagram

```mermaid
flowchart TB
    subgraph BACK["Backend package app"]
        direction LR
        CORE["app.core<br/>config, db, errors, logging"]
        ING["app.ingestion<br/>base, cleaning, dedupe,<br/>robots, ratelimit, http_client, sources"]
        ETL["app.etl<br/>pipeline, loader, dq,<br/>catalog_reconcile, bootstrap, seed"]
        ANA["app.analytics<br/>service"]
        API["app.api<br/>main, deps, security,<br/>schemas, 15 routers"]
        MODELS["app.models<br/>base, dimensions, facts,<br/>operations, catalog, app_users"]
        CLIM["app.cli<br/>main"]
    end

    subgraph ASSETS["Repository assets"]
        SQL[("db/views.sql<br/>20 views")]
        DAG["dags/product_intelligence_pipeline.py"]
        MK["Makefile"]
        ENV[(".env.example")]
        SMOKE["scripts/api_smoke.py"]
        CFG["pyproject.toml"]
    end

    CORE --> MODELS
    ING --> CORE
    ING --> MODELS
    ETL --> CORE
    ETL --> ING
    ETL --> MODELS
    ANA --> MODELS
    API --> ANA
    API --> ETL
    API --> MODELS
    API --> CORE
    CLIM --> ETL
    CLIM --> API
    CLIM --> CORE
    ETL --> SQL
    MK --> CLIM
    MK --> DAG
    SMOKE --> API
    CFG --> CORE
```

### 3.1 Dependency rules (enforced by review, not by tooling)

| Rule | Reason |
| --- | --- |
| `app.ingestion` must not import `app.etl`, `app.analytics` or `app.api` | Ingestion is reusable and must stay independent of serving |
| `app.ingestion.cleaning` and `app.ingestion.dedupe` must not import `app.core.db` or `httpx` | They must stay pure so they can be unit tested without I/O |
| `app.analytics` must not import `app.api` | The service layer is the single source of analytical SQL |
| `app.api` must not contain business rules | Routers validate, delegate and serialise |
| `db/views.sql` is the only place analytical joins are defined | One semantic layer |
| No module may import Airflow outside `dags/` | The DAG must be optional |

---

## 4. Environment matrix

| Variable | Development | Testing | Production | Notes |
| --- | --- | --- | --- | --- |
| `APP_ENV` | `development` | `testing` | `production` | Drives `is_production`, demo-account exposure |
| `APP_DEBUG` | `true` | `true` | `false` | Controls stack traces in 500 responses |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `8000` | `127.0.0.1` / `8099` | `0.0.0.0` / `8000` | Smoke test uses 8099 |
| `APP_LOG_LEVEL` | `INFO` | `DEBUG` | `INFO` | |
| `APP_LOG_FORMAT` | `text` | `text` | `json` | JSON for log shippers |
| `DATABASE_URL` | `postgresql+psycopg2://pip:pip@localhost:5432/pipeline` | `sqlite:///var/test.sqlite3` | secret manager reference | Never hard-coded |
| `MYSQL_URL` | `mysql+pymysql://pip:pip@localhost:3306/pipeline?charset=utf8mb4` | unset | secret manager reference | Needed for cross-dialect verification |
| `ACTIVE_DATABASE` | `postgres` | `sqlite` | `postgres` | `--database` overrides per invocation |
| `DB_SCHEMA` | `public` | `public` | `public` | Created on PostgreSQL only |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_RECYCLE` | 10 / 20 / 1800 | 5 / 5 / 900 | 20 / 40 / 1800 | Larger pool with more API workers |
| `DB_STATEMENT_TIMEOUT_MS` | 30,000 | 30,000 | 15,000 | PostgreSQL `statement_timeout` |
| `DB_ECHO` | `false` | `false` | `false` | Never enable in production |
| `SECRET_KEY` | development placeholder | test key | 32+ random bytes from the secret manager | Rotating it invalidates all tokens |
| `JWT_ALGORITHM` | `HS256` | `HS256` | `HS256` (or RS256 with a key pair) | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | `60` | `480` | 8 h in production |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | `1` | `14` | |
| `CORS_ORIGINS` | `http://localhost:5173,…` | `http://localhost:5173` | exact dashboard origin | No wildcard with credentials |
| `SEED_*_EMAIL/PASSWORD` | documented demo accounts | unused | unset | `SEED_DEMO_DATA=false` in production |
| `INGEST_USER_AGENT` | project bot with a contact address | same | same + real contact | Honesty requirement |
| `RESPECT_ROBOTS_TXT` | `true` | `true` | `true` | Must never be `false` in production |
| `RESPECT_TERMS_WHITELIST` | `true` | `true` | `true` | Must never be `false` in production |
| `REQUESTS_PER_MINUTE` / `REQUESTS_PER_SECOND` | 30 / 1.0 | 30 / 1.0 | 30 / 1.0 | Per host; sources may lower it further |
| `CRAWL_DELAY_FALLBACK_SECONDS` | `2.0` | `2.0` | `2.0` | |
| `MAX_CONCURRENT_REQUESTS` | `4` | `4` | `8` | httpx connection limit |
| `CACHE_ENABLED` / `CACHE_TTL_SECONDS` | `true` / `1800` | `true` / `60` | `true` / `1800` | |
| `MAX_RETRIES` / `RETRY_BACKOFF_SECONDS` | `3` / `1.5` | `1` / `0.1` | `3` / `1.5` | |
| `PIPELINE_BATCH_SIZE` | `500` | `100` | `500` | Staging and load batch size |
| `PIPELINE_FAIL_FAST` | `false` | `true` | `false` | Strict fail-fast in CI |
| `DEDUPE_SIMILARITY_THRESHOLD` | `0.90` | `0.90` | `0.90` | Validated to 0–1 at startup |
| `DEDUPE_BLOCKING_KEY_LENGTH` / `DEDUPE_CANDIDATE_LIMIT` | `4` / `25` | `4` / `25` | `5` / `40` | Wider pool for larger catalogues |
| `MAX_PRODUCTS_PER_SOURCE` | `400` | `10` | `400` | API trigger caps at 5,000 |
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | `http://127.0.0.1:8099/api/v1` | `https://<host>/api/v1` | Baked into the bundle at build time |

---

## 5. Docker Compose services

`docker-compose.yml` defines six services on one user-defined bridge network (`pipnet`) with four
named volumes.

| Service | Image / build | Purpose | Depends on | Health check |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | Primary warehouse; also stores the Airflow metadata DB | — | `pg_isready -U pip -d pipeline`, 5 s interval, 20 retries |
| `mysql` | `mysql:8.4` | Secondary warehouse for cross-dialect verification | — | `mysqladmin ping`, 5 s interval, 30 retries |
| `api` | build `docker/api.Dockerfile` | FastAPI on port 8000 | healthy `postgres`, healthy `mysql` | `GET /health` every 15 s, 10 retries |
| `airflow` | `apache/airflow:2.10.5-python3.12` | Webserver; runs `airflow db migrate` then creates the admin user | healthy `postgres` | none (start-up probe via depends_on) |
| `airflow-scheduler` | `apache/airflow:2.10.5-python3.12` | Scheduler that fires the DAG on schedule | started `airflow` | none |
| `frontend` | build `frontend/Dockerfile` (nginx) | Serves the built SPA on port 5173 → container port 80 | started `api` | none |

### 5.1 Notable service settings

| Service | Setting | Reason |
| --- | --- | --- |
| `postgres` | `POSTGRES_INITDB_ARGS=--data-checksums` | Detect silent corruption in a long-lived warehouse |
| `postgres` | `TZ: UTC` | One timezone everywhere |
| `mysql` | `character-set-server=utf8mb4`, `collation-server=utf8mb4_unicode_ci` | Unicode product names (e.g. `L'Oréal`, `Café`) |
| `mysql` | `innodb-buffer-pool-size=512M`, `max-connections=300` | Right-sized for the measured workload |
| `api` | `env_file: .env` plus explicit `DATABASE_URL`, `MYSQL_URL`, `CORS_ORIGINS` | Compose injects service-host names, not localhost |
| `api` | `./app:/srv/app/app:ro`, `./db:/srv/app/db:ro` | Read-only source mounts so code edits do not require a rebuild |
| `airflow` | `AIRFLOW__CORE__EXECUTOR: LocalExecutor` | Single-host execution |
| `airflow` | `AIRFLOW__CORE__LOAD_EXAMPLES: "false"` | No example DAGs |
| `airflow` | `AIRFLOW__CORE__DAG_DISCOVERY_SAFE_MODE: "false"` | Allows the DAG module to import without Airflow extras |
| `airflow` | `AIRFLOW__API__AUTH_BACKENDS: airflow.api.auth.backend.session` | Session auth for the UI |
| `airflow` | `PIP_DATABASE_URL` | Lets the DAG reach the same warehouse as the API |
| `airflow` | `AIRFLOW_UID/GID` | Aligns container file ownership with the host |
| All | `restart: unless-stopped` | Survives host reboots |

### 5.2 Volumes

| Volume | Mounted at | Contents |
| --- | --- | --- |
| `pg_data` | `/var/lib/postgresql/data` | Warehouse and Airflow metadata |
| `mysql_data` | `/var/lib/mysql` | Secondary warehouse |
| `airflow_logs` | `/opt/airflow/logs` | Task logs |
| `airflow_dags` | `/opt/airflow/dags_processed` | Processed DAG files |

### 5.3 Makefile deployment targets

| Target | Effect |
| --- | --- |
| `make up-db` | Start only `postgres` and `mysql` |
| `make db-wait` | Block until both report healthy |
| `make up` | `docker compose up -d --build` (full stack) |
| `make down` | Stop the stack, keep volumes |
| `make clean` | Stop and delete volumes (**destructive**) |
| `make ps` / `make logs` | Status and log tail |
| `make serve` / `make serve-prod` | Run the API on the host instead of a container |

---

## 6. Ports and endpoints

| Port | Service | Protocol | Exposure | Notes |
| --- | --- | --- | --- | --- |
| 5173 | Frontend (nginx in Compose, Vite in dev) | HTTP | Public | `FRONTEND_PORT` |
| 8000 | FastAPI / uvicorn | HTTP | Public behind a proxy | `APP_PORT` |
| 8000 | `/docs`, `/redoc`, `/openapi.json` | HTTP | Public | Interactive API documentation |
| 8000 | `/api/v1/*` | HTTP | Public | All 104 operations |
| 5432 | PostgreSQL | TCP | Internal only | `POSTGRES_PORT`; Airflow metadata too |
| 3306 | MySQL | TCP | Internal only | `MYSQL_PORT` |
| 33060 | MySQL X protocol | TCP | Internal only | Container-internal, not published |
| 8080 | Airflow webserver | HTTP | Internal or VPN | `AIRFLOW_PORT` |
| 8001 | Documentation server (`make docs-serve`) | HTTP | Internal | Serves `docs/` |
| 8099 | Smoke-test API instance | HTTP | Loopback | `scripts/api_smoke.py --port 8099` |
| 33060 / 8080 / 5173 / 8000 | — | — | — | Not published outside the Compose network in production |

**Production exposure recommendation.** Publish only 5173 (or 80/443 through a reverse proxy) and 8000
behind TLS; keep 5432, 3306 and 8080 on an internal network reachable only by the operator.

---

## 7. Installation and run order

### 7.1 Full local stack

```bash
cp .env.example .env                 # then edit SECRET_KEY and credentials
make install                         # venv + dependencies [postgres,mysql,dev,scrapy]
make up-db && make db-wait           # databases only
make bootstrap                       # 23 tables + 20 views + reference data
make demo-postgres                   # demo dataset (optional but recommended)
make demo-mysql                      # the same dataset on MySQL
make run-pipeline                    # one live multi-source run
make verify-dialects                 # cross-dialect comparison
make serve                           # API on http://localhost:8000/docs
```

### 7.2 Full container stack

```bash
make env
make up                              # builds api + frontend, starts everything
docker compose exec api python -m app.cli.main bootstrap
docker compose exec api python -m app.cli.main seed-demo --days 150
docker compose exec api python -m app.cli.main run-pipeline
open http://localhost:5173           # sign in with the documented demo account
```

### 7.3 Verification after deployment

```bash
curl -s localhost:8000/api/v1/health | jq '{status, database: .database.connected, tables: .database.tables}'
curl -s localhost:8000/api/v1/queries/views -H "Authorization: Bearer $TOKEN" | jq 'length'   # 20
.venv/bin/python scripts/api_smoke.py                                                        # 78 checks
```

### 7.4 Orchestration run

```bash
make install-airflow                 # apache-airflow==2.10.5 with constraints for 3.12
make airflow-init                    # metadata DB migrate + admin user (admin / admin)
make airflow-test                    # run the DAG once for a fixed logical date
# Or in the Compose stack: open http://localhost:8080, enable product_intelligence_pipeline
```

---

## 8. Secrets management

### 8.1 Classification

| Secret | Where it lives | Rotation |
| --- | --- | --- |
| `SECRET_KEY` | `.env` locally; secret manager in production | On rotation every issued token becomes invalid; planned maintenance window |
| `POSTGRES_PASSWORD`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` | `.env` / Compose environment | Rotate by updating the secret and restarting |
| `SEED_*_PASSWORD` | `.env`; documented demo values | Change on first production boot; then unset |
| `AIRFLOW_ADMIN_PASSWORD` | `.env` | Before exposing the webserver |
| API keys (`pip_…`) | Issued once, stored hashed | Revoke and re-issue |
| User passwords | Argon2id hash in `app_user.hashed_password` | User-initiated or admin reset; `password_changed_at` is recorded |

### 8.2 Controls

| Control | Implementation |
| --- | --- |
| No secrets in version control | `.env` is in `.gitignore`; only `.env.example` is committed |
| Redaction in logs | `describe_target()` masks credentials: `scheme://***:***@host` |
| Redaction in errors | `ComplianceError` details carry the URL, never the connection string |
| Least exposure | API keys store `prefix` and a SHA-256 hash with a server pepper; only the prefix is ever listed |
| Password strength | ≥ 10 characters with upper, lower, digit and symbol, enforced server-side |
| Brute-force control | 5 failed logins lock the account for 15 minutes; failures are audited |
| Transport | JWT HS256 over TLS in production; the API must not be exposed over plain HTTP |
| Rotation procedure | Change in the secret manager → restart `api` and `airflow` → re-login; see §9 for data impact (none) |

### 8.3 Production hardening checklist

- [ ] `APP_ENV=production`, `APP_DEBUG=false`, `APP_LOG_FORMAT=json`
- [ ] `SEED_DEMO_DATA=false`; demo accounts removed or rotated
- [ ] `CORS_ORIGINS` restricted to the exact dashboard origin
- [ ] `RESPECT_ROBOTS_TXT=true` and `RESPECT_TERMS_WHITELIST=true` (never disable)
- [ ] `SECRET_KEY` from the secret manager, ≥ 32 random bytes
- [ ] Database credentials with only the privileges the app needs (`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE` during bootstrap)
- [ ] API behind TLS with a request-size limit
- [ ] Backup job scheduled and a restore rehearsed

---

## 9. Backup and restore

### 9.1 What to back up

| Store | Importance | Frequency | Notes |
| --- | --- | --- | --- |
| PostgreSQL `pipeline` | Critical | Daily, plus before releases | Contains the warehouse, reference catalog and accounts |
| Airflow metadata DB | High | Daily | Run history and DAG state; can be rebuilt with `airflow db migrate` |
| MySQL `pipeline` | Medium | Daily | Only needed for cross-dialect verification |
| `app_setting` rows | Medium | With the database | Small, but holds the schedule and thresholds |
| `var/http-cache` | Low | Not required | Rebuildable; disposable |
| Repository (`docs/`, `db/`, `dags/`) | Critical | On every commit | Version control is the backup |

### 9.2 Backup

```bash
# PostgreSQL — custom format so a single-threaded restore is possible
docker compose exec -T postgres pg_dump -U pip -d pipeline -Fc \
  > "backup/pipeline-$(date +%F).dump"

# schema-only copy for environment provisioning
docker compose exec -T postgres pg_dump -U pip -d pipeline -s \
  > "backup/schema-$(date +%F).sql"

# Airflow metadata
docker compose exec -T postgres pg_dump -U pip -d postgres -Fc \
  > "backup/airflow-$(date +%F).dump"

# MySQL
docker compose exec -T mysql mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" \
  --single-transaction --routines pipeline \
  > "backup/mysql-$(date +%F).sql"

# Application configuration (non-secret keys only)
docker compose exec -T postgres psql -U pip -d pipeline -c \
  "COPY app_setting TO STDOUT WITH CSV HEADER" > "backup/app_setting-$(date +%F).csv"
```

Recommended retention: 7 daily, 4 weekly, 6 monthly, stored off-host (encrypted).

### 9.3 Restore

```bash
# 1. Stop the writers
docker compose stop api airflow airflow-scheduler

# 2. Recreate the database and restore
docker compose exec -T postgres dropdb -U pip --if-exists pipeline
docker compose exec -T postgres createdb -U pip pipeline
docker compose exec -T postgres pg_restore -U pip -d pipeline --no-owner < backup/pipeline-2026-03-20.dump

# 3. Re-apply the analytical views (idempotent, and guarantees they match db/views.sql)
docker compose exec -T postgres psql -U pip -d pipeline -c 'CREATE SCHEMA IF NOT EXISTS public'
docker compose exec api python -m app.cli.main init-db      # create_all + apply_views, checkfirst

# 4. Verify object completeness and data quality
docker compose exec api python -m app.cli.main check-schema
docker compose exec api python -m app.cli.main status

# 5. Restart and smoke-test
docker compose start api airflow airflow-scheduler
.venv/bin/python scripts/api_smoke.py
```

### 9.4 Recovery objectives and drills

| Objective | Target | Basis |
| --- | --- | --- |
| RPO | ≤ 24 h (daily dump) | The warehouse is rebuilt by the next pipeline run |
| RTO | ≤ 60 min | Restore is a single `pg_restore` plus `init-db` |
| Drill frequency | Every sprint in the final three sprints | Rehearsed on a scratch database, not on production |
| Verified recovery | Row counts compared with `app.cli.main status` | 23 tables, 20 views, DQ score equal to the recorded value |

The **fact tables are recoverable by re-running the pipeline**: because extraction is polite and
cached, a rebuild costs minutes. Only the *account* tables (`app_*`), `catalog_product`, `dim_date`
and `dim_currency` are irreplaceable by re-running, which is why they are inside the same dump.

---

## 10. Scaling and high availability

### 10.1 Serving tier

| Concern | Option | Effect | Cost |
| --- | --- | --- | --- |
| More parallelism | `uvicorn --workers N` (or Gunicorn with Uvicorn workers) | N × concurrency; API workers are stateless | Memory only |
| Process supervision | systemd unit, `restart: unless-stopped`, Kubernetes Deployment | Automatic restart | Operational |
| Multiple hosts | 2+ API replicas behind nginx | Removes a single point of failure | Load balancer |
| Session state | Already stateless (self-contained JWT) | No sticky sessions needed | Zero |
| Caching | HTTP cache for the dashboard bundle; server-side cache for `table_counts()` and `kpi_summary()` keyed by `(window, run_id)` | Removes repeated aggregate queries | Invalidation on new run |
| Database reads | PostgreSQL read replica for the analytics views | Offloads dashboard queries | Replication lag |
| Slow endpoints | Cap `page_size` at 200 and `days` at 3650 (already enforced) | Prevents accidental full scans | — |

### 10.2 Batch tier

| Concern | Option | Effect |
| --- | --- | --- |
| Longer runs | Partition by date and run sources in parallel (`ThreadPoolExecutor` over sources; the HTTP layer is thread-safe) | Wall-clock time falls roughly linearly |
| Larger catalogues | Raise `MAX_PRODUCTS_PER_SOURCE`; widen the blocking key; move the candidate index to a materialised view | Keeps comparison cost bounded |
| Faster dedupe | Replace the in-process blocking index with a sorted-neighbourhood index persisted per source | O(n log n) instead of O(n·k) |
| Airflow at scale | `CeleryExecutor` or `KubernetesExecutor` with a broker | Distributed task execution |
| Scheduling | Replace cron with `0 3 * * *` in Airflow, plus `max_active_runs=1` to prevent overlap | Already the delivered configuration |
| Backfill | `seed_history` style batch insert with `PIPELINE_BATCH_SIZE` = 5,000 | 10× faster history loading |

### 10.3 Data tier

| Concern | Option | Effect |
| --- | --- | --- |
| Read scaling | Replica + `DATABASE_URL` pointing the dashboard at the replica | Dashboard never competes with ingestion |
| Write scaling | PostgreSQL partitioning by month; archive old partitions | Keeps indexes small |
| Storage | `agg_category_daily` retained beyond the fact table | Cheaper history |
| Connection budget | Pool size = workers × 2, `pool_recycle=1800` to survive proxy timeouts | Avoids stale connections |
| MySQL parity | Keep the dialect-portable SQL; add a comparison test | No divergence |

### 10.4 Availability summary

| Component | Single point of failure? | Mitigation available |
| --- | --- | --- |
| Frontend (nginx) | No | Static; any replica works |
| API | Yes, in the single-host profile | `--workers`, then multiple replicas |
| Airflow scheduler | Yes | Retry policy, `max_active_runs=1`, manual CLI fallback |
| PostgreSQL | Yes | Daily dump, replica for reads |
| Cache directory | No | Disposable |
| Upstream sources | Yes, by nature | Degradation to `partial`, offline `local_demo` fallback |

---

## 11. Monitoring and operations

| Signal | Source | Threshold | Action |
| --- | --- | --- | --- |
| API liveness | `GET /api/v1/health` | `status != ok` | Restart the container |
| API readiness | `GET /api/v1/health/ready` | `ready = false` | Check the database and the schema |
| Object completeness | `GET /api/v1/meta/tables` | ≠ 23 tables | Run `init-db` |
| View completeness | `GET /api/v1/queries/views` | ≠ 20 views | Run `init-db` |
| Data freshness | `GET /api/v1/quality/latest` → `DQ007` | > 24 h warn, > 48 h fail | Trigger a run |
| DQ score | `GET /api/v1/quality/latest` | < 80 | Investigate the failing rules |
| Run failures | `GET /api/v1/pipeline/runs?status=failed` | Any | Read `error_message`, re-run |
| Source failures | `GET /api/v1/pipeline/sources/status` | 3 consecutive | Disable the source |
| Compliance | `GET /api/v1/audit/compliance` | `blocked_requests > 0` | Review the source terms |
| Latency | `X-Process-Time-Ms` | p95 > 500 ms | Inspect the query plan |
| Slow requests | Application log | > 2,000 ms (logged automatically) | Investigate |
| Disk | Host metrics | Cache/log growth | Prune `var/` |

### 11.1 Routine tasks

| Task | Frequency | Command |
| --- | --- | --- |
| Pipeline run | Daily 03:00 | Airflow DAG `product_intelligence_pipeline` |
| Health check | Daily | `curl -s localhost:8000/api/v1/health` |
| Backup | Daily | §9.2 |
| Cache prune | Weekly | `make clean-cache`; the TTL prunes payloads automatically |
| Schema check | After every deployment | `make check-schema` |
| Smoke test | After every deployment | `.venv/bin/python scripts/api_smoke.py` |
| Cross-dialect verification | Monthly | `make verify-dialects` |

---

## 12. CI/CD

### 12.1 Pipeline stages

```mermaid
flowchart LR
    A["Push / pull request"] --> B["Install dependencies<br/>make install"]
    B --> C["Lint and format<br/>make lint"]
    C --> D["Type check<br/>make typecheck"]
    D --> E["Unit tests<br/>make test"]
    E --> F["Start PostgreSQL and MySQL services"]
    F --> G["Bootstrap both targets<br/>make bootstrap / bootstrap-mysql"]
    G --> H["Seed and run the pipeline<br/>make demo-postgres / run-pipeline"]
    H --> I["Cross-dialect verification<br/>make verify-dialects"]
    I --> J["API smoke test<br/>scripts/api_smoke.py"]
    J --> K["Build the dashboard<br/>make frontend-build"]
    K --> L{"All green?"}
    L -->|"yes"| M["Tag release v1.0.0 and build images"]
    L -->|"no"| N["Fail with the stage name in the log"]
```

### 12.2 Quality gates

| Gate | Command | Blocking condition |
| --- | --- | --- |
| Lint | `make lint` (ruff check + format check) | Any finding |
| Types | `make typecheck` (mypy) | Any error |
| Unit tests | `make test` | Any failure |
| Coverage | `make test-cov` | Coverage below the target in `docs/15` §6 |
| Schema | `make check-schema` | Missing table |
| Dialects | `make verify-dialects` | Structural drift or differing DQ score |
| API | `scripts/api_smoke.py` | Any of the 78 checks failing |
| Frontend | `make frontend-lint`, `make frontend-build` | ESLint, `tsc` or bundling error |

### 12.3 Release artefacts

| Artefact | Produced by | Published to |
| --- | --- | --- |
| Python distribution | `pip install -e .` / `python -m build` | Package index (private) |
| API image | `docker build -f docker/api.Dockerfile .` | Container registry |
| Frontend bundle | `make frontend-build` | Served by the nginx image |
| Schema + views | `db/views.sql` | Applied by `init-db` at deploy time |
| Documentation | `docs/*.md` | GitHub (private repository) |

### 12.4 Deployment strategy

Blue/green is unnecessary for a single-warehouse batch system; a **rolling restart with a
verification step** is sufficient:

```bash
git pull --ff-only
make check                                   # lint, types, unit tests
docker compose build api frontend
docker compose up -d                         # recreate changed services
docker compose exec api python -m app.cli.main init-db
.venv/bin/python scripts/api_smoke.py        # 78 checks
docker compose exec api python -m app.cli.main status
```

If the smoke test fails, `docker compose up -d --build` restores the previous image tag, because the
schema change is additive (`create_all(checkfirst=True)` and `DROP VIEW IF EXISTS` before re-creating
the views) and no migration destroys data.

---

## 13. Deployment caveats

| # | Caveat | Impact | Recommendation |
| --- | --- | --- | --- |
| 1 | `docker-compose.yml` builds the `api` service from `docker/api.Dockerfile` and the `frontend` service from `frontend/Dockerfile`. Those build contexts are not present in this repository snapshot, so `make up` (which builds) cannot run as delivered | `make up-db`, `make bootstrap`, `make serve`, `make run-pipeline` and `scripts/api_smoke.py` are unaffected, because they only need Python and the databases | Recreate the two Dockerfiles, or deploy with `make serve` plus `make frontend-dev` |
| 2 | No CI workflow file is committed under `.github/` | The gates in §12.2 must be run locally with `make check` | Add the workflow described in §12.1 |
| 3 | `AIRFLOW_UID/GID` default to `50000:0` | On a host without that user, the Airflow logs volume may be unwritable | Set `AIRFLOW_UID=$(id -u)` in `.env` |
| 4 | `ingestion_http_log` grows with every request | Disk growth on a long-running deployment | Retention job (§8 of doc 09) |
| 5 | SQLite is a development fallback | No concurrent writers, `WAL` mode only | Never use SQLite for a production API |
| 6 | The Airflow webserver uses session auth with the default credentials in the Compose command | Not acceptable in production | Set `AIRFLOW_ADMIN_PASSWORD` and place the webserver behind SSO or a VPN |