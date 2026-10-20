# 16 — User Manual

## Purpose

This manual is written for the people who use the Product Intelligence Pipeline every day: the
pricing analyst, the category manager, the data platform lead and the system administrator. It
explains how to sign in, what each screen shows, what you can do on it, how to filter, export, save a
view and raise an alert, how to change your own settings, what an administrator administers, and what
to do when something does not work.

No code is required to follow this manual. Every action is described with the screen it happens on
and, where it helps, the API path behind it.

---

## Table of contents

1. [Before you start](#1-before-you-start)
2. [Signing in and out](#2-signing-in-and-out)
3. [The dashboard](#3-the-dashboard)
4. [Products](#4-products)
5. [Product detail](#5-product-detail)
6. [Changes](#6-changes)
7. [Analytics](#7-analytics)
8. [Pipeline](#8-pipeline)
9. [Run detail](#9-run-detail)
10. [Quality](#10-quality)
11. [Catalog](#11-catalog)
12. [Sources](#12-sources)
13. [Query Lab](#13-query-lab)
14. [Account and preferences](#14-account-and-preferences)
15. [Saved views](#15-saved-views)
16. [Alerts and notifications](#16-alerts-and-notifications)
17. [API keys](#17-api-keys)
18. [Administration](#18-administration)
19. [Exporting data](#19-exporting-data)
20. [Troubleshooting](#20-troubleshooting)
21. [FAQ](#21-faq)
22. [Glossary](#22-glossary)

---

## 1. Before you start

| Item | Value |
| --- | --- |
| Dashboard URL | `http://localhost:5173` (development) |
| API URL | `http://localhost:8000/api/v1` |
| Interactive API docs | `http://localhost:8000/docs` |
| Demo accounts | `admin@example.com`, `analyst@example.com`, `viewer@example.com` |
| Default passwords | `Admin@12345`, `Analyst@12345`, `Viewer@12345` |
| Expected data state | 23 tables, 20 views, 60 demo products, 150 days of history, DQ score 98.26 |

If the dashboard cannot be reached, ask the operator to run:

```bash
make up-db && make db-wait      # databases
make serve                      # API on port 8000
make frontend-dev               # dashboard on port 5173
```

---

## 2. Signing in and out

### 2.1 Sign in

1. Open the dashboard URL. You land on the sign-in screen.
2. Enter your email address and password.
3. Tick **Remember me** if you work on this machine regularly; it extends the refresh token to 30 days.
4. Press **Sign in**. The shell loads with your role's navigation.

If you make five wrong attempts the account locks for 15 minutes and the message says so. Wait, then
sign in again, or ask an administrator to reset the account.

### 2.2 What your role can see

| Role | Sees | Cannot do |
| --- | --- | --- |
| **Viewer** | Dashboard, Products, Changes, Analytics, Pipeline, Quality, Catalog, Sources, Account | Run a pipeline, use the Query Lab, change settings, manage users, see the audit log |
| **Analyst** | Everything a viewer sees, plus **Query Lab**, saved views, alerts, and the **Run pipeline** button | Manage users, edit global settings, see the application audit log |
| **Admin** | Everything, plus **Admin** (users, settings, audit, compliance) and run-history maintenance | — |

Navigation items you cannot use are not rendered; API calls that bypass the UI return
`403 permission_denied`.

### 2.3 Sign out

Click the account menu (top right) → **Sign out**. The session is recorded in the audit log with your
IP address. Tokens are held in memory only, so closing the browser also ends the session.

---

## 3. The dashboard

The dashboard answers "what is the state of my data today?" in one screen.

### 3.1 The five KPI cards

| Card | Meaning | Where the number comes from |
| --- | --- | --- |
| **Products** | Products observed in the selected window | `GET /api/v1/analytics/kpi` |
| **Price changes** | Price changes in the window, with the significant count | same |
| **New / removed** | New arrivals and products that disappeared | same |
| **DQ score** | Data-quality score of the last run, plus the failure count | same |
| **Catalog** | Internal SKUs matched in the last reconciliation | same |

Use the window selector (7 / 30 / 90 days) in the card header to change every card and chart at once.

### 3.2 The charts

| Chart | What to read from it |
| --- | --- |
| Observations and average price | Whether the daily observation volume is stable and how the average USD price moves |
| Price-change timeline | Green (down) and red (up) bars; the line is the mean absolute change — spikes mean a promotion cycle |
| Category breakdown | Bars are average USD price; click a bar to filter the Products screen |
| Brand leaderboard | Ranked by product count; the in-stock percentage highlights availability risk |

### 3.3 Latest run strip

The strip at the bottom shows the most recent run: `run_id`, status, duration, records extracted and
loaded, DQ score and warnings. Click it to open the run detail.

---

## 4. Products

The Products screen is the deduplicated, canonical catalogue.

### 4.1 Filters

| Filter | How to use | Effect |
| --- | --- | --- |
| Search | Type at least two characters | Matches name, brand, category or URL |
| Category | Pick from the facet list (counts shown) | Exact category name or a path prefix |
| Brand | Pick from the facet list | Exact brand |
| Source | Pick a source code | Only products observed by that source |
| Stock | Any / in stock / out of stock / limited / preorder | Availability filter |
| Price range | Two numeric inputs | Inclusive USD range |
| Rating | Dropdown | Minimum rating |
| Movement | Numeric | Only products whose last change is at least this percentage |
| Recency | 30 / 90 / 365 days | Products first seen or last seen inside the window |
| Active | On by default | Untick to include removed products |

Active filters appear as chips above the table. Click a chip to remove it, or **Clear all** to reset.
The URL always reflects the current filters, so you can bookmark or share an exact view.

### 4.2 Sorting and paging

Click a column header to sort; click again to reverse. Use the pager at the bottom to move between
pages; the page size follows your account preference (default 25).

### 4.3 Actions

| Action | Result |
| --- | --- |
| Click a row | Opens the product detail |
| Tick rows (up to 6) → **Compare** | Side-by-side comparison drawer |
| **Save view** | Stores the current filters, sort and visible columns |
| **Export CSV** | Downloads the current product list |
| Search box type-ahead | Suggestions appear after two characters |

---

## 5. Product detail

Everything known about one canonical product.

| Section | What it shows |
| --- | --- |
| Header | Name, current price (USD), rating with count, availability, last change, match strategy and score, links to the source page and to the catalog SKU |
| Price history | Line chart of every observation, with the minimum, average and maximum and the observation count |
| Recent changes | The last 25 price changes with date, previous, new, percentage, direction and magnitude band |
| Lifecycle events | New, recurring, removed and category-changed events |
| Duplicate candidates | Similar products with a similarity score and a breakdown; use this to judge whether a merge is correct |
| Catalog position | Internal SKU, our price, market price, price gap and match status |
| Raw payload tab | The original name, quality flags, blocking key and the FX rate that was applied |

**Tip.** If two products look merged that should not be, record the product id and the score and
raise it — the threshold is configurable and can be tightened globally.

---

## 6. Changes

The Changes screen has six tabs.

| Tab | Contents | Useful filter |
| --- | --- | --- |
| **Price** | Every detected price change, largest first | Window, direction, category, brand, source, significant only, minimum absolute change |
| **Top movers** | The biggest absolute movements in the window | Direction |
| **Events** | The full lifecycle feed | Event type, category |
| **New** | Products first seen in the window | Window |
| **Removed** | Products that disappeared, with days missing and the last known price | Window |
| **Category** | Products whose category changed | Window |
| **Drift** | Per-category added / removed / recategorised / net change | Window |

**Reading a change row.** `Δ%` is the percentage move against the previous observation of the same
product **from the same source**. `Band` summarises the size: `minor` (< 1 %), `small` (< 5 %),
`moderate` (< 15 %), `large` (< 30 %), `major` (≥ 30 %). `Sig` means the move is at least 1 %.

---

## 7. Analytics

Six panels, each one report:

| Panel | Question it answers |
| --- | --- |
| Category price index | How did the average price of each category move, and how volatile was it? |
| Availability by category | Which categories are running out of stock? |
| Brand leaderboard | Which brands are cheapest, best rated, most available? |
| Source coverage matrix | Which sources contribute which categories? |
| Top movers | Which products moved most in the window? |
| Category drift | Which categories are gaining or losing assortment? |

Use the window selector at the top of the screen. The **Explain** action on the Query Lab and the
`/analytics/report/*` endpoints provide the same data in tabular form for copying into a document.

---

## 8. Pipeline

### 8.1 Reading the header

| Item | Meaning |
| --- | --- |
| Schedule | The cron expression from the settings (`0 3 * * *` = daily at 03:00) |
| Orchestrator | Which engine is responsible (Airflow 2.10.5, LocalExecutor) |
| Last run / next expected | Last start time and the next scheduled time |
| Status badges | Counts of `success`, `partial` and `failed` runs |

### 8.2 The run table

Columns: run id, status, trigger (`manual`, `cli`, `api`, `airflow`, `schedule`, `smoke_test`), target
database, start time, duration, extracted, valid, price changes, DQ score and warnings. Click a row for
the run detail.

### 8.3 Running the pipeline

If the **Run pipeline** button is visible (analyst or admin):

1. Click **Run pipeline**.
2. Choose the sources (all enabled sources by default).
3. Set **Records per source** (default 25; use a small number for a quick check).
4. Optionally tick **Strict** (reject records without a price), **Skip quality checks** or
   **Skip catalog reconciliation**.
5. Press **Run**. The run is queued and a notification confirms it. Refresh the run table to watch it.

> The administrator can also clear the run history. This deletes run, quality, reconciliation and
> request-audit history — it cannot be undone, and it asks for confirmation twice.

### 8.4 Stage timings

The stage list shows the nine stages — extract, stage, transform, resolve, load, detect, reconcile,
quality, aggregate — with the average duration per status. Use it to answer "where does the time go?".

### 8.5 Source health

For each source: kind, rate limit, terms permission, robots status, last run, success rate, average
duration, consecutive failures and sync status. Three consecutive failures mean the source should be
reviewed or disabled.

---

## 9. Run detail

| Section | Contents |
| --- | --- |
| Header | Status, trigger, target, start, finish, duration, DQ score |
| Counters | Extracted, valid, rejected, inserted, updated, duplicates merged, new, changes, removed, catalog matched |
| DQ outcomes | All 12 rules with status, severity, observed and expected values and the message |
| HTTP compliance | Requests grouped by source and host with status codes, latency, cache hits and robots refusals |
| Reconciliation | Matched / unmatched / price mismatches and the average similarity for this run |
| Params | The exact configuration the run used (expand) |
| Warnings | Any source error or DQ problem, verbatim |

---

## 10. Quality

| Element | Meaning |
| --- | --- |
| Score | 0–100, weighted by rule severity. The demo dataset scores **98.26** |
| pass / warn / fail | Rule counts. `warn` means the value is within 5 % of the threshold |
| Blocking | Rules that failed at `critical` severity — any entry here means the run was marked `failed` |
| Dimension matrix | Rules grouped by completeness, validity, uniqueness, consistency, accuracy and timeliness |
| Score trend | One point per run, with the 80-point threshold line |
| Rule results | Every historical outcome, filterable by status and dimension |
| Rule catalogue | The 12 rules with their descriptions and thresholds |

**What to do when a rule fails.** Open the rule's message: it states how many records were checked and
how many failed. `DQ001` (required fields) usually means a source is publishing incomplete records;
`DQ002`/`DQ003` mean the cleaning rules need a new pattern; `DQ004` means a new currency appeared —
add it to the reference table; `DQ009` means a source published an implausible price jump.

---

## 11. Catalog

### 11.1 Reconciliation tab

| Column | Meaning |
| --- | --- |
| SKU | The internal catalog identifier |
| Catalog name / brand / category / supplier | What our ERP thinks |
| Our price / market price | The two prices compared |
| Gap % | `(market − ours) / ours × 100` |
| Status | `matched` or `unmatched` |
| Strategy | How the match was made: `sku`, `normalized_name` or `fuzzy` |
| Similarity | Score of the chosen match (1.0 for identifier matches) |

Filter with **only mismatches** to see just the rows where the gap is at least 1 %.

### 11.2 Opportunities tab

The same rows sorted by the size of the gap, with a **Position** column:

| Position | Meaning | Action |
| --- | --- | --- |
| `we_are_dearer` | The market is cheaper than us | Review sourcing or price |
| `we_are_cheaper` | We are cheaper than the market | Check that we are not leaving margin on the table |

### 11.3 Internal catalog tab

Every SKU with cost price, list price, stock on hand, status (`active` / `discontinued`) and supplier.
Use it to confirm that the delisted SKUs in the reconciliation output are genuinely internal-only.

---

## 12. Sources

| Column | Meaning |
| --- | --- |
| code / name / kind | `api`, `scrape` or `synthetic` |
| base URL | Where the data comes from |
| rate / delay | Requests per minute and the minimum delay enforced by the rate limiter |
| paging | Whether the source supports paging |
| terms | Whether the terms of service permit automated access |
| robots | Whether `robots.txt` is respected (it always is) |

Below the table, the **robots.txt cache** shows `fetched`, `cached`, `blocked`, `allowed` and `errors`,
plus the exact user-agent string used.

### 12.1 Source preview

Select a source and press **Preview**. The drawer shows, for the first few records, the raw name next
to the cleaned name, the normalised category, the parsed price, the USD price, the rating, the
availability and any quality flags — plus how many HTTP calls were made. A synthetic source reports
`http_calls 0`, which proves it never touches the network.

---

## 13. Query Lab

Available to analysts and administrators.

1. Pick a table, a view or one of the five example queries.
2. Edit the statement.
3. Press **Run**. The grid appears with the column names, the row count and the duration.

Rules you must respect:

| Rule | Consequence if broken |
| --- | --- |
| Only `SELECT`, `WITH` and `EXPLAIN` | The request is rejected with a message before anything runs |
| No second statement, no comments | Rejected |
| At most 5,000 rows (200 by default) | The result is truncated and flagged |

Useful starting points:

```sql
-- Biggest price drops in the last 30 days
SELECT canonical_name, category_name, previous_price, new_price, change_pct
FROM vw_price_changes
WHERE change_pct < -5 ORDER BY change_pct LIMIT 25;

-- Category price index with volatility
SELECT category_name, full_date, avg_price_usd, price_stddev, distinct_products
FROM vw_category_price_index ORDER BY full_date DESC LIMIT 50;

-- Failing quality rules of the latest run
SELECT rule_code, rule_name, dimension, severity, message
FROM dq_rule_result WHERE status <> 'pass' ORDER BY evaluated_at DESC;
```

Never write to the database from the Query Lab; the warehouse is maintained only by the pipeline.

---

## 13.1 View builder

The Builder composes custom views instead of raw SQL. It has two modes, switched at the top of the
screen.

### Filter & customise

Pick an entity, then narrow it with the search box, facets (category, brand, source, availability),
numeric windows (price, rating, price change) and toggles. Choose which columns appear and in which
order, then **Save view** to store the preset for one-click reuse, optionally shared with the team.

### Group & aggregate

Ask a question of the whole dataset instead of listing rows.

1. **Dataset** — one of eleven entities: current products, price changes, new products, removed
   products, category index, brand summary, source coverage, top movers, availability, latest quality
   report, catalog reconciliation.
2. **Group by** — the dimension to group on (for example category, brand or source).
3. **Measures** — one or more of `Count`, `Count distinct`, `Sum`, `Average`, `Minimum`, `Maximum`,
   each with a column and an optional label. Add or remove rows freely.
4. **Advanced filters** — add as many as you need; each row chooses a column, one of fifteen
   operators (`equals`, `not equal`, `greater than`, `at least`, `less than`, `at most`, `contains`,
   `excludes`, `starts with`, `ends with`, `in list`, `not in list`, `between`, `is empty`,
   `is not empty`) and one or two values. Use a comma-separated list for the `in` operators.
5. **Sort measure** — order by any returned column, including your aggregates.
6. **Run** — results stream in automatically. Use the right-hand card for the group count, the query
   duration and export buttons; toggle **Show chart** for a bar preview.

The **Generated SQL** card shows exactly what the server executed, and **Copy cURL** gives you a
ready-to-run command with the bearer header. Export to CSV or JSON at any time.

Everything is rebuilt from scratch on each keystroke, so a reload never loses your composition.

---

## 13.2 Feature catalogue

The **Features** screen (Explore → Features) lists everything the platform ships, grouped into
thirteen areas. Use the search box to filter across feature names and details, or the chips to jump to
one area. Click the copy icon on any feature to put its name on the clipboard. The catalogue is served
by `GET /api/v1/meta/features`, so it always reflects the deployed code.

---

## 14. Account and preferences

### 14.1 Profile

Name, job title, department, avatar colour and timezone. Press **Save** to persist.

### 14.2 Appearance

| Control | Options | Effect |
| --- | --- | --- |
| Theme | System / Light / Dark | `system` follows your operating system |
| Accent | Indigo / Sky / Emerald / Amber / Rose | Recolours the primary control only |
| Density | Compact / Comfortable / Spacious | Row height: 32 / 40 / 48 px |
| Rows per page | 5 – 500 | Default page size for every list |

### 14.3 Data and notifications

Default currency for display, the price-change alert threshold (default 5 %), e-mail alerts and the
weekly digest flags.

### 14.4 Security

Change your password: enter the current password, then a new one of at least 10 characters containing
upper-case, lower-case, a digit and a symbol. The strength checklist shows exactly what is missing.
Changing the password is written to the audit log.

### 14.5 API keys

Create, copy and revoke machine credentials from the **API keys** tab. A key is shown exactly once,
prefix-indexed, stored as a SHA-256 hash with a server pepper, and carries its own usage counter,
expiry and rate limit. Use it as `Authorization: Bearer pip_…`.

### 14.6 Activity

The **Activity** tab lists everything you did in the last 90 days — sign-ins, password changes, API-key
operations and settings updates — with the target, outcome, IP address and relative time. It reads your
own audit entries only, so no administrator permission is required. Use **Refresh** after performing an
action elsewhere.

### 14.7 Data & privacy

| Action | What it does |
| --- | --- |
| **Download my data** | Saves a JSON snapshot: profile, preferences, API-key metadata (never secrets), saved views, alert rules, notifications and 90 days of activity |
| **Delete my account** | Irreversible. Requires your password and typing `DELETE` |

Deleting your account removes your personal rows (keys, views, alert rules, notifications) and signs
you out. The audit trail keeps a `user.self_delete` entry with your email recorded. Warehouse data is
not affected — it belongs to the pipeline, not to your account.

---

## 15. Saved views

A saved view stores the filters, the sort column and direction, and the visible columns of a list
screen.

| Action | Effect |
| --- | --- |
| **Save view** | Name it and choose whether to share it with the team |
| Apply | The filters are replayed; the usage counter is incremented |
| Favourite (★) | Pins the view to the top of the list |
| Delete | Removes the view (only your own views) |

Four views ship with the demo data: *Big price drops*, *Out of stock*, *Electronics movers* and
*New arrivals*.

---

## 16. Alerts and notifications

### 16.1 Alert rules

An alert rule is `metric`, `operator`, `threshold`, plus an optional category or source scope.

| Metric | Fires when | Example |
| --- | --- | --- |
| `price_change_pct` | A price change beyond the threshold | "Price drop > 10 %" |
| `rating` | A product rating below the threshold | "Rating below 2.5" |
| `new_product` | New products in the scope | "New product in Electronics" |
| `dq_failure` | The latest run has failing quality rules | "DQ failure" |
| `stock_out` | Out-of-stock products exist | "Stock out" |

Operators: `lt`, `gt`, `lte`, `gte`, `eq`. Channels: `in_app` (always available), `email`, `webhook`.

Use **Evaluate now** to see how many rows would fire each rule right now, without waiting for the next
run.

### 16.2 Notifications

The bell shows unread notifications. A notification carries a level (`info`, `success`, `warning`,
`critical`), a title, a body and a deep link to the affected screen. Mark one as read, or mark all as
read. The scheduled DAG publishes price-movement notifications after a run that produced changes.

---

## 17. API keys

For scheduled jobs and integrations.

1. Open **Account → API keys**.
2. Name the key (for example `nightly-export`) and press **Create**.
3. **Copy the key immediately** — the full value is shown once and never again. Only the 12-character
   prefix is stored.
4. Use it exactly like a token:

```bash
curl -s "localhost:8000/api/v1/products?page_size=5" -H "Authorization: Bearer pip_xxxxxxxxxxxx"
```

Keys expire after 90 days, are shown with their last use and usage count, and can be revoked at any
time. Revocation is immediate.

---

## 18. Administration

### 18.1 Users

Create an account (email, name, role, job title, department). The password must satisfy the strength
rules. You can change a user's fields and deactivate an account; **you cannot deactivate your own
account**. Statistics show total and active users, logins in the last 24 hours and 7 days, locked
accounts, active keys and the distribution by role.

### 18.2 Settings

Settings are grouped by category. The seeded keys are:

| Key | Default | Meaning |
| --- | --- | --- |
| `pipeline.schedule_cron` | `0 3 * * *` | When the scheduled DAG should run |
| `pipeline.default_sources` | four sources | Sources used by a scheduled run |
| `dq.min_quality_score` | `80` | Score below which a run is treated as a failure |
| `ingest.rate_limit_per_minute` | `30` | Global ceiling per host |
| `ui.default_theme` | `system` | Theme for new accounts |
| `retention.snapshot_days` | `730` | Days of price history to keep |

Only administrators can change settings. Keys prefixed `ui.` are public and are readable by all
signed-in users.

### 18.3 Audit log

Every mutating action is recorded with the action name, the user, the status, the IP address and the
duration. Filter by action, user or time window. The **Actions** tab lists which action types exist and
how often they occurred.

### 18.4 Compliance

Requests in the window, requests blocked by `robots.txt`, cache hits, retried requests, total bytes,
average and maximum latency and the number of distinct hosts. Use this screen to answer "how did we
behave?" — a non-zero *blocked* count is a signal to review the source's terms immediately.

### 18.5 Maintenance

**Clear run history** deletes `etl_run`, `dq_rule_result`, `fact_catalog_snapshot` and
`ingestion_http_log`. It requires an administrator and an explicit confirmation. Price history and
catalogue data are not affected.

---

## 19. Exporting data

| What | How | Format | Limit |
| --- | --- | --- | --- |
| Current product list | Products screen → **Export CSV** | CSV | 50,000 rows |
| Price changes | Changes → Price → **Export** | CSV | Uses the active filters |
| Any table you can query | Query Lab → run → copy, or use `analytics/report/*` | JSON | 5,000 rows per query |
| A run's compliance evidence | Compliance screen → **Export** | CSV / JSON | 1,000 log rows |

The CSV export includes the run context so a file can be interpreted later: `product_id`,
`canonical_name`, `brand`, `category_name`, `availability`, `price`, `price_usd`, `currency`,
`rating`, `price_change_pct`, `last_seen_at`, `source_code`, `product_url`.

---

## 20. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| "connection refused" on the dashboard | Frontend not running | `make frontend-dev`, then open `http://localhost:5173` |
| Sign-in fails with a valid password | Database unreachable | `make db-wait`; check `docker compose ps`; `pip-cli status` |
| "token expired" banner | Access token older than 12 hours | Sign in again; the client refreshes automatically once |
| 403 on the Run pipeline button | Role is `viewer` | Ask for an analyst or admin account |
| 403 on the Query Lab tab | Role is `viewer` | As above |
| Dashboard shows 0 products | Pipeline has not run, or the window is too short | `make run-pipeline`; widen the window to 90 days |
| DQ score dropped below 90 | A source published bad data | Open **Quality → Rule results**, read the message, then re-run with **Strict** |
| A run shows status `partial` | One source failed; the others completed | Open the run detail → Warnings; fix the source or disable it |
| A run shows status `failed` | A critical rule failed (grain or no observations) | Check `DQ006`/`DQ011` in the run detail |
| Compliance panel shows 0 requests | Only the offline source has run | `make run-all-sources` |
| Compliance panel shows blocked requests | A source's `robots.txt` disallows the path | The source is skipped by design; review its terms before re-enabling |
| Source card shows "Disabled" | `terms_allowed` is false for that source | Obtain permission, then set `enabled = true` in `dim_source` |
| Query Lab returns 422 | Statement is not `SELECT`/`WITH`/`EXPLAIN`, or contains a write keyword or two statements | Rewrite as a single read-only statement |
| Query Lab returns no rows | Filters too narrow, or the table is empty | Remove filters; check the row count with `/analytics/stats/tables` |
| Export downloads an empty file | No rows match the filters | Clear a filter and retry |
| A product looks merged with another | Fuzzy match at threshold 0.90 | Raise `DEDUPE_SIMILARITY_THRESHOLD` to 0.94 and re-run; report the pair |
| Product prices look wrong | Currency mis-detected (for example `$` assumed USD) | Check the product's `currency` in the detail header; add a source-specific hint |
| Charts show a single point | Only one day of data | Seed more history: `pip-cli seed-demo --days 150` |
| Port 8000 already in use | Another process is bound | `make serve-prod` or `pip-cli serve --port 8001` |
| Airflow UI unreachable | Container not started or port busy | `docker compose ps`; open `http://localhost:8080` |
| `vw_pipeline_health` query fails on MySQL | `TRIGGER` is a reserved word in MySQL 8.4 | Switch to the PostgreSQL target, or quote the column (see `docs/20`) |
| Everything is slow | Cache disabled or upstream slow | Check `CACHE_ENABLED`; read `ingestion_http_log.elapsed_ms` |

---

## 21. FAQ

**Q. Where does the price in USD come from?**
Each observation stores its original currency, the FX rate that was applied and the resulting USD
value. The rate table is a documented static reference table; re-runs do not restate history.

**Q. Why do two products from different sources appear once?**
That is duplicate detection working. The product detail shows the match strategy and score, and the
Duplicate candidates panel shows every near match with its score.

**Q. Why is a change shown as "recurring" rather than "new"?**
The product had already been observed in an earlier run, so this is another sighting, not an arrival.

**Q. What is the difference between `partial` and `failed`?**
`partial` means at least one source failed but the run completed and the data is usable. `failed`
means a critical rule failed — for example the fact grain was violated or no observation was produced.

**Q. Can I delete a fact row?**
Not from the UI or the API. Facts are append-only; corrections arrive as new observations. Historical
rows are managed only by the documented retention procedure.

**Q. Does the dashboard work offline?**
Yes for everything derived from the warehouse. The Sources preview and any run that needs a network
source require internet access; the synthetic source does not.

**Q. Which currency is used in reports?**
The USD-normalised column, `price_usd`. Set your preferred display currency under Account → Data.

**Q. Who can see the audit log?**
Administrators. Compliance data such as the HTTP request log is visible to any signed-in user with the
`read` right.

**Q. How do I reproduce the numbers in the documentation?**
Every figure in `docs/05_kpis.md` has a command next to it. In short:
`make bootstrap && make demo-postgres --days 150 && make run-pipeline && make verify-dialects`,
then `.venv/bin/python scripts/api_smoke.py`.

**Q. The demo password is public — is that a problem?**
Not in a development or demonstration environment. Change `SEED_*_PASSWORD` (or delete the seeded
accounts) and set `SEED_DEMO_DATA=false` before any deployment that matters. See `docs/13` §8.

**Q. How is "price changed" defined?**
A change is recorded when a product is observed again from the same source and the price differs from
the previous observation. The percentage is `(new − previous) / |previous| × 100`; a change is
*significant* at 1 % or more.

**Q. Can I add a new source myself?**
Yes, in six steps, documented in `docs/17` §7. The terms justification is the only approval step
required.

---

## 22. Glossary

| Term | Meaning |
| --- | --- |
| Blocking key | The first four characters of the normalised name, used to limit which products are compared |
| Canonical product | The single `dim_product` row that represents a real-world product after deduplication |
| Crawl delay | The `Crawl-delay` advertised in `robots.txt`, honoured by the rate limiter |
| DQ score | The severity-weighted 0–100 data-quality score of a run |
| Grain | The definition of what one row means, e.g. one snapshot per product per run |
| Magnitude band | The size bucket of a price change: minor, small, moderate, large, major |
| Match strategy | How a record was matched: `sku`, `normalized_name`, `fuzzy`, `exact`, `blocked_exact`, `new`, `merged`, `seed` |
| Price gap | The difference between the market price and our catalog price, in absolute and percentage terms |
| Run | One execution of the pipeline, identified by `run_id` |
| Snapshot | One observed price for one product from one source in one run |
| Staging zone | The landing table that keeps every raw payload before cleaning |
| Staleness window | The number of days (default 7) after which an unseen product is marked removed |
| View | A stored SQL query (`vw_*`) that defines an analytical concept used by the API and the Query Lab |