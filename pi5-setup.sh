#!/bin/bash
#
# Planroom Genius - Raspberry Pi 5 Quick Setup
# Optimized for Raspberry Pi 5 with Bookworm OS (64-bit)
#
# Usage: curl -sSL https://your-repo/pi5-setup.sh | bash
#    or: chmod +x pi5-setup.sh && ./pi5-setup.sh
#

set -e

echo "=================================================="
echo "  PLANROOM GENIUS - Raspberry Pi 5 Quick Setup"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Pi 5
check_pi5() {
    echo -n "Checking hardware... "
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(cat /proc/device-tree/model | tr -d '\0')
        if [[ "$MODEL" == *"Raspberry Pi 5"* ]]; then
            echo -e "${GREEN}Raspberry Pi 5 detected${NC}"
            echo "  Model: $MODEL"
            return 0
        fi
    fi

    # Fallback: check cpuinfo for BCM2712
    if grep -q "BCM2712" /proc/cpuinfo 2>/dev/null; then
        echo -e "${GREEN}Raspberry Pi 5 detected (BCM2712)${NC}"
        return 0
    fi

    echo -e "${YELLOW}Warning: Not running on Raspberry Pi 5${NC}"
    echo "  This script is optimized for Pi 5. Continue anyway? (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 1
    fi
}

# Check 64-bit OS
check_64bit() {
    echo -n "Checking OS architecture... "
    ARCH=$(uname -m)
    if [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "arm64" ]]; then
        echo -e "${GREEN}64-bit OS${NC}"
    else
        echo -e "${RED}32-bit OS detected${NC}"
        echo ""
        echo "ERROR: 64-bit Raspberry Pi OS is required for optimal performance."
        echo "Please reinstall with Raspberry Pi OS (64-bit) from:"
        echo "  https://www.raspberrypi.com/software/"
        exit 1
    fi
}

# Check RAM
check_ram() {
    echo -n "Checking RAM... "
    RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    RAM_GB=$(echo "scale=1; $RAM_KB / 1024 / 1024" | bc)
    echo -e "${GREEN}${RAM_GB} GB${NC}"

    if (( $(echo "$RAM_GB < 4" | bc -l) )); then
        echo -e "${YELLOW}Warning: 4GB+ RAM recommended for browser automation${NC}"
    fi
}

# Check for active cooler
check_cooling() {
    echo -n "Checking cooling... "
    if [ -f /sys/class/thermal/cooling_device0/type ]; then
        COOLER=$(cat /sys/class/thermal/cooling_device0/type)
        if [[ "$COOLER" == *"fan"* ]]; then
            echo -e "${GREEN}Active cooler detected${NC}"
            return
        fi
    fi
    echo -e "${YELLOW}No active cooler detected${NC}"
    echo "  Tip: Active cooler recommended for sustained workloads"
}

# Get current temperature
check_temp() {
    echo -n "Checking temperature... "
    if command -v vcgencmd &> /dev/null; then
        TEMP=$(vcgencmd measure_temp | cut -d'=' -f2)
        echo -e "${GREEN}${TEMP}${NC}"
    else
        echo "N/A"
    fi
}

# Update system
update_system() {
    echo ""
    echo "[1/7] Updating system packages..."
    sudo apt-get update -qq
    sudo apt-get upgrade -y -qq
    echo -e "${GREEN}✓ System updated${NC}"
}

# Install Python
install_python() {
    echo ""
    echo "[2/7] Installing Python 3 with venv support..."
    sudo apt-get install -y -qq python3 python3-pip python3-venv python3-full
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ $PYTHON_VERSION installed${NC}"
}

# Install Node.js
install_node() {
    echo ""
    echo "[3/7] Installing Node.js 20 LTS..."
    if ! command -v node &> /dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - > /dev/null 2>&1
        sudo apt-get install -y -qq nodejs
    fi
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✓ Node.js $NODE_VERSION installed${NC}"
}

# Install browser dependencies
install_browser_deps() {
    echo ""
    echo "[4/7] Installing Chromium and browser dependencies..."
    sudo apt-get install -y -qq \
        chromium-browser \
        chromium-codecs-ffmpeg-extra \
        libgbm1 \
        libxkbcommon0 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        libatspi2.0-0 \
        libgtk-3-0
    echo -e "${GREEN}✓ Chromium and dependencies installed${NC}"
}

# Setup Python environment
setup_python_env() {
    echo ""
    echo "[5/7] Setting up Python virtual environment..."

    # Remove existing venv if present
    if [ -d "backend/venv" ]; then
        rm -rf backend/venv
    fi

    # Create venv with system site packages for Pi compatibility
    python3 -m venv --system-site-packages backend/venv

    # Upgrade pip and install dependencies
    backend/venv/bin/pip install --upgrade pip wheel setuptools -q
    backend/venv/bin/pip install -r backend/requirements.txt -q

    echo -e "${GREEN}✓ Python environment ready${NC}"
}

# Setup Playwright
setup_playwright() {
    echo ""
    echo "[6/7] Installing Playwright for ARM64..."
    backend/venv/bin/python -m playwright install chromium
    backend/venv/bin/python -m playwright install-deps chromium
    echo -e "${GREEN}✓ Playwright ready${NC}"
}

# Setup frontend
setup_frontend() {
    echo ""
    echo "[7/7] Installing frontend dependencies..."
    cd frontend
    npm install -q
    cd ..
    echo -e "${GREEN}✓ Frontend ready${NC}"
}

# Create .env if needed
setup_env() {
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            echo "" >> .env
            echo "# Raspberry Pi 5 Optimizations" >> .env
            echo "HEADLESS=true" >> .env
            echo -e "${GREEN}✓ Created .env from template${NC}"
        fi
    fi
}

# Make scripts executable
setup_permissions() {
    chmod +x start.sh stop.sh start.py setup.py 2>/dev/null || true
}

# Print final instructions
print_success() {
    echo ""
    echo "=================================================="
    echo -e "${GREEN}  SETUP COMPLETE!${NC}"
    echo "=================================================="
    echo ""
    echo "Next steps:"
    echo ""
    echo "  1. Configure your credentials:"
    echo "     nano .env"
    echo ""
    echo "  2. Start the application:"
    echo "     ./start.sh"
    echo ""
    echo "  3. Access the dashboard:"
    IP=$(hostname -I | awk '{print $1}')
    echo "     Local:   http://localhost:5173"
    echo "     Network: http://${IP}:5173"
    echo ""
    echo "Pi 5 Tips:"
    echo "  - Active cooler keeps CPU at optimal temps under load"
    echo "  - App runs headless by default (no GUI needed)"
    echo "  - For autostart on boot, see: systemctl enable planroom-genius"
    echo ""
}

# Main execution
main() {
    # Pre-flight checks
    check_pi5
    check_64bit
    check_ram
    check_cooling
    check_temp

    echo ""
    echo "Ready to install Planroom Genius?"
    echo "Press Enter to continue or Ctrl+C to cancel..."
    read -r

    # Installation steps
    update_system
    install_python
    install_node
    install_browser_deps
    setup_python_env
    setup_playwright
    setup_frontend
    setup_env
    setup_permissions

    # Done!
    print_success
}

# Run main function
main
