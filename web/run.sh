#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  zicengine web — launch backend + frontend together (Linux / macOS)
#  Usage: bash web/run.sh
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"
FRONTEND="$SCRIPT_DIR/frontend"

# ── Colours ──────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "${CYAN}"
cat << 'EOF'
 ███████╗██╗ ██████╗███████╗███╗   ██╗ ██████╗ ██╗███╗   ██╗███████╗
 ╚══███╔╝██║██╔════╝██╔════╝████╗  ██║██╔════╝ ██║████╗  ██║██╔════╝
   ███╔╝ ██║██║     █████╗  ██╔██╗ ██║██║  ███╗██║██╔██╗ ██║█████╗
  ███╔╝  ██║██║     ██╔══╝  ██║╚██╗██║██║   ██║██║██║╚██╗██║██╔══╝
 ███████╗██║╚██████╗███████╗██║ ╚████║╚██████╔╝██║██║ ╚████║███████╗
 ╚══════╝╚═╝ ╚═════╝╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝╚═╝  ╚═══╝╚══════╝
EOF
echo -e "${NC}"
echo -e "  Image to DXF — web UI"
echo -e "  Backend : ${CYAN}http://localhost:8000${NC}"
echo -e "  Frontend: ${CYAN}http://localhost:5173${NC}"
echo -e "  Docs    : ${CYAN}http://localhost:8000/docs${NC}"
echo ""

# ── Checks ───────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[ERROR] python3 not found. Install Python 3.11+.${NC}"; exit 1
fi
if ! command -v node &>/dev/null; then
    echo -e "${RED}[ERROR] node not found. Install Node.js 18+.${NC}"; exit 1
fi

# ── Install Python deps ───────────────────────────────────────────────
if [ ! -f "$BACKEND/.deps_ok" ]; then
    echo "[1/4] Installing Python dependencies..."
    pip3 install -r "$BACKEND/requirements.txt" -q
    touch "$BACKEND/.deps_ok"
    echo -e "      ${GREEN}Done.${NC}"
else
    echo "[1/4] Python deps already installed."
fi

# ── Install Node deps ─────────────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
    echo "[2/4] Installing Node dependencies (may take a minute)..."
    (cd "$FRONTEND" && npm install --silent)
    echo -e "      ${GREEN}Done.${NC}"
else
    echo "[2/4] Node modules already present."
fi

# ── Launch backend ────────────────────────────────────────────────────
echo "[3/4] Starting FastAPI backend on port 8000..."
(cd "$BACKEND" && uvicorn main:app --reload --port 8000) &
BACKEND_PID=$!

sleep 1

# ── Launch frontend ───────────────────────────────────────────────────
echo "[4/4] Starting Vite frontend on port 5173..."
(cd "$FRONTEND" && npm run dev) &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}✓ Both services are running.${NC}"
echo -e "  Open ${CYAN}http://localhost:5173${NC} in your browser."
echo ""
echo "  Press Ctrl+C to stop both services."

# ── Wait / cleanup ────────────────────────────────────────────────────
cleanup() {
    echo ""
    echo "Stopping services..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM
wait
