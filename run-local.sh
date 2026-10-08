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
#   NO_COLOR=1              plain text, no ANSI colours or glyphs
#   FORCE_HYPERLINKS=1      always emit clickable OSC 8 links
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
ANALYST_EMAIL="analyst@example.com"
VIEWER_EMAIL="viewer@example.com"
DEMO_DAYS="${DEMO_DAYS:-120}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
APP_PORT="${APP_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
AIRFLOW_PORT="${AIRFLOW_PORT:-8080}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
POSTGRES_USER="${POSTGRES_USER:-pip}"
POSTGRES_DB="${POSTGRES_DB:-pipeline}"
MYSQL_USER="${MYSQL_USER:-pip}"
MYSQL_DATABASE="${MYSQL_DATABASE:-pipeline}"
AIRFLOW_ADMIN_USER="${AIRFLOW_ADMIN_USER:-admin}"
AIRFLOW_ADMIN_PASSWORD="${AIRFLOW_ADMIN_PASSWORD:-admin}"
API_URL="http://localhost:${APP_PORT}"
API_DOCS_URL="${API_URL}/docs"
API_HEALTH_URL="${API_URL}/api/v1/health"
DASH_URL="http://localhost:${FRONTEND_PORT}"
AIRFLOW_URL="http://localhost:${AIRFLOW_PORT}"
SERVICE_COUNT=6
VERSION="$(cat VERSION 2>/dev/null || echo dev)"

# The `python -m app.cli.main` entry point always prints a runpy
# RuntimeWarning (the package __init__ imports `main`); silence it so the
# phase output stays readable.
export PYTHONWARNINGS="${PYTHONWARNINGS:-ignore::RuntimeWarning}"

# ------------------------------------------------------------------- terminal
TTY=0
[ -t 1 ] && TTY=1

UTF8=0
case "$(locale charmap 2>/dev/null || echo ASCII)" in
  *UTF-8* | *UTF8* | *utf8*) UTF8=1 ;;
esac

if [ "$TTY" -eq 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; CYAN=$'\033[36m'; NC=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; NC=''
  TTY=0
fi

if [ "$UTF8" -eq 1 ] && [ -z "${NO_COLOR:-}" ]; then
  GLYPH_OK=$'\342\234\223'        # ✓
  GLYPH_WARN='!'
  GLYPH_ERR=$'\342\234\227'       # ✗
  GLYPH_MID=$'\302\267'           # ·
  GLYPH_ARROW=$'\342\206\222'     # →
  GLYPH_DOT=$'\342\227\217'       # ●
  GLYPH_RING=$'\342\227\213'      # ○
  BOX_TL=$'\342\255\255'          # ╭
  BOX_TR=$'\342\255\256'          # ╮
  BOX_BL=$'\342\225\260'          # ╰
  BOX_BR=$'\342\225\257'          # ╯
  BOX_H=$'\342\224\200'           # ─
  BOX_V=$'\342\224\202'           # │
  BOX_ML=$'\342\224\234'          # ├
  BOX_MR=$'\342\224\244'          # ┤
else
  GLYPH_OK='+'; GLYPH_WARN='!'; GLYPH_ERR='x'
  GLYPH_MID='-'; GLYPH_ARROW='->'; GLYPH_DOT='*'; GLYPH_RING='o'
  BOX_TL='+'; BOX_TR='+'; BOX_BL='+'; BOX_BR='+'
  BOX_H='-'; BOX_V='|'; BOX_ML='+'; BOX_MR='+'
fi

# A line of repeated characters, e.g. `hrule 70 "$BOX_H"`.
hrule() { printf '%*s' "$1" '' | tr ' ' "$2"; }

TERM_COLS="$(tput cols 2>/dev/null || echo 80)"
WIDTH="$TERM_COLS"
[ "$WIDTH" -gt 88 ] && WIDTH=88
[ "$WIDTH" -lt 60 ] && WIDTH=60
# Row layout: │ + space + INNER chars + space + │  →  INNER = WIDTH - 4.
BOX_INNER=$(( WIDTH - 4 ))
[ "$UTF8" -eq 1 ] && ELLIPSIS=$'\342\200\246' || ELLIPSIS='+'  # …

#: True when the terminal renders OSC 8 hyperlinks. Plain URLs are still
#: printed either way (most terminals auto-link those), the escape is only
#: added where it is known to render instead of showing as garbage.
hyperlinks_ok() {
  [ -n "${FORCE_HYPERLINKS:-}" ] && return 0
  [ "$TTY" -eq 1 ] || return 1
  case "${TERM_PROGRAM:-}" in
    iTerm.app | WezTerm | vscode | kitty | mintty | Hyper | Tabby | \
      Contour | WindowsTerminal | Alacritty) return 0 ;;
    Apple_Terminal) return 1 ;;
  esac
  case "${TERM:-}" in
    xterm-kitty | foot* | alacritty* | contour* | wezterm*) return 0 ;;
  esac
  # GNOME Terminal / VTE, recent Konsole and tmux pass-through.
  if [ -n "${VTE_VERSION:-}" ] && [ "${VTE_VERSION:-0}" -ge 5000 ] 2>/dev/null; then
    return 0
  fi
  return 1
}
LINKS=0
hyperlinks_ok && LINKS=1

#: link URL [label] — a clickable local link on capable terminals, the plain
#: URL everywhere else (still clickable via terminal URL detection).
link() {
  local url="$1" label="${2:-$1}"
  if [ "$LINKS" -eq 1 ]; then
    printf '\033]8;;%s\033\\%s\033]8;;\033\\' "$url" "$label"
  else
    printf '%s' "$label"
  fi
}

# ------------------------------------------------------------------- output
PHASE_N=0
PHASE_T=$SECONDS
PHASE_TOTAL=8
STEP_START=$SECONDS

step()  { printf '\n%s==>%s %s%s%s\n' "$BLUE" "$NC" "$BOLD" "$*" "$NC"; }
info()  { printf '    %s%s%s\n' "$DIM" "$*" "$NC"; }
ok()    { printf '    %s%s%s %s\n' "$GREEN" "$GLYPH_OK" "$NC" "$*"; }
warn()  { printf '    %s%s%s %s\n' "$YELLOW" "$GLYPH_WARN" "$NC" "$*"; }
die()   { spin_stop; printf '\n%serror:%s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }

fmt_dur() { # seconds -> "45s" / "2m 05s"
  local s="${1:-0}"
  if [ "$s" -ge 60 ]; then
    printf '%dm %02ds' $(( s / 60 )) $(( s % 60 ))
  else
    printf '%ds' "$s"
  fi
}

#: phase "Title" — numbered section header with a trailing rule.
phase() {
  local title="$1" label fill
  PHASE_N=$(( PHASE_N + 1 ))
  PHASE_T=$SECONDS
  if [ "$TTY" -eq 1 ]; then
    label=" ${PHASE_N}/${PHASE_TOTAL} ${GLYPH_MID} ${title} "
    fill=$(( WIDTH - 3 - ${#label} ))
    [ "$fill" -lt 2 ] && fill=2
    printf '\n%s%s%s%s%s%s%s%s\n' \
      "$DIM" "$(hrule 3 "$BOX_H")" "$NC$CYAN$BOLD" "$label" "$NC$DIM" \
      "$(hrule "$fill" "$BOX_H")" "$NC"
  else
    printf '\n==> [%s/%s] %s\n' "$PHASE_N" "$PHASE_TOTAL" "$title"
  fi
}

#: phase_ok "message" — completion line for the current phase, with timing.
phase_ok() {
  local dur=$(( SECONDS - PHASE_T ))
  ok "$* ${DIM}(${GLYPH_MID} $(fmt_dur "$dur"))${NC}"
}

#: phase_skip "message" — skipped phase, no timing fuss.
phase_skip() {
  info "$* (skipped)"
}

usage() {
  cat <<EOF
${BOLD}run-local.sh${NC} — bring the whole platform up on this machine, with data.

One command instead of the seven in the README:

  ${CYAN}./run-local.sh${NC}            start, seed and verify (idempotent, fast re-runs)
  ${CYAN}./run-local.sh --rebuild${NC}  rebuild the api/frontend images, then start
  ${CYAN}./run-local.sh --reset${NC}    drop the volumes first, so the run is from scratch
  ${CYAN}./run-local.sh --no-seed${NC}  start the stack but skip the 120-day demo dataset
  ${CYAN}./run-local.sh --open${NC}     start and open the dashboard in the browser
  ${CYAN}./run-local.sh --stop${NC}     stop the stack, keeping the data
  ${CYAN}./run-local.sh --clean${NC}    stop the stack and delete the volumes
  ${CYAN}./run-local.sh --status${NC}   show what is running and whether it is healthy
  ${CYAN}./run-local.sh --logs [service]${NC}
                            follow the logs (all services, or one name)

Safe to re-run: an existing stack is reused without rebuilding, and the seed
is skipped when the warehouse already holds data.

Environment overrides:
  VENV=.venv  DEMO_DAYS=120  HEALTH_TIMEOUT=180
  APP_PORT=8000  FRONTEND_PORT=5173  AIRFLOW_PORT=8080
  ADMIN_EMAIL / ADMIN_PASSWORD (demo sign-in verified at the end)
  COMPOSE="docker compose"
  NO_COLOR=1 / FORCE_HYPERLINKS=1
EOF
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

#: Raw container state: healthy|running|starting|exited|…|missing.
service_state() {
  local name="$1" id
  id="$($COMPOSE ps -q "$name" 2>/dev/null | head -1)"
  [ -n "$id" ] || { printf 'missing'; return 0; }
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || printf 'unknown'
}

#: True when a compose service reports a healthy container.
service_healthy() {
  case "$(service_state "$1")" in
    healthy | running) return 0 ;;
  esac
  return 1
}

#: True when the compose service has a running container (healthy or still starting).
service_running() {
  local id
  id="$($COMPOSE ps -q "$1" 2>/dev/null | head -1)"
  [ -n "$id" ] && [ "$(docker inspect --format '{{.State.Running}}' "$id" 2>/dev/null)" = "true" ]
}

#: Coloured state dot for tables: green healthy, yellow starting, red stopped.
state_dot() {
  case "$1" in
    healthy)       printf '%s%s%s healthy' "$GREEN" "$GLYPH_DOT" "$NC" ;;
    running)       printf '%s%s%s running' "$GREEN" "$GLYPH_DOT" "$NC" ;;
    starting)      printf '%s%s%s starting' "$YELLOW" "$GLYPH_DOT" "$NC" ;;
    exited | dead) printf '%s%s%s %s' "$RED" "$GLYPH_DOT" "$NC" "$1" ;;
    missing)       printf '%s%s%s missing' "$DIM" "$GLYPH_RING" "$NC" ;;
    *)             printf '%s%s%s %s' "$DIM" "$GLYPH_DOT" "$NC" "$1" ;;
  esac
}

# ------------------------------------------------------------------ spinner
SPIN_PID=""
SPIN_FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
[ "$UTF8" -eq 0 ] && SPIN_FRAMES=('|' '/' '-' '\')

spin_start() {
  local msg="$1"
  [ -n "$SPIN_PID" ] && return 0
  if [ "$TTY" -eq 0 ]; then
    printf '    %s %s ' "..." "$msg"
    return 0
  fi
  (
    trap 'exit 0' TERM INT
    i=0
    n=${#SPIN_FRAMES[@]}
    t0=$SECONDS
    while :; do
      printf '\r\033[K    %s%s%s %s %s(%ss)%s' \
        "$CYAN" "${SPIN_FRAMES[$i]}" "$NC" "$msg" "$DIM" "$(( SECONDS - t0 ))" "$NC"
      sleep 0.12
      i=$(( (i + 1) % n ))
    done
  ) &
  SPIN_PID=$!
}

spin_stop() {
  [ -n "$SPIN_PID" ] || return 0
  kill "$SPIN_PID" 2>/dev/null || true
  wait "$SPIN_PID" 2>/dev/null || true
  SPIN_PID=""
  [ "$TTY" -eq 1 ] && printf '\r\033[K'
  return 0
}

#: wait_until LABEL TIMEOUT CMD... — spin while CMD fails; sets WAIT_SECS.
WAIT_SECS=0
wait_until() {
  local label="$1" timeout="$2"
  shift 2
  local start=$SECONDS elapsed=0
  spin_start "$label"
  while :; do
    if "$@" >/dev/null 2>&1; then
      WAIT_SECS=$(( SECONDS - start ))
      spin_stop
      [ "$TTY" -eq 0 ] && printf 'done\n'
      return 0
    fi
    elapsed=$(( SECONDS - start ))
    if [ "$elapsed" -gt "$timeout" ]; then
      WAIT_SECS=$elapsed
      spin_stop
      [ "$TTY" -eq 0 ] && printf 'timeout\n'
      return 1
    fi
    [ "$TTY" -eq 0 ] && printf '.'
    sleep 2
  done
}

# --------------------------------------------------------------- link box
box_top()    { printf '%s%s%s%s%s\n' "$CYAN$BOLD" "$BOX_TL" "$(hrule $(( WIDTH - 2 )) "$BOX_H")" "$BOX_TR" "$NC"; }
box_mid()    { printf '%s%s%s%s%s\n' "$DIM" "$BOX_ML" "$(hrule $(( WIDTH - 2 )) "$BOX_H")" "$BOX_MR" "$NC"; }
box_bottom() { printf '%s%s%s%s%s\n' "$CYAN$BOLD" "$BOX_BL" "$(hrule $(( WIDTH - 2 )) "$BOX_H")" "$BOX_BR" "$NC"; }

#: box_row VISIBLE [RENDERED] — padded box row. VISIBLE is plain text and
#: drives the padding math; RENDERED may carry colours and OSC 8 hyperlinks.
box_row() {
  local vis="$1" out="${2:-$1}" pad
  if [ "${#vis}" -gt "$BOX_INNER" ]; then
    vis="${vis:0:$(( BOX_INNER - 1 ))}${ELLIPSIS}"
    out="$vis"
  fi
  pad=$(( BOX_INNER - ${#vis} ))
  printf '%s%s%s %s%*s %s%s%s\n' "$DIM" "$BOX_V" "$NC" "$out" "$pad" '' "$DIM" "$BOX_V" "$NC"
}

#: box_kv LABEL VISIBLE [RENDERED] — two-column row, labels left-aligned.
box_kv() {
  local label="$1" vis="$2" out="${3:-$2}"
  box_row "$(printf '  %-11s %s' "$label" "$vis")" \
          "$(printf '  %s%-11s%s %s' "$BOLD" "$label" "$NC" "$out")"
}

#: box_h TEXT — bold section header inside the box.
box_h() { box_row "  $1" "  ${BOLD}$1${NC}"; }

#: box_dim TEXT — dimmed note inside the box.
box_dim() { box_row "  $1" "  ${DIM}$1${NC}"; }

#: The clickable local-links card, used by both the final summary and --status.
links_card() {
  local title="${1:-The stack is running}"
  box_top
  box_row "  ${title}  v${VERSION}" "  ${BOLD}${title}${NC}  ${DIM}v${VERSION}${NC}"
  box_mid
  box_row "  Local links  (click to open)" "  ${BOLD}Local links${NC}  ${DIM}(click to open)${NC}"
  box_kv "Dashboard" "$DASH_URL" "$(link "$DASH_URL")"
  box_kv "Analytics" "${DASH_URL}/analytics" "$(link "${DASH_URL}/analytics")"
  box_kv "Products" "${DASH_URL}/products" "$(link "${DASH_URL}/products")"
  box_kv "API docs" "$API_DOCS_URL" "$(link "$API_DOCS_URL")"
  box_kv "API health" "$API_HEALTH_URL" "$(link "$API_HEALTH_URL")"
  box_kv "Airflow" "$AIRFLOW_URL" "$(link "$AIRFLOW_URL")"
  box_kv "PostgreSQL" "localhost:${POSTGRES_PORT} ${GLYPH_MID} ${POSTGRES_USER}/${POSTGRES_DB}"
  box_kv "MySQL" "localhost:${MYSQL_PORT} ${GLYPH_MID} ${MYSQL_USER}/${MYSQL_DATABASE}"
  box_mid
  box_h "Sign in"
  box_row "    admin     ${ADMIN_EMAIL} / ${ADMIN_PASSWORD}"
  box_row "    analyst   ${ANALYST_EMAIL} / Analyst@12345"
  box_row "    viewer    ${VIEWER_EMAIL} / Viewer@12345"
  box_row "    airflow   ${AIRFLOW_ADMIN_USER} / ${AIRFLOW_ADMIN_PASSWORD}   (Airflow UI only)" \
          "    airflow   ${AIRFLOW_ADMIN_USER} / ${AIRFLOW_ADMIN_PASSWORD}   ${DIM}(Airflow UI only)${NC}"
  box_dim "(or create your own account on the sign-in page)"
  box_mid
  box_h "Next"
  box_row "    ./run-local.sh --status         health of every service"
  box_row "    ./run-local.sh --logs [name]    follow one service (api, frontend, …)"
  box_row "    ./run-local.sh --stop           stop the stack, keep the data"
  box_row "    ./run-local.sh --reset          start again from scratch"
  box_bottom
}

#: banner — the opening card for a full run.
banner() {
  local mode="$1"
  box_top
  box_row "  Product Intelligence Pipeline  ${GLYPH_MID} local launcher" \
          "  ${BOLD}Product Intelligence Pipeline${NC}  ${DIM}${GLYPH_MID} local launcher${NC}"
  box_row "  v${VERSION} ${GLYPH_MID} ${SERVICE_COUNT} services ${GLYPH_MID} ${mode}" \
          "  ${DIM}v${VERSION} ${GLYPH_MID} ${SERVICE_COUNT} services ${GLYPH_MID} ${mode}${NC}"
  box_bottom
}

# ------------------------------------------------------------------ actions
exec_status() {
  step "Services"
  printf '\n    %-16s %-24s %s\n' "SERVICE" "STATE" "LINK"
  local svc st code
  for svc in frontend api airflow airflow-scheduler postgres mysql; do
    st="$(service_state "$svc")"
    case "$svc" in
      frontend) code="$(http_code "$DASH_URL/")" ;;
      api) code="$(http_code "$API_HEALTH_URL")" ;;
      airflow) code="$(http_code "$AIRFLOW_URL/health")" ;;
      *) code="-" ;;
    esac
    if [ "$code" = "200" ]; then
      printf '    %-16s %b  HTTP %s\n' "$svc" "$(state_dot "$st")" "$code"
    elif [ "$code" = "-" ]; then
      printf '    %-16s %b\n' "$svc" "$(state_dot "$st")"
    else
      printf '    %-16s %b  HTTP %s\n' "$svc" "$(state_dot "$st")" "$code"
    fi
  done

  step "API"
  if curl -fsS "$API_HEALTH_URL" 2>/dev/null | jsonpy -c "$HEALTH_SUMMARY" 2>/dev/null; then
    ok "API healthy · $(link "$API_DOCS_URL" "docs")"
  else
    warn "API not responding on $API_URL"
  fi

  step "Frontend"
  code="$(http_code "$DASH_URL/")"
  if [ "$code" = "200" ]; then
    ok "Frontend serving · $(link "$DASH_URL")"
  else
    warn "Frontend returned HTTP $code"
  fi

  step "Airflow"
  code="$(http_code "$AIRFLOW_URL/health")"
  if [ "$code" = "200" ]; then
    ok "Airflow serving · $(link "$AIRFLOW_URL")"
  else
    info "Airflow not ready yet (it starts minutes after the API; not fatal)"
    info "Watch it at $(link "$AIRFLOW_URL")"
  fi

  printf '\n'
  links_card "Local links"
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
    printf '\n    Start again any time with %s./run-local.sh%s\n' "$CYAN" "$NC"
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

MODE_DESC="seed ${DEMO_DAYS} days"
[ "$SEED" -eq 0 ] && MODE_DESC="no seed"
[ "$RESET" -eq 1 ] && MODE_DESC="${MODE_DESC}, reset"
[ "$REBUILD" -eq 1 ] && MODE_DESC="${MODE_DESC}, rebuild"
banner "$MODE_DESC"

phase "Preparing the environment"
port_conflict "$APP_PORT" "API" api
port_conflict "$FRONTEND_PORT" "dashboard" frontend

SETUP_DONE=0
if [ ! -x "$PY" ]; then
  info "Creating the Python virtual environment"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  ok "Created $VENV"
  SETUP_DONE=1
fi

if ! "$PY" -c 'import app' >/dev/null 2>&1; then
  info "Installing Python dependencies"
  "$VENV/bin/pip" install --quiet -e '.[dev]'
  ok "Installed"
  SETUP_DONE=1
fi

if [ ! -d frontend/node_modules ]; then
  info "Installing frontend dependencies"
  (cd frontend && npm install --no-fund --no-audit)
  ok "Installed"
  SETUP_DONE=1
fi

if [ ! -f .env ]; then
  info "Writing .env from .env.example"
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
  SETUP_DONE=1
fi

if [ "$SETUP_DONE" -eq 0 ]; then
  phase_ok "Environment ready, nothing to install"
else
  phase_ok "Environment ready"
fi

# ----------------------------------------------------------------- containers
phase "Starting the ${SERVICE_COUNT} services"
if [ "$RESET" -eq 1 ]; then
  info "Reset requested: removing the existing volumes"
  $COMPOSE down -v --remove-orphans
  ok "Volumes removed"
fi

if [ "$REBUILD" -eq 1 ]; then
  info "Rebuilding the api and frontend images"
  $COMPOSE up -d --build
else
  $COMPOSE up -d
fi
phase_ok "Containers created"

# ----------------------------------------------------------------- databases
databases_ready() { service_healthy postgres && service_healthy mysql; }

phase "Waiting for the databases"
if ! wait_until "postgres, mysql" "$HEALTH_TIMEOUT" databases_ready; then
  $COMPOSE ps
  $COMPOSE logs --tail 20 postgres mysql 2>/dev/null || true
  die "The databases did not become healthy within ${HEALTH_TIMEOUT}s."
fi
phase_ok "Both databases healthy"

api_ready() { curl -fsS "$API_HEALTH_URL" >/dev/null 2>&1; }

phase "Waiting for the API"
if ! wait_until "GET ${API_HEALTH_URL#http://}" "$HEALTH_TIMEOUT" api_ready; then
  $COMPOSE logs --tail 40 api
  die "The API did not become healthy within ${HEALTH_TIMEOUT}s."
fi
phase_ok "API responding · $(link "$API_DOCS_URL" "docs")"

# ---------------------------------------------------------------------- schema
phase "Applying migrations and creating the schema"
if "$PY" -m alembic current >/dev/null 2>&1 && \
   "$PY" -m alembic current 2>/dev/null | grep -q "head"; then
  info "Already at the latest revision; nothing to apply"
else
  "$PY" -m alembic upgrade head
  ok "Schema at head"
fi

"$PY" -m app.cli.main bootstrap
phase_ok "Views, users and reference data in place"

# ------------------------------------------------------------------ demo data
phase "Preparing the demo dataset"
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
  phase_skip "Demo dataset (--no-seed)"
elif [ "${PRODUCT_COUNT:-0}" -gt 0 ]; then
  phase_ok "Warehouse already holds ${PRODUCT_COUNT} products; seed skipped"
else
  info "Seeding the ${DEMO_DAYS}-day demo dataset"
  "$PY" -m app.cli.main seed-demo --database postgres --days "$DEMO_DAYS"
  phase_ok "Seeded"
fi

phase "Running one pipeline run so the dashboard has live figures"
"$PY" -m app.cli.main run-pipeline
phase_ok "Pipeline run complete · see $(link "${DASH_URL}/pipeline")"

# ------------------------------------------------------------------ sign in
phase "Exchanging the demo credentials for a token"
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
  phase_ok "API verified"
else
  warn "Could not sign in as $ADMIN_EMAIL; the API is up but unverified"
  $COMPOSE logs --tail 20 api
  phase_ok "API up (verification skipped)"
fi

if [ "$OPEN" -eq 1 ]; then
  open_browser "$DASH_URL"
fi

# ------------------------------------------------------------------- summary
printf '\n'
links_card "The stack is running"
printf '\n  Finished in %s %s open the dashboard %s %s\n\n' \
  "$(fmt_dur $(( SECONDS - STEP_START )))" \
  "$GLYPH_ARROW" "$(link "$DASH_URL")" "$NC"
