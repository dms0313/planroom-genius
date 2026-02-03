#!/bin/bash
# Planroom Genius - Raspberry Pi Setup Script

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}     Planroom Genius - pi setup          ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 1. Update System & Install Dependencies
echo -e "${YELLOW}[INFO] Updating system packages...${NC}"
sudo apt-get update
sudo apt-get install -y python3-full python3-pip python3-venv nodejs npm libasound2 chromium-browser chromium-codecs-ffmpeg

# 2. Setup Backend
echo -e "${YELLOW}[INFO] Setting up Backend...${NC}"
# Use the backend in the root folder, not in pi5_build
cd ../backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}[INFO] Creating Python virtual environment...${NC}"
    python3 -m venv venv
fi

# Install python dependencies
echo -e "${YELLOW}[INFO] Installing Python requirements...${NC}"
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Install Playwright browsers
echo -e "${YELLOW}[INFO] Installing Playwright browsers...${NC}"
./venv/bin/playwright install chromium

# Return to script dir
cd "$SCRIPT_DIR"

# 3. Setup Frontend
echo -e "${YELLOW}[INFO] Setting up Frontend...${NC}"
cd ../frontend
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}[INFO] Installing Node modules...${NC}"
    npm install
else
    echo -e "${GREEN}[OK] Node modules already installed.${NC}"
fi

# Return to script dir
cd "$SCRIPT_DIR"

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}  Setup Complete! ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo -e "You can now run: ${GREEN}./start_pi.sh${NC}"
echo -e "For manual login (VNC): ${GREEN}./manual_login.sh${NC}"
chmod +x start_pi.sh manual_login.sh
