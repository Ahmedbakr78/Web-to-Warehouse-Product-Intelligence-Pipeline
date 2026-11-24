#!/usr/bin/env bash
# ==============================================================================
#  Web-to-Warehouse Product Intelligence Pipeline
#  share-tunnel.sh — Share your local instance with your team via Cloudflare Tunnel
# ==============================================================================
set -euo pipefail

# ANSI color codes
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Ensure standard bin paths are in PATH
export PATH="/home/ahmed/.local/bin:$HOME/.local/bin:/usr/local/bin:$PATH"

# Default port: 5173 (Frontend Nginx, which already proxies /api to Backend 8000)
TARGET_PORT="${1:-5173}"
SERVICE_NAME="Full Pipeline Dashboard (React + API + Docs)"

if [[ "$TARGET_PORT" == "--help" || "$TARGET_PORT" == "-h" ]]; then
  echo -e "${BOLD}Usage:${NC} ./share-tunnel.sh [PORT]"
  echo ""
  echo "Options / Examples:"
  echo "  ./share-tunnel.sh         # Share Full Dashboard + API + Warehouse (Port 5173)"
  echo "  ./share-tunnel.sh 8080    # Share Apache Airflow Webserver (Port 8080)"
  echo "  ./share-tunnel.sh 8000    # Share FastAPI Backend directly (Port 8000)"
  exit 0
fi

if [[ "$TARGET_PORT" == "8080" ]]; then
  SERVICE_NAME="Apache Airflow Webserver"
elif [[ "$TARGET_PORT" == "8000" ]]; then
  SERVICE_NAME="FastAPI Backend & Analytics"
fi

echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}${BOLD}  🌐 Web-to-Warehouse: Cloudflare Team Share Tunnel          ${NC}"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check for cloudflared binary
if ! command -v cloudflared &>/dev/null; then
  echo -e "${YELLOW}cloudflared not found in PATH, checking ~/.local/bin/cloudflared...${NC}"
  if [[ -x "$HOME/.local/bin/cloudflared" ]]; then
    CLOUDFLARED_BIN="$HOME/.local/bin/cloudflared"
  else
    echo -e "${YELLOW}Downloading cloudflared binary...${NC}"
    mkdir -p "$HOME/.local/bin"
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o "$HOME/.local/bin/cloudflared"
    chmod +x "$HOME/.local/bin/cloudflared"
    CLOUDFLARED_BIN="$HOME/.local/bin/cloudflared"
  fi
else
  CLOUDFLARED_BIN="$(command -v cloudflared)"
fi

echo -e "✓ Found ${BOLD}$($CLOUDFLARED_BIN --version | head -n 1)${NC}"

# Check if target local port is active
if ! curl -s "http://127.0.0.1:${TARGET_PORT}" &>/dev/null && ! nc -z 127.0.0.1 "${TARGET_PORT}" &>/dev/null; then
  echo -e "${YELLOW}⚠️  Warning: Nothing seems to be answering on http://localhost:${TARGET_PORT}.${NC}"
  echo -e "   Make sure your containers are running: ${BOLD}docker compose up -d${NC}"
  echo -e "   Starting tunnel anyway...${NC}\n"
else
  echo -e "✓ Target service ${GREEN}http://localhost:${TARGET_PORT}${NC} (${SERVICE_NAME}) is reachable."
fi

# Log file for tunnel output
TUNNEL_LOG=$(mktemp /tmp/cloudflared-tunnel.XXXXXX.log)
trap 'rm -f "$TUNNEL_LOG"' EXIT

echo -e "${YELLOW}⏳ Requesting secure public HTTPS URL from Cloudflare...${NC}"

# Launch cloudflared in the background while monitoring output
"$CLOUDFLARED_BIN" tunnel --url "http://localhost:${TARGET_PORT}" > "$TUNNEL_LOG" 2>&1 &
CF_PID=$!

# Cleanup background process on exit/SIGINT
cleanup() {
  echo -e "\n${YELLOW}Shutting down tunnel...${NC}"
  kill "$CF_PID" 2>/dev/null || true
  wait "$CF_PID" 2>/dev/null || true
  rm -f "$TUNNEL_LOG"
  echo -e "${GREEN}Tunnel closed.${NC}"
}
trap cleanup SIGINT SIGTERM EXIT

# Poll for the generated trycloudflare URL (timeout after 30s)
PUBLIC_URL=""
for i in {1..30}; do
  if grep -E -q 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG"; then
    PUBLIC_URL=$(grep -o -E 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -n 1)
    break
  fi
  sleep 1
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo -e "${RED}❌ Failed to retrieve Cloudflare tunnel URL within 30 seconds.${NC}"
  echo -e "${YELLOW}Log output:${NC}"
  cat "$TUNNEL_LOG"
  exit 1
fi

# Save to tunnel-url.txt for easy sharing
echo "$PUBLIC_URL" > tunnel-url.txt

# Try to copy to clipboard if clipboard utilities are available
if command -v wl-copy &>/dev/null; then
  echo "$PUBLIC_URL" | wl-copy 2>/dev/null || true
elif command -v xclip &>/dev/null; then
  echo "$PUBLIC_URL" | xclip -selection clipboard 2>/dev/null || true
fi

# Banner output for team sharing
echo ""
echo -e "${GREEN}${BOLD}=================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 TUNNEL ACTIVE! SHARE THIS LINK WITH YOUR TEAM:              ${NC}"
echo -e "${GREEN}${BOLD}=================================================================${NC}"
echo ""
echo -e "  🌐 ${BOLD}Public HTTPS URL:${NC}  ${CYAN}${BOLD}${PUBLIC_URL}${NC}"
echo -e "  🎯 ${BOLD}Forwarding to:${NC}     http://localhost:${TARGET_PORT} (${SERVICE_NAME})"
echo -e "  💾 ${BOLD}Saved to:${NC}          tunnel-url.txt"
echo ""
echo -e "${MAGENTA}${BOLD}-----------------------------------------------------------------${NC}"
echo -e "${BOLD} 🔑 Team Credentials to Sign In:${NC}"
echo -e "    👑 ${BOLD}Admin:${NC}    admin@example.com   /  Admin@12345"
echo -e "    📊 ${BOLD}Analyst:${NC}  analyst@example.com /  Analyst@12345"
echo -e "    👁️  ${BOLD}Viewer:${NC}   viewer@example.com  /  Viewer@12345"
if [[ "$TARGET_PORT" == "8080" ]]; then
echo -e "    ⚙️  ${BOLD}Airflow:${NC} admin               /  admin"
fi
echo -e "${MAGENTA}${BOLD}-----------------------------------------------------------------${NC}"
echo -e "  📚 ${BOLD}Interactive API Docs (Swagger):${NC} ${PUBLIC_URL}/docs"
echo -e "  📈 ${BOLD}Sources & Compliance Audit:${NC}    ${PUBLIC_URL}/sources"
echo -e "${GREEN}${BOLD}=================================================================${NC}"
echo -e "${YELLOW}Press [Ctrl+C] anytime to stop sharing the tunnel.${NC}"
echo ""

# Wait for cloudflared process to terminate
wait "$CF_PID"
