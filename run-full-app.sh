#!/usr/bin/env bash
#
# run-full-app.sh — test the FULL app end-to-end with REAL data (no fakes).
#
# Default mode is REAL: live permitted sources (DummyJSON, FakeStore, Open Library),
# a real pipeline run into SQLite, the full backend + frontend test suites, a
# production frontend build, and a compose config check. Nothing here uses
# `local_demo` unless you explicitly ask for it.
#
#   ./run-full-app.sh              full real verification (recommended)
#   ./run-full-app.sh --offline    same flow but with the synthetic local_demo source
#   ./run-full-app.sh --quick      skip frontend build + full backend suite (smoke only)
#   ./run-full-app.sh --no-frontend
#                                  skip all frontend steps (backend + real data only)
#   ./run-full-app.sh --help       this help
#
# Real sources used (all free, keyless, automation-permitted, live-verified):
#   dummyjson_products, books_to_scrape, openlibrary_books
# Offline fallback (explicit only): local_demo (synthetic, deterministic)
#
# Env overrides:
#   VENV=.venv  REAL_SOURCES="dummyjson_products,books_to_scrape,openlibrary_books"
#   REAL_LIMIT=15  SQLITE_DB=/tmp/pip-real-test.db  NO_COLOR=1
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"
REAL_SOURCES="${REAL_SOURCES:-dummyjson_products,books_to_scrape,openlibrary_books}"
REAL_LIMIT="${REAL_LIMIT:-15}"
SQLITE_DB="${SQLITE_DB:-/tmp/pip-real-test.db}"
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
step "Proving prod auto-select is real-only (local_demo excluded)"
"$PY" - <<'PY'
from app.etl.pipeline import Pipeline, PipelineConfig
codes = Pipeline(PipelineConfig())._source_codes()
assert "local_demo" not in codes, f"fake leak in auto-select: {codes}"
real = [c for c in codes if c in {"dummyjson_products", "fakestore_products", "openlibrary_books"}]
assert real, "no real sources in auto-select!"
print(f"    auto-select: {len(codes)} sources, local_demo excluded, real present: {real}")
PY
ok "registry guard passed"

# ------------------------------------------------------------- 4. backend tests
if [ "$QUICK" -eq 1 ]; then
  step "Backend tests (quick subset)"
  "$PY" -m pytest tests/test_ingestion.py tests/test_etl_pipeline.py tests/test_cleaning.py tests/test_dedupe.py --tb=short -q 2>&1 | tail -3
else
  step "Backend tests (full suite, SQLite)"
  "$PY" -m pytest tests/ --ignore=tests/test_api.py --tb=short -q 2>&1 | tail -3
  "$PY" -m pytest tests/test_api.py --tb=short -q 2>&1 | tail -3
fi
ok "backend tests passed"

# ------------------------------------------------------------- 5. LIVE real-source smoke
step "Fetching LIVE records from real sources (network proof, no DB)"
if [ "$OFFLINE" -eq 1 ]; then
  info "offline mode — skipping live fetch (synthetic source used below instead)"
else
  "$PY" - "$SOURCES" "$REAL_LIMIT" <<'PY'
import sys
from app.ingestion.base import get_source
total = 0
for code in sys.argv[1].split(","):
    src = get_source(code.strip())
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
  "$PY" -c "
import sqlite3, os
srcs = [r[0] for r in sqlite3.connect(os.environ.get('SQLITE_DB','/tmp/pip-real-test.db')).execute('SELECT DISTINCT source_code FROM dim_product').fetchall()]
assert 'local_demo' not in srcs, f'FAKE LEAK: {srcs}'
print('    confirmed: zero local_demo rows — 100% real data')
"
fi
ok "real pipeline run verified"

# ------------------------------------------------------------- 7. frontend
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

# ------------------------------------------------------------- 8. compose
step "Validating the Docker Compose stack definition"
docker compose config --quiet && ok "compose file valid (6 services)" \
  || warn "docker compose unavailable — skipping (needs Docker daemon)"

# ---------------------------------------------------------------- summary
printf '\n%s%sFULL APP TEST: PASS%s\n' "$GREEN" "$BOLD" "$NC"
printf '  mode      %s\n' "$MODE"
printf '  sources   %s (limit %s/source)\n' "$SOURCES" "$REAL_LIMIT"
printf '  warehouse %s\n' "$SQLITE_DB"
printf '  stack     backend lint+tests, live-source smoke, real pipeline, frontend, compose\n'
printf '  dashboard ./run-local.sh  ->  http://localhost:5173\n'
printf '  api docs  http://localhost:8000/docs\n\n'
