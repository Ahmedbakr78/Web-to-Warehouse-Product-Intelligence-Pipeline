# Screenshots — light + dark captures of every screen

This folder holds the dashboard captures referenced by the README Screens
section, the website and the defence deck. Captures are taken manually (they
depend on live data) with this exact procedure so every shot matches:

1. `./run.sh` — full stack with live data (or `make demo-postgres` for the
   deterministic 120-day dataset).
2. Sign in as `admin@example.com`, set the theme:
   - **Light:** Account, then Appearance, then Light.
   - **Dark:** Account, then Appearance, then Dark.
3. Viewport **1440×900**, sidebar expanded, `100%` zoom.
4. Capture: Dashboard, Analytics, Changes, Products (+ one detail page),
   Categories, Catalog, Pipeline, Quality, Sources, Forecast, Reports,
   Query Lab, Builder, Features, Webhooks, Alerts, Account, Settings,
   Users, Audit — one PNG per screen per theme.
5. Name files `<screen>-light.png` / `<screen>-dark.png` (e.g.
   `dashboard-light.png`), keep them under 500 KB each.

The following captures are committed at 1440×900:
- `dashboard-dark.png` — Live overview, KPI cards, price change activity, quality health
- `analytics-dark.png` — Multi-dimensional analytics, category trends, market volatility
- `changes-dark.png` — SCD Type 2 price changes, new & removed products, category drift
- `products-dark.png` — Star-schema canonical product catalogue, filters, facets
- `pipeline-dark.png` — 9-stage ETL pipeline execution monitor & run history
- `quality-dark.png` — 12-rule data quality gatekeeper scorecards & trend
- `sources-dark.png` — 34 registered public web sources, rate limits & robots.txt compliance
- `airflow-graph.png` — Apache Airflow DAG graph execution view (33 tasks)
- `airflow-grid.png` — Apache Airflow DAG grid run status view

```bash
./run.sh --open   # dashboard at http://localhost:5173
```
