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

No captures are committed yet — the folder is wired and waiting. Until then,
the interactive equivalents are one command away:

```bash
./run.sh --open   # dashboard at http://localhost:5173
```
