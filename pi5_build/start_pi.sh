#!/bin/bash
# Planroom Genius - Startup Script for Raspberry Pi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}     Planroom Genius - Startup           ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Define paths relative to this script (which is in pi5_build)
BACKEND_DIR="../backend"
FRONTEND_DIR="../frontend"
LOG_DIR="logs"

# Prerequisite Checks
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo -e "${RED}[ERROR] Virtual environment not found ($BACKEND_DIR/venv).${NC}"
    echo "Please run: ./setup_pi.sh"
    exit 1
fi

# Kill any leftover instances from previous runs
echo -e "${YELLOW}[INFO] Stopping any existing instances...${NC}"
pkill -f "python3 -m backend.api" 2>/dev/null
pkill -f "python3 api.py" 2>/dev/null
pkill -f "node.*vite" 2>/dev/null
sleep 1

# Logging Setup
mkdir -p "$LOG_DIR"
# Clear logs
echo "" > "$LOG_DIR/backend.log"
echo "" > "$LOG_DIR/frontend.log"

echo -e "${YELLOW}[INFO] Logs streaming to: $LOG_DIR/ ...${NC}"

# Start Services
# ----------------------
echo -e "${YELLOW}[INFO] Starting Backend...${NC}"
cd "$SCRIPT_DIR/.."
. backend/venv/bin/activate
# Run as module from project root to prevent double-import (double logging)
python3 -m backend.api > "pi5_build/$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}[OK] Backend started (PID: $BACKEND_PID)${NC}"

# Return to script dir to be safe (optional, but good practice)
cd "$SCRIPT_DIR"

# ----------------------
echo -e "${YELLOW}[INFO] Starting Frontend...${NC}"
cd "$FRONTEND_DIR"
# Point logs back to pi5_build/logs
npm run dev -- --host 0.0.0.0 > "../pi5_build/$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}[OK] Frontend started (PID: $FRONTEND_PID)${NC}"

# Return to script dir
cd "$SCRIPT_DIR"

# Access Info
IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}Dashboard: http://$IP:5173${NC}"
echo -e "${GREEN}API:       http://$IP:8000${NC}"
echo ""
echo -e "${YELLOW}Streaming logs (Ctrl+C to stop)...${NC}"
echo -e "${BLUE}-----------------------------------------${NC}"

# Cleanup Function
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping services...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# Stream logs
tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log" &
wait
