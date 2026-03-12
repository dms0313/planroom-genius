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
echo ""
echo -e "${YELLOW}Select login mode:${NC}"
echo "  1) All planrooms (BuildingConnected, PlanHub, Bidplanroom, Loyd)"
echo "  2) iSqFt (captures JWT token)"
echo "  3) Both"
echo ""
read -rp "Enter choice [1-3]: " CHOICE
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

# Run the python script(s) based on choice
case "$CHOICE" in
    1)
        python3 manual_login.py
        ;;
    2)
        python3 manual_login.py --isqft
        ;;
    3)
        python3 manual_login.py
        echo ""
        python3 manual_login.py --isqft
        ;;
    *)
        echo -e "${YELLOW}Invalid choice. Running all planrooms by default.${NC}"
        python3 manual_login.py
        ;;
esac

echo -e "${GREEN}Session saved! You can now run ./start_pi.sh${NC}"
