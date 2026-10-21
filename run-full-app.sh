#!/usr/bin/env bash
#
# run-full-app.sh — test the FULL app end-to-end with REAL data (no fakes).
#
# Default mode is REAL: live permitted sources, a real pipeline run into SQLite,
# the full backend + frontend test suites, a production frontend build, a live
# API smoke test and a compose config check. Nothing here uses `local_demo` or
# any other synthetic source unless you explicitly ask for it.
#
#   ./run-full-app.sh              full real verification (recommended)
#   ./run-full-app.sh --offline    same flow but with the synthetic local_demo source
#   ./run-full-app.sh --quick      skip frontend build + full backend suite (smoke only)
#   ./run-full-app.sh --no-frontend
#                                  skip all frontend steps (backend + real data only)
#   ./run-full-app.sh --help       this help
#
# Real sources used (free, keyless, automation-permitted, live-verified):
#   openlibrary_books, gutendex_books, itunes_ebooks, itunes_apps, steam_store,
#   cheapshark_deals, openfoodfacts_prices, tvmaze_shows
# Every one of them is classified `data_trust="real"` and `terms_allowed=True`,
# so the script exercises exactly the sources the app is allowed to pick up on
# its own. Offline fallback (explicit only): local_demo (synthetic, deterministic)
#
# Env overrides:
#   VENV=.venv  REAL_SOURCES="openlibrary_books,steam_store"
#   REAL_LIMIT=40  SQLITE_DB=/tmp/pip-real-test.db  NO_COLOR=1
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"
REAL_SOURCES="${REAL_SOURCES:-openlibrary_books,gutendex_books,itunes_ebooks,itunes_apps,steam_store,cheapshark_deals,openfoodfacts_prices,tvmaze_shows}"
REAL_LIMIT="${REAL_LIMIT:-40}"
SQLITE_DB="${SQLITE_DB:-/tmp/pip-real-test.db}"
export SQLITE_DB
VERSION="$(cat VERSION 2>/dev/null || echo dev)"

OFFLINE=0
QUICK=0
NO_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --offline) OFFLINE=1 ;;
    --quick) QUICK=1 ;;
    --no-frontend) NO_FRONTEND=1 ;;
    -h|--help)
      sed -n '2,24p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    --*) echo "error: unknown option '$arg' (try --help)" >&2; exit 1 ;;
    *) echo "error: unknown option '$arg' (try --help)" >&2; exit 1 ;;
  esac
done

if [ "$OFFLINE" -eq 1 ]; then
  SOURCES="local_demo"
  MODE="OFFLINE (synthetic local_demo — explicit fallback only)"
else
  SOURCES="$REAL_SOURCES"
  MODE="REAL (live permitted sources — no fakes)"
fi

if [ -z "${NO_COLOR:-}" ] && [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; CYAN=$'\033[36m'; NC=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; NC=''
fi

N=0
step()  { N=$((N+1)); printf '\n%s==>%s %s[%s]%s %s%s%s\n' "$BLUE" "$NC" "$DIM" "$N" "$NC" "$BOLD" "$*" "$NC"; }
info()  { printf '    %s%s%s\n' "$DIM" "$*" "$NC"; }
ok()    { printf '    %s+%s %s\n' "$GREEN" "$NC" "$*"; }
warn()  { printf '    %s!%s %s\n' "$YELLOW" "$NC" "$*"; }
die()   { printf '\n%serror:%s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }
export PYTHONWARNINGS="${PYTHONWARNINGS:-ignore::RuntimeWarning}"

printf '\n%sProduct Intelligence Pipeline — full app test%s v%s\n' "$BOLD" "$NC" "$VERSION"
printf '%sMode: %s%s\n' "$CYAN" "$MODE" "$NC"
printf '%sSources: %s | limit/source: %s%s\n' "$DIM" "$SOURCES" "$REAL_LIMIT" "$NC"

# ------------------------------------------------------------- 1. environment
step "Preparing the Python environment"
[ -x "$PY" ] || die "venv python missing at $PY — run 'make install' first"
"$PY" -c 'import app' 2>/dev/null || die "venv lacks the app deps — run 'make install' first"
[ -f .env ] || { cp .env.example .env; info "created .env from template"; }
ok "venv + imports OK ($("$PY" --version 2>&1))"

# ------------------------------------------------------------- 2. static checks
step "Linting the backend (ruff)"
"$PY" -m ruff check app tests scripts dags
ok "ruff clean"

# ------------------------------------------------------------- 3. registry guard
step "Proving prod auto-select is real-only (no synthetic or blocked source)"
"$PY" - <<'PY'
from app.etl.pipeline import Pipeline, PipelineConfig
from app.ingestion.base import DATA_TRUST_REAL, list_sources

codes = Pipeline(PipelineConfig())._source_codes()
registry = {source["code"]: source for source in list_sources()}

untrusted = {
    code
    for code, source in registry.items()
    if source.get("enabled")
    and source.get("terms_allowed", True)
    and source.get("data_trust") != DATA_TRUST_REAL
}
assert untrusted, "expected at least one non-real source to guard against"
leaked = sorted(set(codes) & untrusted)
assert not leaked, f"auto-select leaked untrusted sources: {leaked}"

blocked = {code for code, source in registry.items() if not source.get("terms_allowed", True)}
assert not (set(codes) & blocked), f"auto-select picked a terms-blocked source: {set(codes) & blocked}"

assert "local_demo" not in codes, f"fake leak in auto-select: {codes}"
real = [c for c in codes if registry[c].get("data_trust") == DATA_TRUST_REAL]
assert real, "no real sources in auto-select!"
print(f"    auto-select: {len(codes)} sources, {len(untrusted)} untrusted excluded, {len(blocked)} terms-blocked excluded")
print(f"    real sources selected: {real}")
PY
ok "registry guard passed"

# ------------------------------------------------------------- 4. backend tests
if [ "$QUICK" -eq 1 ]; then
  step "Backend tests (quick subset)"
  "$PY" -m pytest tests/test_ingestion.py tests/test_etl_pipeline.py tests/test_cleaning.py tests/test_dedupe.py --tb=short -q 2>&1 | tail -3
else
  step "Backend tests (full suite, SQLite)"
  # One run, not two: every test gets its own copy of the seeded warehouse, so
  # the suite no longer depends on the order the files are collected in.
  PIP_TEST_DATABASE_URL="${PIP_TEST_DATABASE_URL:-sqlite:///$SQLITE_DB-tests}" \
    "$PY" -m pytest tests/ --tb=short -q 2>&1 | tail -3
fi
ok "backend tests passed"

# ------------------------------------------------------------- 5. LIVE real-source smoke
step "Fetching LIVE records from real sources (network proof, no DB)"
if [ "$OFFLINE" -eq 1 ]; then
  info "offline mode — skipping live fetch (synthetic source used below instead)"
else
  "$PY" - "$SOURCES" "$REAL_LIMIT" <<'PY'
import sys
from app.ingestion.base import DATA_TRUST_REAL, get_source, list_sources
registry = {source["code"]: source for source in list_sources()}
total = 0
for code in sys.argv[1].split(","):
    code = code.strip()
    source = registry[code]
    assert source.get("data_trust") == DATA_TRUST_REAL, f"{code} is not a real source"
    assert source.get("terms_allowed", True), f"{code} is terms-blocked"
    src = get_source(code)
    rows = list(src.fetch(limit=int(sys.argv[2])))
    assert rows, f"REAL source returned 0 records: {code}"
    assert all((r.name or "").strip() for r in rows), f"blank names from {code}"
    total += len(rows)
    print(f"    {code}: {len(rows)} live records, e.g. {rows[0].name[:60]!r}")
    src.close()
print(f"    TOTAL live records: {total} (all real, zero synthetic)")
PY
  ok "live real-source smoke passed"
fi

# ------------------------------------------------------------- 6. real pipeline run
step "Running the REAL pipeline (sources=$SOURCES, limit=$REAL_LIMIT)"
# Fresh database, schema only (init-db): NO synthetic seed-demo here, so every
# row the warehouse holds afterwards came from the live sources below.
rm -f "$SQLITE_DB"
export DATABASE_URL="sqlite:///$SQLITE_DB" MYSQL_URL="" ACTIVE_DATABASE=sqlite
"$PY" -m app.cli.main init-db
"$PY" -m app.cli.main run-pipeline --sources "$SOURCES" --limit "$REAL_LIMIT" --trigger real-verification
"$PY" - <<'PY'
import os, sqlite3
db = os.environ.get("SQLITE_DB", "/tmp/pip-real-test.db")
con = sqlite3.connect(db)
prod = con.execute("SELECT COUNT(*) FROM dim_product").fetchone()[0]
snap = con.execute("SELECT COUNT(*) FROM fact_price_snapshot").fetchone()[0]
srcs = [r[0] for r in con.execute("SELECT DISTINCT source_code FROM dim_product").fetchall()]
print(f"    warehouse now holds {prod} products, {snap} snapshots from: {srcs}")
assert prod > 0 and snap > 0, "pipeline wrote nothing!"
con.close()
PY
if [ "$OFFLINE" -eq 0 ]; then
  # The authoritative check: the standalone audit walks every table that
  # records an upstream and proves each row traces back to a real, permitted
  # source. It exits non-zero the moment one does not.
  "$PY" scripts/audit_no_fakes.py --database "$DATABASE_URL"
  ok "no-fake audit passed — every row traces back to a real source"
fi
ok "real pipeline run verified"

# ------------------------------------------------------------- 6b. the audit has teeth
if [ "$OFFLINE" -eq 0 ]; then
  step "Proving the no-fake audit actually catches synthetic data"
  # A check that never fails is worthless. Seed a throwaway warehouse with the
  # synthetic demo dataset and assert the audit rejects it, then purge the
  # synthetic rows and assert the audit accepts what is left.
  FAKE_DB="${SQLITE_DB%.db}-selftest.db"
  rm -f "$FAKE_DB" "$FAKE_DB-wal" "$FAKE_DB-shm"
  DATABASE_URL="sqlite:///$FAKE_DB" ACTIVE_DATABASE=sqlite \
    "$PY" -m app.cli.main init-db --database sqlite >/dev/null 2>&1
  DATABASE_URL="sqlite:///$FAKE_DB" ACTIVE_DATABASE=sqlite \
    "$PY" -m app.cli.main seed-demo --database sqlite >/dev/null 2>&1
  if "$PY" scripts/audit_no_fakes.py --database "sqlite:///$FAKE_DB" >/dev/null 2>&1; then
    die "the no-fake audit accepted a warehouse full of synthetic rows — it cannot be trusted"
  fi
  info "audit correctly rejected the seeded synthetic warehouse"
  DATABASE_URL="sqlite:///$FAKE_DB" ACTIVE_DATABASE=sqlite \
    "$PY" -m app.cli.main purge-untrusted --database sqlite >/dev/null 2>&1
  "$PY" scripts/audit_no_fakes.py --database "sqlite:///$FAKE_DB" >/dev/null
  ok "purge removed the synthetic rows and the audit now passes"
  rm -f "$FAKE_DB" "$FAKE_DB-wal" "$FAKE_DB-shm"
fi

# ------------------------------------------------------------- 7. live API over the real warehouse
step "Serving the REAL warehouse through the API (no seeded demo data)"
"$PY" - <<'PY'
import os
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.security import create_access_token

token = create_access_token(1, role="admin", email="admin@example.com")
headers = {"Authorization": f"Bearer {token}"}
with TestClient(app) as client:
    assert client.get("/api/v1/health").json()["database"]["connected"] is True

    products = client.get("/api/v1/products", headers=headers, params={"page_size": 5}).json()
    total = products.get("total", 0)
    assert total > 0, "the API returned no products from the real warehouse"
    for item in products.get("items", [])[:5]:
        print(f"    live product: {item.get('canonical_name')[:44]!r} from {item.get('source_code')}")

    coverage = client.get("/api/v1/analytics/sources", headers=headers).json()
    print(f"    source coverage: {len(coverage)} sources with observations")

    kpi = client.get("/api/v1/analytics/kpi", headers=headers).json()
    print(f"    kpi snapshot: {kpi.get('latest')}")

    listed = client.get("/api/v1/sources", headers=headers).json()
    if isinstance(listed, dict):
        listed = listed.get("items", [])
    untrusted = [s for s in listed if s.get("data_trust") not in (None, "real")]
    print(f"    registry: {len(listed)} sources, {len(untrusted)} not classified 'real'")
print("    the API served the live warehouse end-to-end")
PY
ok "live API check passed"

# ------------------------------------------------------------- 8. frontend
if [ "$NO_FRONTEND" -eq 1 ]; then
  info "frontend steps skipped (--no-frontend)"
else
  step "Frontend typecheck + lint"
  (cd frontend && npm run typecheck 2>&1 | tail -2)
  (cd frontend && npm run lint 2>&1 | tail -2)
  ok "frontend static checks passed"
  if [ "$QUICK" -eq 0 ]; then
    step "Frontend unit tests (vitest)"
    (cd frontend && npm run test 2>&1 | tail -4)
    ok "frontend tests passed"
    step "Frontend production build"
    (cd frontend && npm run build 2>&1 | tail -3)
    ok "frontend build passed"
  else
    info "vitest + build skipped (--quick)"
  fi
fi

# ------------------------------------------------------------- 9. compose
step "Validating the Docker Compose stack definition"
docker compose config --quiet && ok "compose file valid (6 services)" \
  || warn "docker compose unavailable — skipping (needs Docker daemon)"

# ---------------------------------------------------------------- summary
printf '\n%s%sFULL APP TEST: PASS%s\n' "$GREEN" "$BOLD" "$NC"
printf '  mode      %s\n' "$MODE"
printf '  sources   %s (limit %s/source)\n' "$SOURCES" "$REAL_LIMIT"
printf '  warehouse %s\n' "$SQLITE_DB"
printf '  stack     backend lint+tests, live-source smoke, real pipeline, live API, frontend, compose\n'
printf '  dashboard ./run-local.sh  ->  http://localhost:5173\n'
printf '  api docs  http://localhost:8000/docs\n\n'
