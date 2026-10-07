#!/usr/bin/env bash
#
# run-local.sh — bring the whole platform up on this machine, with data.
#
# One command instead of the seven in the README:
#
#   ./run-local.sh            start, seed and verify (idempotent, fast re-runs)
#   ./run-local.sh --rebuild  rebuild the api/frontend images, then start
#   ./run-local.sh --reset    drop the volumes first, so the run is from scratch
#   ./run-local.sh --no-seed  start the stack but skip the 120-day demo dataset
#   ./run-local.sh --open     start and open the dashboard in the browser
#   ./run-local.sh --stop     stop the stack, keeping the data
#   ./run-local.sh --clean    stop the stack and delete the volumes
#   ./run-local.sh --status   show what is running and whether it is healthy
#   ./run-local.sh --logs [service]
#                             follow the logs (all services, or one name)
#
# Safe to re-run: an existing stack is reused without rebuilding, and the seed
# is skipped when the warehouse already holds data.
#
# Environment overrides:
#   VENV=.venv  DEMO_DAYS=120  HEALTH_TIMEOUT=180
#   APP_PORT=8000  FRONTEND_PORT=5173  AIRFLOW_PORT=8080
#   ADMIN_EMAIL / ADMIN_PASSWORD (demo sign-in verified at the end)
#   COMPOSE="docker compose"
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
APP_PORT="${APP_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
AIRFLOW_PORT="${AIRFLOW_PORT:-8080}"
API_URL="http://localhost:${APP_PORT}"
DASH_URL="http://localhost:${FRONTEND_PORT}"
AIRFLOW_URL="http://localhost:${AIRFLOW_PORT}"

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
  sed -n '3,26p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

#: JSON python: prefers the venv, falls back to the system interpreter so
#: `--status` works even before the one-time setup has ever run.
jsonpy() {
  if [ -x "$PY" ]; then "$PY" "$@"; else python3 "$@"; fi
}

#: Prints a one-line summary of GET /health. Kept in a variable so both `--status`
#: and the startup verification use exactly the same formatting.
HEALTH_SUMMARY='import json,sys
h=json.load(sys.stdin); d=h["database"]
print("    status %s - version %s - %s %s - %s tables - %s sources" % (h["status"], h["version"], d["dialect"], d.get("server_version") or "?", d["tables"], len(h.get("sources") or [])))'

http_code() {
  curl -s -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000
}

#: True when a compose service reports a healthy container.
service_healthy() {
  local name="$1" id status
  id="$($COMPOSE ps -q "$name" 2>/dev/null | head -1)"
  [ -n "$id" ] || return 1
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null)"
  [ "$status" = "healthy" ] || [ "$status" = "running" ]
}

exec_status() {
  step "Services"
  $COMPOSE ps

  step "API"
  if curl -fsS "$API_URL/api/v1/health" 2>/dev/null | jsonpy -c "$HEALTH_SUMMARY" 2>/dev/null; then
    ok "API healthy"
  else
    warn "API not responding on $API_URL"
  fi

  step "Frontend"
  local code
  code="$(http_code "$DASH_URL/")"
  if [ "$code" = "200" ]; then
    ok "Frontend serving on $DASH_URL"
  else
    warn "Frontend returned HTTP $code"
  fi

  step "Airflow"
  code="$(http_code "$AIRFLOW_URL/health")"
  if [ "$code" = "200" ]; then
    ok "Airflow serving on $AIRFLOW_URL"
  else
    info "Airflow not ready yet on $AIRFLOW_URL (it starts minutes after the API; not fatal)"
  fi
}

open_browser() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$url" >/dev/null 2>&1 &
  elif command -v wslview >/dev/null 2>&1; then wslview "$url" >/dev/null 2>&1 &
  else warn "Could not find a browser opener; visit $url manually"; fi
}

# ------------------------------------------------------------------ flags
RESET=0
SEED=1
REBUILD=0
OPEN=0
ACTION=up
LOGS_TARGET=""

# A bare service name belongs to --logs regardless of position (`--logs api`,
# `api --logs`, `--logs=api`): detect the mode before parsing anything else.
for arg in "$@"; do
  case "$arg" in
    --logs|--logs=*) ACTION=logs ;;
  esac
done

for arg in "$@"; do
  case "$arg" in
    --reset)    RESET=1 ;;
    --no-seed)  SEED=0 ;;
    --rebuild)  REBUILD=1 ;;
    --open)     OPEN=1 ;;
    --stop)     ACTION=stop ;;
    --clean)    ACTION=clean ;;
    --status)   ACTION=status ;;
    --logs)     ACTION=logs ;;
    --logs=*)   ACTION=logs; LOGS_TARGET="${arg#--logs=}" ;;
    -h|--help)  usage ;;
    --*)        die "unknown option '$arg' (try --help)" ;;
    *)          if [ "$ACTION" = "logs" ]; then LOGS_TARGET="$arg"; else die "unknown option '$arg' (try --help)"; fi ;;
  esac
done

# ------------------------------------------------------------- prerequisites
need() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required but not installed. $2"
}

need python3 "Install Python 3.12 or newer."
need docker "Install Docker Engine with the Compose plugin."
need node   "Install Node.js 20 or newer."
docker compose version >/dev/null 2>&1 || die "'docker compose' is unavailable. Update Docker, or set COMPOSE."
docker info >/dev/null 2>&1 || die "The Docker daemon is not reachable. Is Docker running?"

check_version() { # name cmd min_major min_minor -- warns, never dies
  local name="$1" cmd="$2" want_major="$3" want_minor="$4" got major minor
  got="$($cmd 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)"
  major="${got%%.*}"; minor="${got#*.}"
  if [ -z "$major" ]; then warn "Could not determine $name version; continuing anyway"; return 0; fi
  if [ "$major" -lt "$want_major" ] || { [ "$major" -eq "$want_major" ] && [ "$minor" -lt "$want_minor" ]; }; then
    warn "$name $got found; $want_major.$want_minor or newer is expected — the build may fail"
  fi
}

check_version "Python" "python3 --version" 3 12
check_version "Node.js" "node --version" 20 0

if command -v df >/dev/null 2>&1; then
  avail_kb="$(df -k --output=avail . 2>/dev/null | tail -1 | tr -d ' ')"
  if [ -n "$avail_kb" ] && [ "$avail_kb" -lt 5242880 ]; then
    warn "Less than 5 GB free on this disk; Docker images plus databases may not fit"
  fi
fi

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
  logs)
    if [ -n "$LOGS_TARGET" ]; then
      $COMPOSE logs -f --tail=200 "$LOGS_TARGET"
    else
      $COMPOSE logs -f --tail=100
    fi
    exit 0
    ;;
esac

# ----------------------------------------------------------------- one-time setup
#: True when the compose service has a running container (healthy or still starting).
service_running() {
  local name="$1" id
  id="$($COMPOSE ps -q "$name" 2>/dev/null | head -1)"
  [ -n "$id" ] && [ "$(docker inspect --format '{{.State.Running}}' "$id" 2>/dev/null)" = "true" ]
}

#: A port held by anyone except our own container aborts the start with a fix-it
#: hint. Re-runs against a live stack pass through untouched.
port_conflict() { # port label compose-service
  local port="$1" label="$2" service="$3"
  if service_running "$service"; then return 0; fi
  if curl -fsS --max-time 2 "http://localhost:$port/" >/dev/null 2>&1; then
    die "port $port ($label) is already in use by something outside this stack.
  Stop it, or pick a free port, e.g.: APP_PORT=8001 FRONTEND_PORT=5174 ./run-local.sh"
  fi
}

port_conflict "$APP_PORT" "API" api
port_conflict "$FRONTEND_PORT" "dashboard" frontend

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

if [ "$REBUILD" -eq 1 ]; then
  step "Rebuilding the api and frontend images"
  $COMPOSE up -d --build
else
  step "Starting the six services"
  $COMPOSE up -d
fi
ok "Containers created"

step "Waiting for the databases"
printf '    %s' "postgres, mysql"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while :; do
  if service_healthy postgres && service_healthy mysql; then break; fi
  if [ "$(date +%s)" -gt "$deadline" ]; then
    printf '\n'
    $COMPOSE ps
    $COMPOSE logs --tail 20 postgres mysql 2>/dev/null || true
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
  if curl -fsS "$API_URL/api/v1/health" >/dev/null 2>&1; then break; fi
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
LOGIN="$(curl -fsS -X POST "$API_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" 2>/dev/null || true)"

if [ -n "$LOGIN" ] && printf '%s' "$LOGIN" | grep -q access_token; then
  TOKEN="$(printf '%s' "$LOGIN" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
  curl -fsS "$API_URL/api/v1/meta" -H "Authorization: Bearer $TOKEN" 2>/dev/null | "$PY" -c '
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

if [ "$OPEN" -eq 1 ]; then
  open_browser "$DASH_URL"
fi

# ------------------------------------------------------------------- summary
cat <<EOF

${GREEN}${BOLD}The stack is running.${NC}

  ${BOLD}Dashboard${NC}   $DASH_URL
  ${BOLD}API${NC}         $API_URL/docs
  ${BOLD}Airflow${NC}     $AIRFLOW_URL

  ${BOLD}Sign in${NC}
    admin    $ADMIN_EMAIL / $ADMIN_PASSWORD
    analyst  analyst@example.com / Analyst@12345
    viewer   viewer@example.com / Viewer@12345
    (or create your own account on the sign-in page)

  ${DIM}Status    ./run-local.sh --status
  ${DIM}Logs      ./run-local.sh --logs [service]
  ${DIM}Stop      ./run-local.sh --stop
  ${DIM}Reset     ./run-local.sh --reset${NC}

EOF
