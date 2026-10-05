# 18 — Presentation Outline

## Purpose

This document is the defence script for the Web-to-Warehouse Product Intelligence Pipeline. It
contains a slide-by-slide outline of the final presentation (with the message each slide must land),
speaker notes, an anticipated question-and-answer preparation sheet, and a three-minute live
demonstration script with the exact commands and URLs to type.

---

## Table of contents

1. [Presentation parameters](#1-presentation-parameters)
2. [Slide deck (18 slides)](#2-slide-deck-18-slides)
3. [Q&A preparation](#3-qa-preparation)
4. [Three-minute demo script](#4-three-minute-demo-script)
5. [Rehearsal plan](#5-rehearsal-plan)
6. [Backup plan if the demo fails](#6-backup-plan-if-the-demo-fails)

---

## 1. Presentation parameters

| Parameter | Plan |
| --- | --- |
| Total time | 15 minutes presentation + 5 minutes questions |
| Deck | 18 slides (target 45 seconds each) |
| Live demo | 3 minutes, integrated after slide 11 |
| Audience | Examination committee: academic supervisor, data-engineering panel, industry observer |
| Style | Problem → solution → evidence; every claim has a number and a command |
| Visual language | Mermaid diagrams rendered by GitHub or `make docs-render`; no stock imagery |
| Backup | Pre-recorded screenshots of each screen + the CLI report output in a text file |

---

## 2. Slide deck (18 slides)

### Slide 1 — Title

**On screen:** Project title, track, name, supervisor, date, repository link (private), one-line
abstract.

> "Web-to-Warehouse Product Intelligence Pipeline. A compliant, orchestrated and testable ETL
> platform that turns permitted public web sources into a dimensional warehouse with full price
> history, duplicate resolution, catalog reconciliation and a measured data-quality posture."

**Speaker note:** 20 seconds. Do not read the abstract aloud; state the problem in one sentence and
move on.

### Slide 2 — The problem

**On screen:** The six pain points from `docs/07` §2.2 as a table; the cost in analyst hours; the
question nobody can answer today.

**Message:** Manual collection is slow, inconsistent and destroys history.

> "A merchandising team spends 6–10 hours a week copying prices into spreadsheets. Nobody can answer
> 'what did this product cost last March?' because the history does not exist."

### Slide 3 — Objectives and scope

**On screen:** The ten objectives from `docs/01` §2 with their targets; the out-of-scope list
(streaming, ML, personal data, bypass of protections).

**Message:** Ten measurable objectives; five deliberate exclusions.

### Slide 4 — Compliance position

**On screen:** The seven robots/terms principles; the decision table for all five sources.

> "Politeness is not the scraper's job — it is the transport layer's job. `CompliantHttpClient` asks
> `RobotsCache` before every request, so a new source cannot forget to comply. RFC 9309's fallback
> rules are implemented literally: 4xx means allow, 401/403 means disallow."

**Anticipated question:** "What if a site forbids scraping?" — Answer: the source is disabled, the run
degrades to `partial`, and the reason is recorded in `dim_source.terms_allowed`.

### Slide 5 — Architecture

**On screen:** The component diagram from `docs/08` §5.1 (simplified to one box per layer).

**Message:** Layered batch ETL plus a read-only serving API.

> "Nine pipeline stages, five ingestion sources, five conformed dimensions, twenty views, one semantic
> layer, 104 API operations. The pipeline is a plain Python object: the CLI, the API and Airflow all
> call the same `Pipeline.run()`."

### Slide 6 — Data model

**On screen:** The star schema plus the change feeds; the grain of each fact table; the normalisation
argument in three bullets.

**Message:** Kimball's grain-first rule; 3NF dimensions, deliberate denormalisation in the facts.

> "`fact_price_snapshot` is append-only with a declared grain — one row per product per source per run
> — and a unique constraint enforces it. That single decision makes the `LAG()`-based movement analysis
> valid, and it is checked by the critical rule DQ006."

### Slide 7 — Preparation and deduplication

**On screen:** The similarity formula; the digit-signature example (`Canon EOS R6` vs `R5`); the
blocking diagram.

**Message:** Six measures blended, with a guard that protects against the classic false merge.

> "Six string measures are blended with published weights, then a digit-signature factor penalises any
> difference in model numbers. That is what keeps two camera bodies apart, and it is measured: R6 vs R5
> scores 0.81, below the 0.90 threshold."

### Slide 8 — Change detection and reconciliation

**On screen:** The four event types with the measured event mix; the three-stage reconciliation
cascade with the 39/57 result.

**Message:** Price history, four change classes and a quantified market position.

### Slide 9 — Data quality

**On screen:** The six dimensions, the 12 rules, the severity-weighted score formula, and the measured
report (98.26, 22 pass / 2 warn / 0 fail).

**Message:** Quality is measured per run, persisted, and only critical failures block.

> "The score is severity-weighted, and only `critical` rules can fail a run. Rules execute inside a
> savepoint, so a broken rule degrades to a recorded failure instead of killing the load."

### Slide 10 — Orchestration and operations

**On screen:** The Airflow DAG with its guards and branch; the CLI command list.

**Message:** One library, three entry points; recoverable tasks; a full CLI for the terminal.

### Slide 11 — API and security

**On screen:** Router table with counts; the role matrix; the token and API-key flows.

**Message:** 113 documented operations behind JWT + RBAC; 78 automated regression checks.

### Slide 12 — Live demo (3 minutes)

**On screen:** The browser and a terminal. Use the script in §4 exactly.

**Message:** "Here is the system, end to end, in three minutes."

### Slide 13 — Results

**On screen:** The measured results table (from `docs/05` §3) — DQ 98.26 on two engines, 39/57 catalog
match rate, p95 ≤ 38.2 ms, 3.5 s run, 0 structural drift, 78/78 checks.

**Message:** Every number was produced by a command in front of the panel.

### Slide 14 — Engineering challenges solved

**On screen:** Four challenges with cause → fix → measured effect:

| Challenge | Fix | Effect |
| --- | --- | --- |
| Reconciliation too slow | Blocking index + rare-token fallback | 2,975 ms → 104 ms (29×) |
| One model, two engines | Portable types, per-statement view DDL, read-then-write upserts | 0 structural drift, identical DQ score |
| A failing source killed the run | Per-source isolation | Run becomes `partial`, data stays usable |
| MySQL DDL invalidates savepoints | One transaction per view statement | 20/20 views on both engines |

### Slide 15 — Limitations and known issues

**On screen:** The five known issues from `docs/15` §10.4, especially the MySQL `TRIGGER` reserved-word
defect, and the missing committed unit-test suite.

**Message:** Saying what is not finished is part of finishing.

### Slide 16 — Evaluation against the rubric

**On screen:** The self-assessment table from `docs/20` §4.

### Slide 17 — Future work

**On screen:** Six items with effort and benefit (from `docs/20` §2): incremental sync, partitioned
fact table, provider-backed FX, an alerting service, a committed test suite, ML forecasting.

### Slide 18 — Conclusion and questions

**On screen:** One sentence per contribution; contact; repository; "Questions?"

> "One pipeline, five permitted sources, 23 tables, 20 views, 12 quality rules, 104 API operations,
> two database engines, and a compliance trail for every request we made."

---

## 3. Q&A preparation

| Likely question | Short answer | Evidence to show |
| --- | --- | --- |
| Why is scraping the right approach instead of supplier feeds? | Feeds are per-supplier, per-format and usually paid; the sandbox sites used here are published for exactly this purpose, so the engineering problem can be studied legally | `app/ingestion/sources/books_to_scrape.py` docstring; `docs/01` §8.2 |
| How do you know you are not breaking the law? | Compliance is enforced in the transport layer, the terms position is recorded per source, and every request is audited with its robots decision | `RobotsCache`, `ingestion_http_log`, `GET /api/v1/audit/compliance` |
| How accurate is your deduplication? | 14/14 on the project's curated pair set at threshold 0.90; six measures blended; a digit-signature guard handles model numbers; the score and breakdown are stored per product and exposed by the API | `docs/05` §7.1, `GET /api/v1/products/{id}/duplicates` |
| How do you avoid false merges? | The digit-signature factor penalises differing numeric runs; the brand term is weighted 12 %; the category adds at most 3 %; a merge is reversible because the absorbed row keeps `matched_product_id` | `dedupe.py`, `dim_product.matched_product_id` |
| What is the data quality of the warehouse? | A severity-weighted 98.26 out of 100 across 12 rules and 6 dimensions, persisted per run; two warnings are explained and no blocking failure | `GET /api/v1/quality/latest` |
| Why a star schema and not a flat table? | Facts stay small, dimensions are reused across three facts, and 20 views hide the joins so analysts never write them | `db/views.sql`, `vw_daily_kpis` |
| Why support MySQL as well as PostgreSQL? | The retailer may not choose the engine; the same model loads on both with no vendor SQL, and the DQ score is identical — that is a portability guarantee, not a claim | `make verify-dialects` |
| How do you handle timezones and money? | One `UTCDateTime` decorator normalises every timestamp at the boundary; money is `NUMERIC(18,4)` and the FX rate used is stored with each observation | `app/models/base.py` |
| What happens if a source breaks? | The run degrades to `partial`, the failure is a warning, the sync state records consecutive failures, and after three the source is disabled | `pipeline._process_source`, `sync_state` |
| How is performance maintained as the catalogue grows? | Blocking bounds the comparison set, dimensions are cached, facts are batched, and `preload_latest` removes the N+1 pattern; the reconciliation went from 3 s to 104 ms with identical results | `docs/09` §7, `docs/17` §9 |
| How do you secure the API? | Argon2id, HS256 JWT with type and issuer validation, three roles with ten rights, hashed revocable API keys, an audit trail, and a read-only SQL console that rejects writes before execution | `app/api/security.py`, `scripts/api_smoke.py` |
| Why is the dashboard not in the repository? | The delivered repository snapshot contains the API and the specification for every screen (doc 12); each screen is mapped to the endpoints that back it, and the API smoke suite verifies the same journeys | `docs/12`, `docs/16` |
| What would you do differently? | Commit the unit suite, partition the fact table, replace the static FX table with a provider, and enforce the retention job | `docs/20` |
| How would this scale to 100,000 SKUs? | Partition by month, persist a sorted-neighbourhood index for blocking, raise the candidate pool, add a read replica for the dashboard and move Airflow to a distributed executor | `docs/13` §10 |
| What is your contribution? | End-to-end: the compliance layer, the cleaning and normalisation, the deduplication engine with its blocking optimisation, the dimensional model and views, the DQ framework, the API with RBAC, the orchestration and this documentation set | `docs/19` |

**Three rules for the Q&A:** answer in one sentence first; give the file path second; run the command
third. If you do not know, say "I would measure that" and name the measurement.

---

## 4. Three-minute demo script

### 4.1 Preparation (before the defence, 5 minutes)

```bash
cd /home/ahmed/Downloads/Depi_Ahmed_Abobakr_Project
make db-wait                    # both databases healthy
pip-cli status | tail -20       # row counts and the last runs
pip-cli serve --port 8000 > var/demo-api.log 2>&1 &    # API on 8000
sleep 6
curl -s localhost:8000/api/v1/health | head -c 200; echo
# Open two browser tabs: http://localhost:8000/docs and the dashboard (http://localhost:5173)
# Sign in as admin@example.com / Admin@12345
```

### 4.2 The script, minute by minute

**0:00–0:30 — Prove the warehouse exists (terminal)**

```bash
pip-cli status | head -25
```

Say: "23 tables, 20 views, 66 products, 8,302 price snapshots over 150 days."

**0:30–1:00 — Run the pipeline live (terminal)**

```bash
pip-cli run-pipeline --sources local_demo,dummyjson_products --limit 25 --quiet
```

Say: "One command. Nine instrumented stages, compliance-gated extraction, dedupe, change detection,
catalog reconciliation and twelve quality rules. It finished in under four seconds."

**1:00–1:30 — Show the run detail (browser: Pipeline screen, or terminal)**

```bash
pip-cli report --days 30 --limit 5
```

Say: "Top movers, category drift and the quality report — all of it SQL, no hard-coded numbers."

**1:30–2:00 — Dashboard (browser)**

Open `http://localhost:5173`. Point at the KPI cards, then the price-change timeline, then the
category breakdown. Say: "Sixty-six products, 1,608 price changes in the window, DQ score 98.26, and
195 of 285 catalog rows matched."

**2:00–2:30 — Product detail and duplicates (browser)**

Open Products → *Samsung 4K Smart TV 55 inch Plus*. Say: "Price history with 150 observations. The
match strategy is shown — this product was merged with a fuzzy match at 0.98." Open the Duplicate
candidates tab: "and here is the score breakdown for every near match."

**2:30–2:50 — Quality and compliance (browser)**

Open Quality: "12 rules, 6 dimensions, score 98.26, two warnings explained." Open Compliance: "Every
outbound request is logged with its robots decision — zero unlogged requests."

**2:50–3:00 — The API (browser: `http://localhost:8000/docs`)**

Say: "113 documented operations, JWT plus role-based access, and 78 automated checks that exercise all
of it — including the 401 and the 403."

### 4.3 Optional 20-second flourish: cross-dialect parity

```bash
pip-cli verify
```

Say: "The same model, the same data, two engines — zero structural drift and an identical data-quality
score of 98.26 on PostgreSQL 16 and MySQL 8.4."

### 4.4 Backup: the same story with `curl`

If the dashboard is unavailable, the demo still works:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"Admin@12345"}' | jq -r .access_token)

curl -s "localhost:8000/api/v1/analytics/kpi?days=30" -H "Authorization: Bearer $TOKEN" \
  | jq '{products: .latest.products, changes: .changes.total_changes, dq: .quality.dq_score, catalog: .catalog}'

curl -s "localhost:8000/api/v1/changes/price?days=90&significant_only=true&page_size=3" \
  -H "Authorization: Bearer $TOKEN" | jq '.items[] | {name: .canonical_name, change: .change_pct}'

curl -s "localhost:8000/api/v1/audit/compliance?days=7" -H "Authorization: Bearer $TOKEN" | jq
```

---

## 5. Rehearsal plan

| Rehearsal | Duration | Focus | Success criterion |
| --- | --- | --- | --- |
| R1 — Content | 45 min | Slides 1–18 spoken aloud, timing each slide | Within 15 minutes, no slide over 60 seconds |
| R2 — Q&A | 30 min | The 15 questions in §3 answered from memory, then with notes | Each answer under 30 seconds with a file path |
| R3 — Demo dry run | 20 min | The full §4 script twice, cold | Under 3 minutes, no unexplained waiting |
| R4 — Failure drill | 15 min | Kill the API, kill the database, block the network | Demonstrate the fallback in §6 without panic |
| R5 — Final | 15 min | Full run-through standing up, no notes | Clean, and the demo fits inside the slot |

**Rehearsal checklist**

- [ ] Terminal font size increased; `PYTHONPATH` correct; the working directory is the project root
- [ ] Browser zoom at 100 %, dashboard tab already signed in, devtools closed
- [ ] `pip-cli status` and `pip-cli report` executed once so the output is warm
- [ ] Screenshots of every screen exported to the backup slide deck
- [ ] CLI report output saved to `var/artifacts/demo-report.txt` as text backup
- [ ] Laptop power supply, screen sharing tested, presentation file exported as PDF as well

---

## 6. Backup plan if the demo fails

| Failure | Immediate action | Narration to use |
| --- | --- | --- |
| API does not start | `pip-cli status`; check the port; start with `--port 8001` and use `curl` | "Let me show the same evidence through the CLI, which uses the same code." |
| Database is down | `make db-wait`; if that fails, show the SQLite fallback: `ACTIVE_DATABASE=sqlite` | "The warehouse is the same model; only the engine differs." |
| No internet | Use `--sources local_demo` — the synthetic source needs no network | "This is the offline source; it is how the project is demonstrated without internet access." |
| Dashboard is blank | Switch to Swagger UI at `/docs` and run `GET /analytics/kpi` | "Here is the same contract the dashboard consumes." |
| Everything fails | Present the results slide with the measured table from `docs/05` §3 | "These numbers were measured and re-measurable; the commands are in the documentation." |

**Never** spend more than 30 seconds recovering on stage. Switch to the backup narrative and continue
with slides 13–18.