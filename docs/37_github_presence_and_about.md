# GitHub Presence & About Kit

Everything needed to make the repository look complete on GitHub: the About
description, topics, website, release notes, badges, and the exact commands.
Nothing here deletes or overwrites content — every operation is additive. The
only consequential change is the explicitly requested **private** visibility.

Repository: <https://github.com/Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline>

---

## 1. About — short description (GitHub About field)

> Compliance-first product intelligence pipeline: permitted web/API ingestion → cleaning → deduplication → PostgreSQL warehouse with price history → SQL analytics → Airflow → FastAPI + React dashboard.

## 2. About — full description (recommended, paste verbatim)

> **Web-to-Warehouse Product Intelligence Pipeline** — a production-style DEPI Data Engineering capstone that continuously collects product information from *permitted* public web sources and merges it with an internal catalogue. It respects `robots.txt`, rate limits and website terms before it fetches a single record; cleans and normalises names, categories, prices, ratings and availability; detects exact and fuzzy duplicates; then loads a Kimball-style warehouse on **PostgreSQL and MySQL** with full price-history snapshots. SQL analytics answer price changes, new products, removed products and category drift, while **Apache Airflow** orchestrates the nine-stage run. A **FastAPI** service exposes 222 REST operations (OpenAPI/Swagger included) and a **React 19** dashboard renders 23 screens with light/dark/system themes, a mobile off-canvas sidebar and silent in-place reloads. 767 catalogued features · 34 registered sources · 12 enforced data-quality rules · 29 tables · 23 analytical views · 39 documents · 128 Mermaid diagrams · 636 passing tests · 104/104 API smoke checks. Zero fake data: a dedicated audit proves every row traces back to a real, permitted source.

## 3. Website (paste into About → Website)

```
https://ahmedbakr78.github.io/Web-to-Warehouse-Product-Intelligence-Pipeline/
```

The live website showcases the `website/index.html` landing page alongside the 42-page searchable documentation portal (`site/`) deployed by `.github/workflows/pages.yml`.

## 4. Topics (paste into About → Topics, in this order)

```
web-scraping  beautifulsoup  scrapy  etl  data-engineering  airflow  postgresql
fastapi  python  data-quality  deduplication  price-tracking  data-warehouse
docker  plotly  streamlit  rest-api  depi  data-pipeline  sql-analytics
react  reactjs  typescript  vite  analytics  dashboard  data-visualization
kimball  data-modeling  robots-txt  data-governance  unit-testing
```

## 5. Badges (already in README; keep them visible)

| Badge | Meaning |
| --- | --- |
| build status | GitHub Actions CI (ruff, mypy, pytest, frontend) |
| coverage | pytest-cov |
| Python 3.12 / 3.14 | supported interpreters |
| Docker Compose | six-service stack |
| AGPL-3.0 | license |
| 636 passing | backend test suite |
| 104/104 | API smoke checks |

## 6. Release notes — v1.14.0

```markdown
# v1.14.0 — "Full GitHub Presence, Live Pages & 128-Diagram Suite"

Comprehensive DEPI Data Engineering capstone release featuring automated GitHub Pages hosting, 128 Mermaid diagrams, high-DPI readable PDF architecture blueprints, and 100% real-data verified dual-warehouse parity.

## Highlights
- 767 catalogued features across 46 areas (612 documented engineering capabilities).
- 222 REST operations across 24 FastAPI routers (OpenAPI/Swagger, JWT, RBAC, 2FA, webhooks).
- 29 warehouse tables + 23 analytical views identical on PostgreSQL 16 & MySQL 8.4.
- 12 enforced data-quality rules, 34 registered sources, 14-task Airflow 2.10 DAG (33 task callables).
- 39 documentation documents, 128 Mermaid diagrams (SVG + high-DPI PNG), 283+ page consolidated PDF, 12-slide deck, infographic & demo video.
- Verified: 636 backend tests, 67 frontend tests, 104/104 API smoke checks, 6/6 CI jobs green, no-fake audit CLEAN.
```

## 7. Commands — run from the project directory

```bash
cd ~/Downloads/Depi_Ahmed_Abobakr_Project
gh auth status                 # must show "Logged in as Ahmedbakr78"
./scripts/github_polish.sh     # privacy + About + topics + website + release
```

If `gh auth status` shows an invalid token, re-authenticate first:

```bash
gh auth login --web -h github.com
```

Then verify:

```bash
gh repo view Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline \
  --json visibility,description,homepageUrl,repositoryTopics
```

## 8. Manual touches (GitHub UI only)

1. **Settings → General → Social preview** → upload a 1280×640 image.
2. **Pin** the repository on your profile.
3. **Settings → Pages → Source: main / docs** if you want the HTML site hosted.
4. **Settings → General → Features** → enable Issues, Projects and Wiki as desired.
5. Add the team as collaborators with the roles in `docs/00_team.md`.

## 9. Safety — what is never touched

No files, branches, tags, issues, releases or repository content are deleted.
`--add-topic` only appends topics; `gh release create` is skipped when a tag
already exists; visibility change is limited to the requested private setting.
