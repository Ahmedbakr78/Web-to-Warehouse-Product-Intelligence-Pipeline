# Contributors — Web-to-Warehouse Product Intelligence Pipeline

DEPI Data Engineering capstone. Total effort split: **100%**.

| # | Member | GitHub | Role | Weight | Main component |
|---|--------|--------|------|-------|----------------|
| 1 | Ahmed (78102) | [@Ahmedbakr78](https://github.com/Ahmedbakr78) | 👑 Team Lead + Backend/API + Documentation + 9 ETL Stages Owner | 28% | FastAPI (23 routers / 216 ops) + 31 docs + 9 ETL stages + integration |
| 2 | Ahmed Abd alla | [@01124758140](https://github.com/01124758140) | Ingestion & Compliance Lead | 15% | robots.txt gate + 34 adapters + rate limiter + conditional GET |
| 3 | Ahmed Medhat | [@AhmedMedhatFarouk](https://github.com/AhmedMedhatFarouk) | ETL & Cleaning Lead | 14% | 29-step cleaner + dedupe engine + ETL support |
| 4 | Eng. Alaa Nasser | [@AlaaNasser-tech](https://github.com/AlaaNasser-tech) | Database & Data Quality Lead | 14% | 29 tables + 23 views + 12 DQ rules |
| 5 | legecy007 | [@legecy007](https://github.com/legecy007) | Frontend / Dashboard Lead | 15% | React 19 + 21 screens + PWA + light/dark/midnight/HC themes |
| 6 | Mennatullah Ahmed | [@mennatullahahmed01-debug](https://github.com/mennatullahahmed01-debug) | DevOps & Orchestration Lead | 14% | Airflow DAG + Docker (6 services) + CI/CD + scripts |

## Responsibility map

- **Ahmed (lead):** `app/api/`, `app/etl/pipeline.py`, `app/core/features.py`,
  `app/core/team.py` (+ `GET /meta/features`, `GET /meta/team`), `docs/`,
  `website/`, release tagging (`docs/31_releases.md`). Reviews every merge.
- **Ahmed Abd alla:** `app/ingestion/` (robots, http_client, ratelimit, sources), compliance evidence (`ingestion_http_log`).
- **Ahmed Medhat:** `app/ingestion/cleaning.py`, `app/ingestion/dedupe.py`, `app/etl/loader.py` support.
- **Eng. Alaa Nasser:** `app/models/`, `db/schema + views.sql + analysis/`, `app/etl/dq.py`.
- **legecy007:** `frontend/` (theme, sidebar, mobile, scrollbars, icons, silent reload, PWA).
- **Mennatullah Ahmed:** `dags/`, `docker/`, `docker-compose.yml`, `.github/workflows/`, `Makefile`, `scripts/`.
