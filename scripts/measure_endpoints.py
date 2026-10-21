#!/usr/bin/env python3
"""Time the dashboard's read endpoints against a running API.

The latency table in ``docs/35_performance_and_capacity.md`` is produced by
this script, so the numbers can be re-measured instead of remembered. It
issues every request a dashboard page load makes and reports the median of
``--repeat`` runs - the median, because a single run is dominated by whatever
else the machine happened to be doing.

Usage::

    python3 scripts/measure_endpoints.py [--url http://localhost:8000] [--repeat 7]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]

#: (label, path) for every read a dashboard page load issues.
ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("dashboard · KPI", "/api/v1/analytics/kpi?days=30"),
    ("dashboard · trend", "/api/v1/analytics/trend?days=30"),
    ("dashboard · price trend", "/api/v1/analytics/price-trend?days=30"),
    ("dashboard · change summary", "/api/v1/changes/summary?days=30"),
    ("dashboard · quality", "/api/v1/quality/latest"),
    ("products · list", "/api/v1/products?page=1&page_size=25"),
    ("products · facets", "/api/v1/products/facets"),
    ("changes · feed", "/api/v1/changes/price?days=90&page=1&page_size=25"),
    ("analytics · categories", "/api/v1/analytics/categories?limit=20"),
    ("analytics · brands", "/api/v1/analytics/brands?limit=20"),
    ("analytics · availability", "/api/v1/analytics/availability"),
    ("analytics · sources", "/api/v1/analytics/sources"),
    ("analytics · category index", "/api/v1/analytics/category-index?days=30"),
    ("analytics · top movers", "/api/v1/analytics/top-movers?limit=20"),
    ("catalog · summary", "/api/v1/catalog/summary"),
    ("catalog · reconciliation", "/api/v1/catalog/reconciliation?page=1&page_size=25"),
    ("pipeline · runs", "/api/v1/pipeline/runs?page=1&page_size=25"),
    ("pipeline · stages", "/api/v1/pipeline/stages"),
    ("quality · rules", "/api/v1/quality/rules"),
    ("sources · registry", "/api/v1/sources"),
    ("audit · http log", "/api/v1/audit/http?page=1&page_size=50"),
    ("meta · features", "/api/v1/meta/features"),
)


def login(base_url: str) -> str:
    response = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin@12345"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def measure(base_url: str, token: str, repeat: int) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0) as client:
        for label, path in ENDPOINTS:
            timings: list[float] = []
            status = 0
            size = 0
            for _ in range(repeat):
                started = time.perf_counter()
                response = client.get(f"{base_url}{path}", headers=headers)
                timings.append((time.perf_counter() - started) * 1000)
                status = response.status_code
                size = len(response.content)
            results.append(
                {
                    "endpoint": label,
                    "path": path,
                    "status": status,
                    "bytes": size,
                    "ms_median": round(statistics.median(timings), 1),
                    "ms_min": round(min(timings), 1),
                    "ms_max": round(max(timings), 1),
                }
            )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    base_url = args.url.rstrip("/")
    token = login(base_url)
    results = measure(base_url, token, max(1, args.repeat))

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    print(f"api: {base_url}   repeat: {args.repeat}\n")
    print(f"{'endpoint':30s} {'status':>7s} {'bytes':>9s} {'median ms':>11s} {'min':>8s} {'max':>8s}")
    print("-" * 80)
    for row in sorted(results, key=lambda item: -item["ms_median"]):
        print(
            f"{row['endpoint']:30s} {row['status']:>7d} {row['bytes']:>9d} "
            f"{row['ms_median']:>11.1f} {row['ms_min']:>8.1f} {row['ms_max']:>8.1f}"
        )
    total = sum(row["ms_median"] for row in results)
    print(f"\nsum of the medians for one pass over every endpoint: {total:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
