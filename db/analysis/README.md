# SQL analysis scripts

Standalone, parameterised SQL that answers the four questions in the project brief —
*price changes, new products, removed products, category changes* — plus volatility,
catalog price-gap, data-quality and compliance analysis.

| File | Question it answers |
| ---- | ------------------- |
| `01_price_changes.sql` | Which products moved, which way, by how much, and how big is the movement in aggregate? |
| `02_new_products.sql` | What entered the market, at what price, and is it already in our catalog? |
| `03_removed_products.sql` | What disappeared, and what was the assortment value we lost? |
| `04_category_changes.sql` | Which products were re-categorised, and how did the taxonomy move? |
| `05_price_volatility_by_category.sql` | How stable are prices per category (daily stddev, range, widest assortment)? |
| `06_catalog_price_gaps.sql` | Are our list prices competitive? Which SKUs are missing from the market? |
| `07_data_quality_posture.sql` | How trustworthy is the warehouse, and which rules keep failing? |
| `08_market_and_compliance.sql` | Market overview per source, daily pulse, and robots.txt compliance evidence. |

## Running them

Every file is written against the analytical views in [`../views.sql`](../views.sql), so the
same SQL runs unchanged on **PostgreSQL**, **MySQL 8.4** and **SQLite**.

```bash
# through the API (read-only SQL console, logged in as an analyst/admin)
make serve                       # terminal 1
curl -s -X POST localhost:8000/api/v1/queries/execute \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM vw_price_changes ORDER BY ABS(change_pct) DESC LIMIT 10"}'

# directly against a database
psql "postgresql://pip:pip@localhost:5432/pipeline" -f db/analysis/01_price_changes.sql
mysql -h 127.0.0.1 -u pip -ppip pipeline < db/analysis/01_price_changes.sql

# or through the CLI, which substitutes the bind parameters for you
make analysis                    # all scripts, human readable tables
make analysis ANALYSIS=01_price_changes.sql
```

## Bind parameters

| Name | Meaning | Default | Set by |
| ---- | ------- | ------- | ------ |
| `:since` | Inclusive lower bound (date or timestamp) | today − 30 days | `--days/-w` |
| `:days` | Window length in days, accepted as an alias for `:since` | 30 | `--days/-w` |
| `:row_limit` | Maximum rows returned | 25 | `--limit/-l` |
| `:gap_pct` | Minimum absolute price gap (%) for catalog analysis | 1.0 | — |

```bash
make analysis ANALYSIS=01_price_changes.sql        # default 30-day window, 25 rows
python scripts/run_analysis.py 01_price --days 7   # last 7 days only
python scripts/run_analysis.py 06_catalog -l 100   # 100 rows per statement
```

> Each script's header comment names the window it was written for (`:days 30` or
> `:days 60`); the runner binds both `:since` and `:days` so a script runs unchanged
> whichever name it uses.

## Conventions

* `ROUND(CAST(x AS DECIMAL(24,6)), n)` — PostgreSQL rejects `round(double precision, int)`,
  so every rounding casts to `DECIMAL` first; this keeps the SQL portable.
* `CASE WHEN <boolean column> THEN …` instead of `<boolean column> = 1`, because MySQL and
  SQLite store booleans as integers while PostgreSQL refuses the comparison.
* No `NULLS LAST` — MySQL does not support that modifier.
* Views only: the analysis never joins the raw landing tables, so results are reproducible
  regardless of how the pipeline batched its inserts.
