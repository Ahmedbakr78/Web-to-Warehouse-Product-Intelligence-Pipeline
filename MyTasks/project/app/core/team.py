"""Team source of truth: members, roles, weights and function ownership.

Mirrors the ``app/core/features.py`` pattern — one Python structure feeds the
REST API (``GET /meta/team``), the docs (``docs/00_team.md``), the website and
the README, so the credit surface can never drift from the shipped record.
Weights sum to exactly 100.
"""

from __future__ import annotations

from typing import Any

TEAM: list[dict[str, Any]] = [
    {
        "member": "Ahmed (78102)",
        "github": "Ahmedbakr78",
        "github_url": "https://github.com/Ahmedbakr78",
        "role": "Team Lead + Backend/API + Documentation + 9 ETL Stages Owner",
        "weight": 28,
        "component": "FastAPI + 30 Docs + 9 ETL Stages + Integration",
        "lead": True,
        "functions": [
            "FastAPI platform: 23 routers, auth (JWT + API keys), RBAC, exports, webhooks",
            "9-stage ETL orchestrator used identically by CLI, REST API and Airflow",
            "Integration transport: in-process/API fallback between Airflow 1.4 and app 2.0",
            "Feature catalogue as code (app/core/features.py) + /meta/features API",
            "Team catalogue as code (this module) + /meta/team API",
            "30 numbered documents, 80+ Mermaid diagrams, README/website/docs alignment",
            "Release management: versioning, changelog, tags, GitHub releases",
            "Cross-cutting quality: ruff/mypy/pytest gates, stats-drift CI, review of every merge",
        ],
    },
    {
        "member": "Ahmed Abd alla",
        "github": "01124758140",
        "github_url": "https://github.com/01124758140",
        "role": "Ingestion & Compliance Lead",
        "weight": 15,
        "component": "robots.txt + 34 sources + rate limiter",
        "lead": False,
        "functions": [
            "robots.txt gate (RFC 9309) in the transport layer",
            "34 source adapters: APIs + BeautifulSoup/Scrapy HTML + synthetic",
            "Token-bucket rate limiting, sliding-window ceiling, circuit breaker",
            "Conditional GET (ETag/Last-Modified) revalidation",
            "Per-request HTTP audit log",
        ],
    },
    {
        "member": "Ahmed Medhat",
        "github": "AhmedMedhatFarouk",
        "github_url": "https://github.com/AhmedMedhatFarouk",
        "role": "ETL & Cleaning Lead",
        "weight": 14,
        "component": "29-step cleaner + Dedupe + ETL support",
        "lead": False,
        "functions": [
            "29-step product-name/category normalisation engine",
            "18+ currency price parsing + offline FX to USD",
            "4-signal fuzzy dedupe (fingerprint + blocking + similarity)",
            "Rating/availability vocabularies",
        ],
    },
    {
        "member": "Eng. Alaa Nasser",
        "github": "AlaaNasser-tech",
        "github_url": "https://github.com/AlaaNasser-tech",
        "role": "Database & Data Quality Lead",
        "weight": 14,
        "component": "29 tables + 23 views + 12 DQ rules",
        "lead": False,
        "functions": [
            "Kimball star schema, dialect-portable PostgreSQL/MySQL",
            "23 analytical views + 15 analysis SQL scripts",
            "12-rule DQ framework across 6 dimensions + weighted score",
            "Change detection: price bands, lifecycle events, catalog reconciliation",
        ],
    },
    {
        "member": "legecy007",
        "github": "legecy007",
        "github_url": "https://github.com/legecy007",
        "role": "Frontend / Dashboard Lead",
        "weight": 15,
        "component": "React 19 + 21 screens + PWA + Themes",
        "lead": False,
        "functions": [
            "React 19 + TypeScript + Tailwind + ReCharts dashboard (21 screens)",
            "Light/dark/midnight/high-contrast themes, zero-flash pre-paint",
            "Mobile-first: drawer sidebar, phone tab bar, safe areas, PWA",
            "Silent-reload data policy, command palette, modern scrollbars",
        ],
    },
    {
        "member": "Mennatullah Ahmed",
        "github": "mennatullahahmed01-debug",
        "github_url": "https://github.com/mennatullahahmed01-debug",
        "role": "DevOps & Orchestration Lead",
        "weight": 14,
        "component": "Airflow + Docker + CI/CD + Scripts",
        "lead": False,
        "functions": [
            "Airflow 2.10 DAG: 14 operators, branch-on-changes, notify/report fan-out",
            "6-service Docker Compose stack + Dockerfiles",
            "GitHub Actions CI (backend, parity, smoke, frontend, docs, stats)",
            "Makefile (30+ targets), run.sh / run-full-app.sh / run-local.sh",
        ],
    },
]


def team() -> dict[str, Any]:
    """The team in the shape served by ``GET /meta/team``."""
    return {
        "track": "Data Engineering",
        "program": "DEPI Digital Egypt Pioneers Initiative",
        "total_weight": sum(member["weight"] for member in TEAM),
        "member_count": len(TEAM),
        "lead": next(member for member in TEAM if member["lead"])["github"],
        "members": [dict(member) for member in TEAM],
    }


__all__ = ["TEAM", "team"]
