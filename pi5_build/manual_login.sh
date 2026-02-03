#!/bin/bash
# Planroom Genius - Manual Login Helper

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}     Planroom Genius - Manual Login      ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo -e "${YELLOW}This will open a browser window.${NC}"
echo -e "${YELLOW}Please Login to BuildingConnected and PlanHub.${NC}"
echo -e "${YELLOW}Press Enter in this terminal when finished.${NC}"
echo ""

# Define backend directory relative to this script
BACKEND_DIR="../backend"

if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo -e "${RED}[ERROR] Virtual environment not found.${NC}"
    echo "Please run: ./setup_pi.sh"
    exit 1
fi

cd "$BACKEND_DIR"
source venv/bin/activate

# Run the python script (HEADLESS=False is enforced by the script itself)
python3 manual_login.py

echo -e "${GREEN}Session saved! You can now run ./start_pi.sh${NC}"
