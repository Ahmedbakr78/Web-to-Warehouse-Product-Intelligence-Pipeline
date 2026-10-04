#!/usr/bin/env python3
"""End-to-end API smoke test.

Starts the FastAPI app with uvicorn, exercises every router (auth, products,
changes, analytics, pipeline, quality, catalog, sources, query lab, account) and
prints a pass/fail table.  Run it with::

    .venv/bin/python scripts/api_smoke.py            # start a temporary server
    .venv/bin/python scripts/api_smoke.py --url URL  # test an already running server
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GREEN, RED, YELLOW, CYAN, DIM, NC = (
    "\033[0;32m",
    "\033[0;31m",
    "\033[0;33m",
    "\033[0;36m",
    "\033[2m",
    "\033[0m",
)

# (method, path, expected_status, needs_auth, note)
CHECKS: list[tuple[str, str, int, bool, str]] = [
    ("GET", "/api/v1/health", 200, False, "liveness + database probe"),
    ("GET", "/api/v1/health/ready", 200, False, "readiness"),
    ("GET", "/api/v1/meta", 200, False, "feature catalogue"),
    ("GET", "/api/v1/meta/tables", 200, False, "table inventory"),
    ("GET", "/api/v1/stats/tables", 200, False, "row counts"),
    ("POST", "/api/v1/auth/login", 200, False, "admin login"),
    ("GET", "/api/v1/auth/me", 200, True, "profile"),
    ("GET", "/api/v1/auth/session", 200, True, "session metadata"),
    ("GET", "/api/v1/auth/demo-accounts", 200, False, "documented credentials"),
    ("GET", "/api/v1/products", 200, True, "product list"),
    ("GET", "/api/v1/products?page=1&page_size=5&sort_by=price&sort_dir=desc", 200, True, "sorted paging"),
    ("GET", "/api/v1/products?q=phone&min_price=10&max_price=900", 200, True, "filtered search"),
    ("GET", "/api/v1/products/facets", 200, True, "facet counts"),
    ("GET", "/api/v1/products/categories", 200, True, "category tree"),
    ("GET", "/api/v1/products/search/suggest?q=sam", 200, True, "type-ahead"),
    ("GET", "/api/v1/products/1", 200, True, "product detail"),
    ("GET", "/api/v1/products/1/history?limit=20", 200, True, "price history"),
    ("GET", "/api/v1/products/1/duplicates", 200, True, "duplicate candidates"),
    ("GET", "/api/v1/products/1/catalog", 200, True, "catalog links"),
    ("GET", "/api/v1/products/999999", 404, True, "unknown product -> 404"),
    ("GET", "/api/v1/changes/price", 200, True, "price change feed"),
    ("GET", "/api/v1/changes/top-movers?limit=5", 200, True, "top movers"),
    ("GET", "/api/v1/changes/events", 200, True, "lifecycle events"),
    ("GET", "/api/v1/changes/new", 200, True, "new products"),
    ("GET", "/api/v1/changes/removed", 200, True, "removed products"),
    ("GET", "/api/v1/changes/categories", 200, True, "category changes"),
    ("GET", "/api/v1/changes/category-drift", 200, True, "assortment drift"),
    ("GET", "/api/v1/changes/summary", 200, True, "change summary"),
    ("GET", "/api/v1/analytics/kpi", 200, True, "KPI cards"),
    ("GET", "/api/v1/analytics/trend?days=30", 200, True, "daily trend"),
    ("GET", "/api/v1/analytics/price-trend?days=30", 200, True, "price trend"),
    ("GET", "/api/v1/analytics/categories", 200, True, "category breakdown"),
    ("GET", "/api/v1/analytics/brands", 200, True, "brand leaderboard"),
    ("GET", "/api/v1/analytics/availability", 200, True, "availability mix"),
    ("GET", "/api/v1/analytics/sources", 200, True, "source coverage"),
    ("GET", "/api/v1/analytics/category-index?days=30", 200, True, "category price index"),
    ("GET", "/api/v1/analytics/report/price-changes", 200, True, "SQL report"),
    ("GET", "/api/v1/analytics/report/compliance", 200, True, "compliance report"),
    ("GET", "/api/v1/analytics/export/products.csv", 200, True, "CSV export"),
    ("GET", "/api/v1/pipeline/runs", 200, True, "run history"),
    ("GET", "/api/v1/pipeline/runs/latest", 200, True, "latest run detail"),
    ("GET", "/api/v1/pipeline/sources/status", 200, True, "source health"),
    ("GET", "/api/v1/pipeline/stages", 200, True, "stage catalogue"),
    ("GET", "/api/v1/pipeline/schedule", 200, True, "scheduler status"),
    ("GET", "/api/v1/quality/latest", 200, True, "latest DQ report"),
    ("GET", "/api/v1/quality/rules", 200, True, "rule catalogue"),
    ("GET", "/api/v1/quality/results", 200, True, "DQ history"),
    ("GET", "/api/v1/quality/trend", 200, True, "DQ score trend"),
    ("GET", "/api/v1/quality/summary", 200, True, "quality posture"),
    ("GET", "/api/v1/catalog/products", 200, True, "internal catalog"),
    ("GET", "/api/v1/catalog/reconciliation", 200, True, "reconciliation"),
    ("GET", "/api/v1/catalog/summary", 200, True, "reconciliation KPIs"),
    ("GET", "/api/v1/catalog/opportunities", 200, True, "pricing opportunities"),
    ("GET", "/api/v1/sources", 200, True, "source registry"),
    ("GET", "/api/v1/sources/robots", 200, True, "robots.txt cache"),
    ("GET", "/api/v1/sources/local_demo/preview?limit=3", 200, True, "raw preview"),
    ("GET", "/api/v1/queries/views", 200, True, "analytical views"),
    ("GET", "/api/v1/queries/tables", 200, True, "queryable tables"),
    ("GET", "/api/v1/queries/examples", 200, True, "starter queries"),
    ("POST", "/api/v1/queries/execute", 200, True, "read-only SQL"),
    ("POST", "/api/v1/queries/execute", 422, True, "write SQL rejected"),
    ("GET", "/api/v1/users/me", 200, True, "my profile"),
    ("PATCH", "/api/v1/users/me", 200, True, "update preferences"),
    ("GET", "/api/v1/users", 200, True, "user admin"),
    ("GET", "/api/v1/users/stats", 200, True, "usage statistics"),
    ("GET", "/api/v1/saved-views", 200, True, "saved views"),
    ("POST", "/api/v1/saved-views", 201, True, "create saved view"),
    ("POST", "/api/v1/alerts", 201, True, "create alert rule"),
    ("GET", "/api/v1/alerts", 200, True, "alert rules"),
    ("POST", "/api/v1/alerts/evaluate", 200, True, "evaluate alerts"),
    ("GET", "/api/v1/notifications", 200, True, "notifications"),
    ("GET", "/api/v1/settings", 200, True, "settings"),
    ("GET", "/api/v1/settings/groups", 200, True, "settings grouped"),
    ("GET", "/api/v1/audit/http", 200, True, "http audit log"),
    ("GET", "/api/v1/audit/compliance", 200, True, "compliance summary"),
    ("GET", "/api/v1/products", 401, True, "unauthenticated -> 401", True),
    ("POST", "/api/v1/pipeline/run/sync", 200, True, "admin may trigger a run"),
    ("POST", "/api/v1/pipeline/run/sync", 403, True, "viewer role denied", False, "viewer"),
]


def wait_for(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def run_checks(base_url: str, token: str, role_tokens: dict[str, str] | None = None) -> tuple[int, int, int]:
    role_tokens = role_tokens or {}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    passed = failed = skipped = 0
    failures: list[str] = []

    for check in CHECKS:
        method, path, expected, needs_auth, note = check[:5]
        no_auth = len(check) > 5 and check[5] is True
        role = check[6] if len(check) > 6 else "admin"
        url = f"{base_url}{path}"
        request_headers = {} if no_auth else dict(headers)
        if role != "admin":
            request_headers = {"Authorization": f"Bearer {role_tokens.get(role, '')}"}
        payload = None
        if method == "POST" and path.endswith("/auth/login"):
            payload = {
                "email": os.getenv("SMOKE_EMAIL", "admin@example.com"),
                "password": os.getenv("SMOKE_PASSWORD", "Admin@12345"),
            }
        elif method == "POST" and path.endswith("/queries/execute"):
            payload = {"sql": "SELECT 1 AS ok"} if expected == 200 else {"sql": "DELETE FROM dim_product"}
        elif method == "POST" and path.endswith("/saved-views"):
            payload = {
                "name": f"smoke-test-view-{int(time.time())}",
                "entity": "products",
                "filters": {"in_stock": True},
            }
        elif method == "POST" and path.endswith("/alerts"):
            payload = {
                "name": f"smoke-alert-{int(time.time())}",
                "metric": "price_change_pct",
                "operator": "lt",
                "threshold": -15,
            }
        elif method == "PATCH" and path.endswith("/users/me"):
            payload = {"theme": "system", "rows_per_page": 25}
        elif method == "POST":
            payload = {"sources": ["local_demo"], "limit_per_source": 2, "trigger": "smoke_test"}

        if needs_auth and not token:
            skipped += 1
            print(f"{DIM}  skip {method:6} {path[:52]:54} (no token){NC}")
            continue

        try:
            response = httpx.request(method, url, headers=request_headers, json=payload, timeout=90.0)
        except Exception as exc:
            failed += 1
            failures.append(f"{method} {path} -> {type(exc).__name__}")
            print(f"{RED}  FAIL{NC} {method:6} {path[:52]:54} {RED}{type(exc).__name__}{NC}")
            continue

        if response.status_code == expected:
            passed += 1
            size = len(response.content)
            print(f"{GREEN}  pass{NC} {method:6} {path[:52]:54} {DIM}{size:>7} bytes  {note}{NC}")
        else:
            failed += 1
            detail = response.text[:120].replace("\n", " ")
            failures.append(f"{method} {path} -> {response.status_code} (expected {expected})")
            print(
                f"{RED}  FAIL{NC} {method:6} {path[:52]:54} {RED}{response.status_code}{NC} {DIM}{detail}{NC}"
            )

    print()
    print(f"{CYAN}{'=' * 78}{NC}")
    colour = GREEN if failed == 0 else RED
    print(f"{colour}  {passed} passed, {failed} failed, {skipped} skipped{NC}")
    if failures:
        print(f"{RED}  failures:{NC}")
        for item in failures:
            print(f"    - {item}")
    print(f"{CYAN}{'=' * 78}{NC}")
    return passed, failed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="API smoke test")
    parser.add_argument("--url", default=None, help="Base URL of a running API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()

    process: subprocess.Popen[bytes] | None = None
    base_url = args.url

    if base_url is None:
        base_url = f"http://{args.host}:{args.port}"
        env = dict(os.environ)
        python = str(ROOT / ".venv" / "bin" / "python")
        command = [
            python if Path(python).exists() else sys.executable,
            "-m",
            "uvicorn",
            "app.api.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--log-level",
            "warning",
        ]
        print(f"{CYAN}starting API on {base_url}{NC}")
        process = subprocess.Popen(
            command, cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if not wait_for(f"{base_url}/api/v1/health"):
            print(f"{RED}API did not become healthy in time{NC}")
            if process:
                process.send_signal(signal.SIGINT)
            return 2

    token = ""
    try:
        login = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={
                "email": os.getenv("SMOKE_EMAIL", "admin@example.com"),
                "password": os.getenv("SMOKE_PASSWORD", "Admin@12345"),
            },
            timeout=30.0,
        )
        token = login.json().get("access_token", "") if login.status_code == 200 else ""
        if not token:
            print(f"{YELLOW}login failed ({login.status_code}) - authenticated checks will be skipped{NC}")
    except Exception as exc:
        print(f"{YELLOW}login error: {exc}{NC}")

    print(f"{CYAN}running {len(CHECKS)} checks against {base_url}{NC}\n")
    try:
        role_tokens: dict[str, str] = {}
        viewer = httpx.post(
            f"{base_url}/api/v1/auth/login",
            json={"email": "viewer@example.com", "password": "Viewer@12345"},
            timeout=30.0,
        )
        if viewer.status_code == 200:
            role_tokens["viewer"] = viewer.json().get("access_token", "")
        _passed, failed, _skipped = run_checks(base_url, token, role_tokens)
    finally:
        if process is not None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
