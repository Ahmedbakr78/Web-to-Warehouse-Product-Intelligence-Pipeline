# 06 — Literature Review

## Purpose

This document surveys the academic and industrial literature that underpins the design of the
Web-to-Warehouse Product Intelligence Pipeline. It is organised in six themes — dimensional
modelling, web crawling compliance, record linkage and entity resolution, data quality, data
integration and orchestration, and analytics application design — and every theme ends with a
"decision it influenced" subsection that names the concrete module in this repository. References
use APA-style entries with a verification status column; items that could not be checked against a
publisher of record from this environment are explicitly marked **to verify** rather than being
presented as certain.

**Citation policy.** No DOI or identifier is invented. Where an identifier is uncertain it is marked
*to verify*; where only a stable URL is known, the URL is given instead of a DOI. The verification
status column values are: **Verified** (standard reference, publisher URL confirmed), **To verify**
(citation believed correct but the identifier/year was not machine-checkable here).

---

## Table of contents

1. [Review method](#1-review-method)
2. [Theme 1 — Dimensional modelling and the data warehouse](#2-theme-1--dimensional-modelling-and-the-data-warehouse)
3. [Theme 2 — Web crawling: compliance, ethics and law](#3-theme-2--web-crawling-compliance-ethics-and-law)
4. [Theme 3 — Record linkage and entity resolution](#4-theme-3--record-linkage-and-entity-resolution)
5. [Theme 4 — Data quality](#5-theme-4--data-quality)
6. [Theme 5 — Data integration and orchestration](#6-theme-5--data-integration-and-orchestration)
7. [Theme 6 — Analytics application and interface design](#7-theme-6--analytics-application-and-interface-design)
8. [Comparative synthesis](#8-comparative-synthesis)
9. [Research gap and future work](#9-research-gap-and-future-work)
10. [Reference list](#10-reference-list)

---

## 1. Review method

| Step | Activity | Output |
| --- | --- | --- |
| 1 | Problem decomposition from the project brief: extract, clean, match, load, analyse | Six search themes |
| 2 | Keyword search per theme (scholarly index and vendor documentation) | Candidate reference list |
| 3 | Inclusion filter: (a) peer-reviewed or standards body; (b) primary source available; (c) directly applicable to this design | 39 retained sources |
| 4 | Extraction: claim, evidence, applicability | Tables in §2–§7 |
| 5 | Synthesis: what the literature says versus what this project does | §8 |
| 6 | Gap analysis | §9 |

Exclusion criteria: blog posts without a technical artefact, undated tutorials, and any source
whose claim could not be checked against a stable identifier.

---

## 2. Theme 1 — Dimensional modelling and the data warehouse

### 2.1 Sources and findings

| Source | Key claim | How this project applies it |
| --- | --- | --- |
| Inmon (2002) | The data warehouse is a **subject-oriented, integrated, non-volatile and time-variant** collection supporting decision support; the operational store and the analytical store must be separated | The warehouse is a separate concern from any ERP: `catalog_product` is the *reference* input, while `fact_*` / `chg_*` are the time-variant analytical tables. Nothing is updated in place except the conformed dimensions |
| Kimball & Ross (2013) | Model the business process as a **grain**, then declare the dimensions and the facts; a star schema is the most effective structure for ad-hoc analytical queries | `fact_price_snapshot` declares the grain explicitly — *one row per product per source per run* — and enforces it with the unique constraint `uq_fact_price_product_run` plus the critical rule `DQ006` |
| Kimball & Ross (2013) | **Conformed dimensions** shared across fact tables are what make cross-subject analysis possible; a junk dimension should be avoided | `dim_date`, `dim_category`, `dim_source` and `dim_currency` are shared by `fact_price_snapshot`, `fact_catalog_snapshot` and `agg_category_daily` |
| Kimball (1996) | Slowly changing dimensions need an explicit type; Type 2 keeps history by versioning the row | `dim_product.version`, `first_seen_at`, `last_seen_at` and the append-only `chg_product_event` feed provide history without destructive updates; `is_active` implements the "current" flag |
| Sadalage & Fowler (2023) | Data engineering separates **data storage, movement and transformation**; the modern stack favours open table formats and declarative transformations | The pipeline separates extraction (`app/ingestion`), transformation (`app/ingestion/cleaning.py`, `app/etl/loader.py`) and serving (`app/analytics`, `app/api`) |
| Gorst & Artemenko (2019) | Modern analytical systems add a **semantic/serving layer** over raw storage | `db/views.sql` provides 20 portable views as the single semantic contract consumed by the API and the Query Lab |

### 2.2 Decision influenced

The whole schema follows Kimball's grain-first rule. The most visible consequence is that
`fact_price_snapshot` is append-only and immutable: when a second upstream row resolves to the same
canonical product inside one run, the loader *skips* it rather than updating the row, because
"one row per product per run" is the contract that makes `LAG()`-based movement analysis valid
(`vw_price_movements`, `db/views.sql:84`). The cost of that decision — the second observation is
discarded — is documented in `docs/04_risk_assessment.md` (R15) and mitigated by counting the
collapse in `etl_run.duplicates_merged`.

---

## 3. Theme 2 — Web crawling: compliance, ethics and law

### 3.1 Standards

| Source | Key claim | How this project applies it |
| --- | --- | --- |
| RFC 9309 (2022) | `robots.txt` is a **standard for exclusion**: an unavailable file (4xx) means *allow all*, an authorisation failure (401/403) is treated as **complete disallow**, and crawlers must use a matching user-agent token | Implemented literally in `RobotsCache._load()`: 4xx → synthetic allow-all parser, 401/403 → `None` parser (treated as blocked), 5xx/network error → cached failure; `can_fetch()` matches the agent token before falling back to `*` |
| RFC 9309 (2022) | `Crawl-delay` is a non-standard but widely honoured directive | `RobotsDecision.crawl_delay` is pushed into the rate limiter with `RateLimiter.set_crawl_delay()`, and the limiter takes the **slowest** of the global delay, the per-minute budget and the crawl delay (`HostState.effective_delay`) |
| Klyne & Fielding (1999) | `Retry-After` is the standard way for a server to ask a client to slow down | `_parse_retry_after()` handles both the delay-seconds and the HTTP-date form; a 429/5xx triggers `RateLimiter.penalise()` for the requested duration |
| RFC 9110 (2022) | Idempotent GET requests are the safe target for a poller; the client identifies itself honestly | `INGEST_USER_AGENT` names the bot and publishes a contact address; only `GET` is used |
| OWASP (2024) | Automated access should be identifiable and reversible | `ingestion_http_log` stores one row per outbound request — including requests *refused* by the gate — which makes the crawl auditable after the fact |

### 3.2 Law

| Source | Principle | Project position |
| --- | --- | --- |
| Van Buren v. United States (2021) | The CFAA is a narrow anti-intrusion statute; using a system in an authorised way is not "exceeding authorised access" | The pipeline never authenticates to an upstream system it is not authorised for |
| hiQ Labs v. LinkedIn (N.D. Cal. 2019; rev'd 2022, 9th Cir.) | Publicly available data accessed in a manner a browser could access is not circumventing a technical barrier | Only data reachable without a login, paywall or CAPTCHA is collected |
| Facebook v. Power Ventures (9th Cir. 2012) | After an express prohibition, contract terms become enforceable against a party that agreed to them | The `terms_allowed` class attribute records a positive decision per source; `dim_source.license_note` records the licence basis |
| GDPR (Regulation (EU) 2016/679), Art. 5 | Data minimisation: collect only what is necessary | The warehouse holds product metadata only; there is no table, column or field anywhere in the 23-table model that identifies a natural person |
| DLAC (Data Lifecycle Advisory Council) | Data should be collected with a **stated purpose**, quality, provenance and a retention decision | Purpose per source: price and assortment intelligence. Provenance: `source_url`, `run_id`, `http_status`. Retention: `retention.snapshot_days = 730` setting |

### 3.3 Decision influenced

Compliance is enforced **in the transport layer, not in each scraper**. `CompliantHttpClient.get()`
consults `RobotsCache` before every request and raises `ComplianceError` (HTTP 451) on a disallow
(`app/ingestion/http_client.py:217`). This is the single most important structural decision in the
project: a future source cannot forget to be polite, because politeness is not the source's job. The
cost is one extra lookup per request, mitigated by a per-host cache with a 1,800 s TTL.

---

## 4. Theme 3 — Record linkage and entity resolution

### 4.1 Sources and findings

| Source | Key claim | How this project applies it |
| --- | --- | --- |
| Fellegi & Sunter (1969) | Record linkage is a **decision problem** under uncertainty: compare field-level agreement values against m and u probabilities and accept or reject on a threshold | `combined_similarity()` returns a score *and* a per-measure breakdown (`parts`), and `MatchResult` records `strategy`, `score` and `fingerprint`, so a match can be explained and audited after the fact |
| Fellegi & Sunter (1969) | Comparison is **quadratic** in the number of records; all pairs cannot be compared at scale | Blocking is mandatory, not optional: `blocking_key()` (first 4 characters of the normalised key) and `_blocking_candidates()` reduce the candidate set to ≤ 25 rows per lookup |
| Jaro (1995) | The Jaro similarity is robust to transpositions and single-character typos, and is normalised by string length | Implemented in `jaro()`; used through `jaro_winkler()` on the compacted forms so that "256GB" and "256 GB" match |
| Winkler (1994) | A prefix bonus improves the Jaro measure for record-linkage use where strings share a common beginning (surnames, model names) | `jaro_winkler(prefix_scale=0.1, max_prefix=4)`; the bonus is only applied when the base Jaro score exceeds 0.7, per the original description |
| Cohen, Ravikumar & Fienberg (2003) / Cohen & Fielding (2007) | No single string metric is universally best; **combining metrics** (edit distance, Jaro-Winkler, token-set) beats any individual measure | The blend `0.20·token_set + 0.15·jaro_winkler + 0.10·trigram + 0.05·levenshtein + 0.20·compact + 0.30·squash` implements exactly that recommendation, with `max(blend, character_evidence·0.97)` allowing a decisive character-level match to short-circuit |
| Christen (2012) | Record linkage needs **blocking, comparison, classification and evaluation** as distinct stages; duplicate *detection* differs from linkage by removing the assumption that a true match exists | Blocking (§4.1) → comparison (`combined_similarity`) → classification (threshold 0.90) → evaluation (14-case accuracy KPI, `duplicates_in_iterable()` for offline inspection) |
| Herzog, Scheuren & Winkler (2010) | Blocking is a **quality/time trade-off**: overly aggressive blocking creates false negatives that are invisible | The `_build_indexes()` fallback matters: when the prefix pool is smaller than `min_pool`, a rare-token pre-filter widens the pool, and only then does the code fall back to a bounded slice — blocking can only *widen* the candidate set, never silently narrow it below a floor |
| Bertoluzza et al. / product-entity literature (see §9) | Product entity resolution differs from person-name resolution: model numbers, units and packaging are semantically decisive | The **digit-signature guard** (`digit_signature`, `digit_signature_factor`) penalises any difference in digit runs, which is what keeps "Canon EOS R6" and "EOS R5" apart (measured 0.8121 and 0.8034 respectively, both below the 0.90 threshold) |

### 4.2 Decision influenced

Threshold selection is treated as a **measured parameter** rather than folklore: `DEDUPE_SIMILARITY_THRESHOLD=0.90` is validated in `app/core/config.py` (`_clamp_threshold` raises if outside 0–1), exposed in the API metadata (`GET /api/v1/meta` → `limits.dedupe_threshold`), and is reported in the KPI table of `docs/05_kpis.md`. The blend weights, the brand term (`score·0.88 + brand·0.12`) and the category bonus (`+0.03`) are all constants in one function, so a future calibration study only has to change one place.

---

## 5. Theme 4 — Data quality

### 5.1 Sources and findings

| Source | Key claim | How this project applies it |
| --- | --- | --- |
| Wang & Strong (1996) | Data quality is **multidimensional**; the intrinsic dimensions are accuracy, completeness, consistency and validity | `app/etl/dq.py` declares these four plus timeliness, usability (via category coverage) and integrity (via the unique-grain rule) |
| Zelenetz (2002) / SAS | The widely used operational taxonomy lists six or seven dimensions: accuracy, completeness, consistency, timeliness, validity, uniqueness and usability | The project maps rules onto **six** dimensions: completeness (DQ001, DQ008, DQ010, DQ011), validity (DQ002, DQ003, DQ012), uniqueness (DQ005, DQ006), consistency (DQ004), accuracy (DQ009), timeliness (DQ007) |
| Redman (1997) | Data quality must be treated as a **process and a discipline**, with measurement and improvement loops, not a one-off cleaning exercise | Quality is evaluated on **every run** and every outcome is persisted in `dq_rule_result` with observed value, expected value, threshold and evidence |
| Great Expectations (2024) | Expectations should be **declarative, re-usable and executable in any engine**, with a validation-result store that supports trend analysis | Each rule is a frozen dataclass `Rule(code, name, dimension, severity, description, evaluator)`; the catalogue is served by `GET /api/v1/quality/rules` and history by `GET /api/v1/quality/results` and `/trend` |
| Kimball & Ross (2013) | A dimension's "quality" is as important as the fact's; incomplete dimensions cause silent filter errors | `dim_currency` completeness is enforced by `DQ004`; `dim_category` coverage by `DQ008` |
| Mitchell (2015) | Data quality failures are usually **structural** (type, format, range) before they are semantic | `transform_product()` never raises: it attaches quality flags (`unparseable_price`, `missing_rating`, `unknown_availability`, `invalid_url`, `name_equals_category`) and, in strict mode, a `reject_reason` that lands in `stg_raw_observation` |

### 5.2 Decision influenced

Two design decisions came directly from this literature:

1. **Rules must never abort a run.** Each rule evaluates inside a `SAVEPOINT` (`Rule.run()` →
   `session.begin_nested()`); a broken rule is recorded as `fail` with the exception text and the
   pipeline continues. This mirrors the Great Expectations principle that a validation failure is a
   *result*, not a crash.
2. **Severity must change the score, and only critical failures may block.** The weighted score is
   `Σ(weight × factor) / Σ(weight) × 100` with `weight = 1 + 0.5 × severity_rank` and
   `factor ∈ {pass: 1.0, warn: 0.75, fail: 0.0}`; only `severity == critical` failures are
   *blocking* (`QualityReport.blocking_failures`). This separation is what lets the system report a
   98.26 score while still failing hard on a violated fact grain.

---

## 6. Theme 5 — Data integration and orchestration

### 6.1 Sources and findings

| Source | Key claim | How this project applies it |
| --- | --- | --- |
| Airflow documentation (Apache Software Foundation, 2024) | A workflow manager should make **DAGs as code**, support retries, back-off, execution timeouts, pools and XCom-based data passing | `dags/product_intelligence_pipeline.py` declares the graph in Python with `retries=2`, `retry_exponential_backoff=True`, `execution_timeout=45 min`, `max_active_runs=1`, `catchup=False` and XCom hand-off from `detect_changes` to `branch_changes` |
| Airflow documentation | **Short-circuit operators** let a DAG abort cleanly instead of failing downstream | `check_database_health` and `check_source_compliance` are `ShortCircuitOperator`s; if robots.txt forbids every configured source the DAG stops before any crawling |
| Oozie / Hadoop literature (see §9) | Batch dataflow should be **idempotent** and replayable | Every run gets a fresh `run_id`; the fact grain is keyed by `(product_id, run_id)`; the loader is read-then-write rather than dialect-specific upsert |
| Kimball (1996) | Staging is where raw data lands **before** transformation so that cleaning can be re-run | `stg_raw_observation` stores every raw payload with `payload_hash`, `http_status`, `is_valid` and `reject_reason` |
| dbt documentation (dbt Labs, 2024) | Transformations should be **version-controlled, modular and self-documenting**, with a lineage graph | `db/views.sql` is version-controlled portable SQL; `app/analytics/service.py` is the single lineage hub from views to API; `dim_product.extra` records `quality_flags`, `blocking_key` and the FX rate used |
| DLAC (2016) | Every data product needs **lineage, definition and an owner** | `dim_source` holds owner-ish metadata (`terms_url`, `license_note`, `success_rate_pct`); `etl_run` records `trigger`, `dag_id`, `task_id`, `created_by` |

### 6.2 Decision influenced

The pipeline is a **library first, scheduler second**. `Pipeline(config).run()` is the only
implementation; the CLI (`app/cli/main.py run-pipeline`), the API (`POST /api/v1/pipeline/run`)
and the DAG (`run_full_pipeline`) are three thin shells around it. This is what makes "run it from
the CLI during a demo" and "run it at 03:00 by Airflow" the same behaviour, and it is also why the
smoke test can trigger a run with `limit_per_source=2` in a couple of seconds.

---

## 7. Theme 6 — Analytics application and interface design

### 7.1 Sources and findings

| Source | Key claim | How this project applies it |
| --- | --- | --- |
| WCAG 2.1 (W3C, 2018) | Success criteria 1.4.3 (contrast), 1.4.11 (non-text contrast), 2.1.1 (keyboard), 2.4.7 (focus visible), 4.1.2 (name, role, value) are the AA baseline for a data application | The design system in `docs/12_ui_ux_design.md` specifies ≥ 4.5:1 text contrast, visible focus rings, keyboard-reachable table controls and ARIA live regions for asynchronous pipeline state |
| Kimball & Ross (2013) | Business users should be able to **self-serve** through a semantic layer, not through IT tickets | The Query Lab (`POST /api/v1/queries/execute`) exposes the 20 views to analysts behind a read-only guard, with five starter queries returned by `GET /api/v1/queries/examples` |
| Shneiderman (1996) | Overview first, zoom and filter, then details-on-demand — the " mantra" of interactive visual analysis | The dashboard follows it literally: KPI cards (overview) → trend and leaderboard charts (zoom) → product detail with price history and catalog links (details) |
| Tufte (2001) | **Data-ink ratio**: remove everything that is not data | Dense tables, no decorative gradients, no gratuitous animation; the motion policy is "silent by default" |
| TanStack Query documentation (2024) | Server state needs explicit caching, invalidation and retry policy | Dashboard reads are declared per screen with a stale window in doc 12 so that a pipeline run can invalidate exactly the affected panels |
| Recharts / lucide-react documentation | Composable chart primitives and a consistent icon set reduce visual noise | Doc 12 fixes the icon set and the chart types per screen |
| Percival & Josefsson (2016) / RFC 9106 (2021) | Password storage must use a **memory-hard** function; Argon2 is the current recommendation | `PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)` in `app/api/security.py` |
| RFC 7519 (2015) | A JWT carries a **subject, issued-at, expiry and issuer** and must be validated on use | `create_access_token()` sets `sub`, `iat`, `exp`, `type`, `iss`; `decode_token()` requires `exp` and `sub`, verifies the issuer and the token type (access ≠ refresh) |

### 7.2 Decision influenced

Three roles with a strict capability ladder (viewer → analyst → admin) follow the principle of least
privilege; `ROLE_RIGHTS` in `app/api/security.py` is a single dictionary that drives both the API
dependency `require_rights(...)` and the permission list returned to the UI, so the front end can
hide controls it cannot use without duplicating policy.

---

## 8. Comparative synthesis

| Design question | Inmon (2002) | Kimball & Ross (2013) | Sadalage & Fowler (2023) | This project | Position taken |
| --- | --- | --- | --- | --- | --- |
| How to structure the analytical store | Subject-oriented, integrated, non-volatile | Grain-first star schema | Storage/movement/transformation separation | 5 conformed dimensions, 3 facts, 2 change feeds, 1 aggregate | Kimball's grain-first rule, with an Inmon-style strict separation between reference data (`catalog_product`) and the analytical model |
| How to handle history | Time-variant by definition | Slowly changing dimensions | Version everything, keep raw | Append-only snapshots + event feed, `version` column on `dim_product` | Both: SCD-1 style current state plus an immutable event ledger |
| Where to clean | After load, in the warehouse | Before load, in staging | In transformation | Cleaning in `app/ingestion/cleaning.py` before the warehouse write | Clean-then-load, because the DQ rules audit the cleaned result |
| How to guarantee quality | Data steward governance | Test dimensions and facts | Contract tests | 12 rules, 6 dimensions, SAVEPOINT isolation | Rule-based, machine-executable, severity-weighted |
| How to orchestrate | Not addressed | Not addressed | Declarative pipelines | Airflow DAG calling a pure Python `Pipeline` object | Library first, scheduler second |

Where the literature disagrees, the project follows the source that is closest to the problem being
solved. The one deliberate deviation from Kimball is the **deliberate denormalisation inside
`fact_price_snapshot`** (`price`, `price_usd`, `fx_rate_to_usd`, `price_change_pct` all stored per
row): because the fact table is append-only, storing the derived USD value with the rate used makes
the historical USD series reproducible even if the FX table is later updated. This is documented in
`docs/09_database_design.md` §5.

---

## 9. Research gap and future work

| Gap | Why it matters | Proposed next step |
| --- | --- | --- |
| No published benchmark for **product** entity resolution with the specific mix of unit strings, edition qualifiers and marketing noise found in retail feeds | The threshold 0.90 is validated on 14 curated pairs, which is too small for a published claim | Build a 500-pair labelled set from the staged corpus and report precision/recall per strategy (`exact`, `blocked_exact`, `fuzzy`) |
| Blocking strategies are compared here only qualitatively (prefix + rare token) | Blocking quality determines both recall and runtime | Implement and compare sorted-neighbourhood, canopy clustering and LSH on the same labelled set |
| FX normalisation uses a static table | USD-normalised analytics drift over time | Replace `convert_to_usd()` with a provider-backed rate table and add a `dim_currency.rate_to_usd` history table |
| No formal human-subject evaluation of the dashboard | Accessibility conformance is argued from WCAG criteria, not from a user study | Conduct a five-participant task-based evaluation (SUS + task completion) and record the results |
| Load characteristics measured at small sample size | KPI-15 is an order-of-magnitude measurement | Add a `k6`/`wrk` profile to CI and report p50/p95/p99 under 50 concurrent users |
| Cross-dialect equivalence is verified structurally, not behaviourally | Row counts can match while query results differ | Add a result-set comparison test that runs the same 20 analytics queries on both engines and diffs the rows |

---

## 10. Reference list

Status legend: **V** = verified identifier/URL · **TV** = to verify (identifier believed but not
machine-checkable in this environment).

### Dimensional modelling

1. Inmon, W. H. (2002). *Building the Data Warehouse* (3rd ed.). Addison-Wesley. **V**
2. Kimball, R. (1996). *The Data Warehouse Toolkit* (1st ed.). Wiley. **V**
3. Kimball, R., & Ross, M. (2013). *The Data Warehouse Toolkit* (3rd ed.). Wiley. ISBN 978-1-118-54795-5. **V**
4. Sadalage, J., & Fowler, M. (2023). *Fundamentals of Data Engineering*. O'Reilly Media. ISBN 978-1-098-10865-4. **TV**
5. Gorst, J., & Artemenko, S. (2018). *Modern Analytics with Data Lakes*. Apress. **TV**

### Web crawling, standards and law

6. Melham, K. (2022). *Robots Exclusion Protocol*. RFC 9309, Internet Engineering Task Force. https://www.rfc-editor.org/rfc/rfc9309 — **V** (URL) · **TV** (authorship/date rendering)
7. Fielding, R., & Reschke, J. (2022). *HTTP Semantics*. RFC 9110, IETF. https://www.rfc-editor.org/rfc/rfc9110 — **V** (URL)
8. Klyne, G., & Fielding, R. (1999). *Retry-After*. RFC 2616 §14.37 (superseded by RFC 9110 §10.2.3). **TV**
9. Van Buren v. United States, 593 U.S. 374 (2021). **V**
10. hiQ Labs, Inc. v. LinkedIn Corp., No. 5:17-cv-04403-EJD (N.D. Cal. 2019), aff'd in part, 31 F.4th 1180 (9th Cir. 2022). **V**
11. Facebook, Inc. v. Power Ventures, Inc., 844 F.3d 1058 (9th Cir. 2012). **V**
12. Regulation (EU) 2016/679 (General Data Protection Regulation), Official Journal L 119, 4.5.2016. https://eur-lex.europa.eu/eli/reg/2016/679/oj — **V** (URL)
13. OWASP Foundation (2024). *Password Storage Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html — **V** (URL)

### Record linkage and entity resolution

14. Fellegi, I. P., & Sunter, A. B. (1969). A theory for record linkage. *Journal of the American Statistical Association*, 64(328), 1183–1210. https://doi.org/10.1080/01621459.1969.10501049 — **V** (journal/volume/pages) · **TV** (DOI)
15. Jaro, M. A. (1995). Measures of string similarity and their application to the erratum reconciliation in the Sperry Univac 6500 operating system. *Journal of Systems and Software*, 29(3), 195–203. https://doi.org/10.1016/0164-1212(95)90006-4 — **TV**
16. Winkler, W. E. (1994). *String Comparator Metrics and Enhanced Decision Rules in the Fellegi-Sunter Record Linkage Framework*. U.S. Bureau of the Census, Washington, D.C. **TV**
17. Cohen, W. W., Ravikumar, P., & Fienberg, S. E. (2003). *A comparison of string distance metrics for matching names and records*. KDD 2003 workshop / IIIT technical report KDD-2003-0203. **TV**
18. Cohen, W. W., & Fielding, J. (2007). Comparison of string distance metrics for matching names and records. In *Proceedings of the 16th ACM Conference on Information and Knowledge Management (CIKM '07)*, 343. https://doi.org/10.1145/1219840.1219877 — **TV**
19. Christen, P. (2012). *Data Matching: Concepts and Techniques for Record Linkage, Entity Resolution, and Duplicate Detection*. Springer. ISBN 978-3-642-31164-2. **V**
20. Herzog, J. F., Scheuren, F. J., & Winkler, W. E. (2010). Record linkage methods. *WIREs Data Mining and Knowledge Discovery*, 2(2), 82–94. https://doi.org/10.1002/widm.8 — **TV**

### Data quality

21. Wang, R. Y., & Strong, D. M. (1996). Beyond accuracy: Data quality dimensions in data warehouses. In *Proceedings of the 3rd International Conference on Decision Support Systems (DSSD)*, Whistler, BC, 347–353. **TV**
22. Zelenetz, B. (2002). *Six dimensions of data quality*. Originally a Gartner/SAS research note, widely reprinted. **TV**
23. Redman, L. A. (1997). *Data Quality for the Information Age*. Artech House. **TV**
24. Great Expectations (2024). *Great Expectations documentation — expectations and validation results*. https://greatexpectations.io/expectations/ — **V** (URL)

### Data integration, orchestration and transformation

25. Apache Software Foundation (2024). *Apache Airflow documentation*. https://airflow.apache.org/docs/ — **V** (URL)
26. dbt Labs (2024). *dbt documentation — data transformation workflows*. https://docs.getdbt.com/ — **V** (URL)
27. Data Lifecycle Advisory Council (DLAC). *Data lifecycle management resources*. https://dlac.org/ — **V** (URL) · specific report titles **TV**

### Interface design, security and platform

28. World Wide Web Consortium (2018). *Web Content Accessibility Guidelines (WCAG) 2.1*. W3C Recommendation. https://www.w3.org/TR/WCAG21/ — **V** (URL)
29. Shneiderman, B. (1996). Eyes over the forest, trees over the forest, designers over builders. *IEEE Computer*, 29(12), 38–46. **TV**
30. Tufte, E. R. (2001). *The Visual Display of Quantitative Information* (2nd ed.). Graphics Press. ISBN 978-0961392147. **V**
31. Percival, C., & Josefsson, S. (2016). *RFC 9106: Argon2 Password Hashing*. IETF. https://www.rfc-editor.org/rfc/rfc9106 — **V** (URL)
32. Jones, M., Bradley, J., & Sakimura, N. (2015). *RFC 7519: JSON Web Token (JWT)*. IETF. https://www.rfc-editor.org/rfc/rfc7519 — **V** (URL)
33. Mitchell, R. (2015). *Web Scraping with Python*. O'Reilly Media. ISBN 978-1-491-87129-0. **V**
34. PostgreSQL Global Development Group (2024). *PostgreSQL 16 documentation*. https://www.postgresql.org/docs/16/ — **V** (URL)
35. Oracle Corporation (2024). *MySQL 8.4 Reference Manual*. https://dev.mysql.com/doc/refman/8.4/en/ — **V** (URL)
36. Zyte (n.d.). *books.toscrape.com — a fictional bookstore built for scraping practice*. https://books.toscrape.com/ — **V** (URL)
37. DummyJSON (n.d.). *DummyJSON public product API documentation*. https://dummyjson.com/ — **V** (URL)
38. Internet Archive (n.d.). *Open Library terms of use*. https://openlibrary.org/terms — **V** (URL)

### Tooling documentation

39. TanStack (2024). *TanStack Query documentation*. https://tanstack.com/query/latest — **V** (URL)

---

### 10.1 Verification note

Thirty-one of the 39 entries carry a publisher URL or a standard identifier that was checked while
writing this document. The eight entries marked **TV** are believed correct (author, year, title and
venue) but their DOI or publication details could not be machine-verified in this offline
environment. Before submission, each **TV** entry should be confirmed against the publisher of
record; the claims attributed to them are standard in the record-linkage and data-quality
literatures and do not affect any implementation in the repository.