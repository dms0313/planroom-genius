#!/bin/bash
# Planroom Genius - Startup Script for Raspberry Pi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}     Planroom Genius - Startup           ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Prerequisite Checks
if [ ! -d "backend/venv" ]; then
    echo -e "${RED}[ERROR] Virtual environment not found (backend/venv).${NC}"
    echo "Please run: ./setup_pi.sh"
    exit 1
fi

# Logging Setup
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
echo "" > "$LOG_DIR/backend.log"
echo "" > "$LOG_DIR/frontend.log"

# Start Services
echo -e "${YELLOW}[INFO] Starting Backend...${NC}"
cd backend
source venv/bin/activate
python3 api.py > "../$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}[OK] Backend started (PID: $BACKEND_PID)${NC}"

cd ../frontend
echo -e "${YELLOW}[INFO] Starting Frontend...${NC}"
npm run dev -- --host 0.0.0.0 > "../$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}[OK] Frontend started (PID: $FRONTEND_PID)${NC}"
cd ..

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
