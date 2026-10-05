#!/usr/bin/env bash
#
# run-local.sh — bring the whole platform up on this machine, with data.
#
# One command instead of the seven in the README:
#
#   ./run-local.sh            start, seed and verify (idempotent)
#   ./run-local.sh --reset    drop the volumes first, so the run is from scratch
#   ./run-local.sh --no-seed  start the stack but skip the 120-day demo dataset
#   ./run-local.sh --stop     stop the stack, keeping the data
#   ./run-local.sh --clean    stop the stack and delete the volumes
#   ./run-local.sh --status   show what is running and whether it is healthy
#
# Safe to re-run: an existing stack is reused, and the seed is skipped when the
# warehouse already holds data.
#
set -euo pipefail

# ------------------------------------------------------------------ locations
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"
COMPOSE="${COMPOSE:-docker compose}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin@12345}"
DEMO_DAYS="${DEMO_DAYS:-120}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"

# ------------------------------------------------------------------- output
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; NC=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi

step()  { printf '\n%s==>%s %s%s%s\n' "$BLUE" "$NC" "$BOLD" "$*" "$NC"; }
info()  { printf '    %s%s%s\n' "$DIM" "$*" "$NC"; }
ok()    { printf '    %s✓%s %s\n' "$GREEN" "$NC" "$*"; }
warn()  { printf '    %s!%s %s\n' "$YELLOW" "$NC" "$*"; }
die()   { printf '\n%serror:%s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }

usage() {
  sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

#: Prints a one-line summary of GET /health. Kept in a variable so both `--status`
#: and the startup verification use exactly the same formatting.
HEALTH_SUMMARY='import json,sys
h=json.load(sys.stdin); d=h["database"]
print("    status %s - version %s - %s %s - %s tables - %s sources" % (h["status"], h["version"], d["dialect"], d.get("server_version") or "?", d["tables"], len(h.get("sources") or [])))'

exec_status() {
  step "Services"
  $COMPOSE ps

  step "API"
  if curl -fsS http://localhost:8000/api/v1/health 2>/dev/null | "$PY" -c "$HEALTH_SUMMARY"; then
    ok "API healthy"
  else
    warn "API not responding on http://localhost:8000"
  fi

  step "Frontend"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5173/ 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then
    ok "Frontend serving on http://localhost:5173"
  else
    warn "Frontend returned HTTP $code"
  fi
}

# ------------------------------------------------------------------ flags
RESET=0
SEED=1
ACTION=up

for arg in "$@"; do
  case "$arg" in
    --reset)    RESET=1 ;;
    --no-seed)  SEED=0 ;;
    --stop)     ACTION=stop ;;
    --clean)    ACTION=clean ;;
    --status)   ACTION=status ;;
    -h|--help)  usage ;;
    *)          die "unknown option '$arg' (try --help)" ;;
  esac
done

# ------------------------------------------------------------- prerequisites
need() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required but not installed. $2"
}

need docker "Install Docker Engine with the Compose plugin."
need node   "Install Node.js 20 or newer."
docker compose version >/dev/null 2>&1 || die "'docker compose' is unavailable. Update Docker, or set COMPOSE."
docker info >/dev/null 2>&1 || die "The Docker daemon is not reachable. Is Docker running?"

case "$ACTION" in
  status) exec_status; exit $? ;;
  stop)
    step "Stopping the stack (data is kept)"
    $COMPOSE down
    ok "Stopped. Volumes and database contents are intact."
    exit 0
    ;;
  clean)
    step "Stopping the stack and deleting its volumes"
    $COMPOSE down -v --remove-orphans
    ok "Removed. The next start will be a clean install."
    exit 0
    ;;
esac

# ----------------------------------------------------------------- one-time setup
if [ ! -x "$PY" ]; then
  step "Creating the Python virtual environment"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  ok "Created $VENV"
fi

if ! "$PY" -c 'import app' >/dev/null 2>&1; then
  step "Installing Python dependencies"
  "$VENV/bin/pip" install --quiet -e '.[dev]'
  ok "Installed"
fi

if [ ! -d frontend/node_modules ]; then
  step "Installing frontend dependencies"
  (cd frontend && npm install --no-fund --no-audit)
  ok "Installed"
fi

if [ ! -f .env ]; then
  step "Writing .env from .env.example"
  cp .env.example .env
  # A locally-generated secret: reusing the example value would ship a known key.
  SECRET="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  if grep -q '^SECRET_KEY=' .env; then
    "$PY" - "$SECRET" <<'PY'
import pathlib, re, sys
path = pathlib.Path(".env")
text = path.read_text(encoding="utf-8")
path.write_text(re.sub(r"(?m)^SECRET_KEY=.*$", f"SECRET_KEY={sys.argv[1]}", text), encoding="utf-8")
PY
  else
    printf '\nSECRET_KEY=%s\n' "$SECRET" >> .env
  fi
  ok "Created .env with a generated SECRET_KEY"
fi

# --------------------------------------------------------------------- database
if [ "$RESET" -eq 1 ]; then
  step "Resetting: removing the existing volumes"
  $COMPOSE down -v --remove-orphans
  ok "Volumes removed"
fi

step "Starting the six services"
$COMPOSE up -d --build
ok "Containers created"

step "Waiting for the databases"
printf '    %s' "postgres, mysql"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while :; do
  pg_ok=$($COMPOSE ps --format json postgres 2>/dev/null | grep -c '"Health":"healthy"' || true)
  my_ok=$($COMPOSE ps --format json mysql 2>/dev/null | grep -c '"Health":"healthy"' || true)
  [ "${pg_ok:-0}" -ge 1 ] && [ "${my_ok:-0}" -ge 1 ] && break
  if [ "$(date +%s)" -gt "$deadline" ]; then
    printf '\n'
    $COMPOSE ps
    die "The databases did not become healthy within ${HEALTH_TIMEOUT}s."
  fi
  printf '.'
  sleep 2
done
printf ' %s\n' "$NC"
ok "Both databases healthy"

step "Waiting for the API"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while :; do
  if curl -fsS http://localhost:8000/api/v1/health >/dev/null 2>&1; then break; fi
  if [ "$(date +%s)" -gt "$deadline" ]; then
    $COMPOSE logs --tail 40 api
    die "The API did not become healthy within ${HEALTH_TIMEOUT}s."
  fi
  printf '.'
  sleep 2
done
printf ' %s\n' "$NC"
ok "API responding"

# ---------------------------------------------------------------------- schema
step "Applying migrations and creating the schema"
if "$PY" -m alembic current >/dev/null 2>&1 && \
   "$PY" -m alembic current 2>/dev/null | grep -q "head"; then
  info "Already at the latest revision; nothing to apply"
else
  "$PY" -m alembic upgrade head
  ok "Schema at head"
fi

"$PY" -m app.cli.main bootstrap
ok "Views, users and reference data in place"

# ------------------------------------------------------------------ demo data
PRODUCT_COUNT="$("$PY" - <<'PY' 2>/dev/null || echo 0
from sqlalchemy import text
from app.core.db import read_session
try:
    with read_session() as session:
        print(int(session.execute(text("SELECT count(*) FROM dim_product")).scalar() or 0))
except Exception:
    print(0)
PY
)"

if [ "$SEED" -eq 0 ]; then
  warn "Skipping the demo dataset (--no-seed)"
elif [ "${PRODUCT_COUNT:-0}" -gt 0 ]; then
  info "Warehouse already holds ${PRODUCT_COUNT} products; skipping the seed"
else
  step "Seeding the ${DEMO_DAYS}-day demo dataset"
  "$PY" -m app.cli.main seed-demo --database postgres --days "$DEMO_DAYS"
  ok "Seeded"
fi

step "Running one pipeline run so the dashboard has live figures"
"$PY" -m app.cli.main run-pipeline
ok "Pipeline run complete"

# ------------------------------------------------------------------ sign in
step "Exchanging the demo credentials for a token"
LOGIN="$(curl -fsS -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" 2>/dev/null || true)"

if [ -n "$LOGIN" ] && printf '%s' "$LOGIN" | grep -q access_token; then
  TOKEN="$(printf '%s' "$LOGIN" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
  curl -fsS http://localhost:8000/api/v1/meta -H "Authorization: Bearer $TOKEN" 2>/dev/null | "$PY" -c '
import json, sys
m = json.load(sys.stdin)
print("    version %s · %s tables · %s views · %s operations · %s sources"
      % (m["version"], m["tables"], m["views"], m["operations"], m["sources"]))
'
  ok "API verified"
else
  warn "Could not sign in as $ADMIN_EMAIL; the API is up but unverified"
  $COMPOSE logs --tail 20 api
fi

# ------------------------------------------------------------------- summary
cat <<EOF

${GREEN}${BOLD}The stack is running.${NC}

  ${BOLD}Dashboard${NC}   http://localhost:5173
  ${BOLD}API${NC}         http://localhost:8000/docs
  ${BOLD}Airflow${NC}     http://localhost:8080

  ${BOLD}Sign in${NC}
    admin    $ADMIN_EMAIL / $ADMIN_PASSWORD
    analyst  analyst@example.com / Analyst@12345
    viewer   viewer@example.com / Viewer@12345

  ${DIM}Logs      ./run-local.sh --status, or: docker compose logs -f api
  ${DIM}Stop      ./run-local.sh --stop
  ${DIM}Reset     ./run-local.sh --reset${NC}

EOF
