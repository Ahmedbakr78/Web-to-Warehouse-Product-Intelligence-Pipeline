#!/usr/bin/env bash
#
# run.sh — THE one file to run the full app. Everything, one command.
#
#   ./run.sh                 verify (real data) + launch the Docker stack + load real data
#   ./run.sh --verify-only   only verify: lint, tests, live-source smoke, real pipeline, frontend
#   ./run.sh --offline       use the synthetic local_demo source (no network needed)
#   ./run.sh --quick         fast verify: subset of tests, no frontend build
#   ./run.sh --no-frontend   skip frontend steps during verify
#   ./run.sh --no-verify     skip verification, just launch the stack
#   ./run.sh --stop          stop the stack (data kept)
#   ./run.sh --clean         stop the stack and delete volumes
#   ./run.sh --status        health of every service
#   ./run.sh --help          this help
#
# What "full" means here:
#   1. VERIFY (real, no fakes): ruff, the backend suite, a registry guard that
#      proves the pipeline auto-select excludes every non-`real` and every
#      terms-blocked source, a LIVE fetch from eight real permitted upstreams
#      (Open Library, Gutendex, iTunes apps + ebooks, Steam, CheapShark, Open
#      Food Facts, TVMaze), a real 9-stage pipeline run into a fresh SQLite
#      warehouse, the no-fake audit over every row plus a self-test proving the
#      audit rejects synthetic data, the live API serving that warehouse, and
#      the frontend typecheck / lint / vitest / build.
#   2. LAUNCH: the 6-service Docker stack (postgres + mysql + api + airflow +
#      scheduler + frontend), schema bootstrap, one real pipeline run so the
#      dashboard opens with live figures, and clickable local links.
#
# Under the hood this dispatches to:
#   run-full-app.sh  (verification, real data — no Docker needed)
#   run-local.sh     (Docker stack launcher with data)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$SCRIPT_DIR"

VERIFY=1
VERIFY_ARGS=()
LAUNCH=1
LOCAL_ARGS=()
ACTION="run"

for arg in "$@"; do
  case "$arg" in
    --verify-only) LAUNCH=0; ACTION="verify" ;;
    --no-verify) VERIFY=0 ;;
    --offline|--quick|--no-frontend) VERIFY_ARGS+=("$arg") ;;
    --stop|--clean|--status) VERIFY=0; LAUNCH=1; LOCAL_ARGS+=("$arg"); ACTION="${arg#--}" ;;
    --rebuild|--reset|--no-seed|--open) LOCAL_ARGS+=("$arg") ;;
    -h|--help)
      sed -n '2,35p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    --*) echo "error: unknown option '$arg' (try --help)" >&2; exit 1 ;;
    *) echo "error: unknown option '$arg' (try --help)" >&2; exit 1 ;;
  esac
done

if [ "$VERIFY" -eq 1 ]; then
  echo "==> [1/2] VERIFYING the full app with real data (no fakes)"
  ./run-full-app.sh "${VERIFY_ARGS[@]}"
fi

if [ "$LAUNCH" -eq 1 ]; then
  case "$ACTION" in
    run)    echo "==> [2/2] LAUNCHING the full stack" ;;
    status) echo "==> STATUS: every service" ;;
    stop)   echo "==> STOPPING the stack (data kept)" ;;
    clean)  echo "==> CLEANING the stack and its volumes" ;;
    *)      echo "==> $ACTION" ;;
  esac
  ./run-local.sh "${LOCAL_ARGS[@]}"
fi
