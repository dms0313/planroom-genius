#!/bin/bash
#
# Planroom Genius - Raspberry Pi 5 Complete Setup
# Optimized for Raspberry Pi 5 with Bookworm OS (64-bit)
#
# Usage: chmod +x pi5-setup.sh && ./pi5-setup.sh
#    or: bash pi5-setup.sh
#

# Ensure we're running under bash, not dash/sh
if [ -z "$BASH_VERSION" ]; then
    echo "Re-launching with bash..."
    exec bash "$0" "$@"
fi

set -e

echo "=================================================="
echo "  PLANROOM GENIUS - Raspberry Pi 5 Complete Setup"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_USER=$(whoami)

log_ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
log_err()  { echo -e "  ${RED}✗${NC} $1"; }
log_info() { echo -e "  ${CYAN}→${NC} $1"; }

# ──────────────────────────────────────────────
# PRE-FLIGHT CHECKS
# ──────────────────────────────────────────────

check_pi5() {
    echo -n "Checking hardware... "
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(tr -d '\0' < /proc/device-tree/model)
        if [[ "$MODEL" == *"Raspberry Pi 5"* ]]; then
            echo -e "${GREEN}Raspberry Pi 5 detected${NC}"
            log_info "Model: $MODEL"
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

check_64bit() {
    echo -n "Checking OS architecture... "
    ARCH=$(uname -m)
    DPKG_ARCH=$(dpkg --print-architecture 2>/dev/null || echo "unknown")
    KERNEL_BITS=$(getconf LONG_BIT 2>/dev/null || echo "unknown")

    if [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "arm64" ]] || \
       [[ "$DPKG_ARCH" == "arm64" ]] || [[ "$KERNEL_BITS" == "64" ]]; then
        echo -e "${GREEN}64-bit OS confirmed${NC}"
        log_info "Arch: $ARCH / dpkg: $DPKG_ARCH / kernel: ${KERNEL_BITS}-bit"
    else
        echo -e "${RED}ERROR: 64-bit OS required${NC}"
        echo "  Raspberry Pi OS (64-bit) Bookworm is required."
        echo "  Re-image your SD card with the 64-bit version from:"
        echo "  https://www.raspberrypi.com/software/"
        exit 1
    fi
}

check_ram() {
    echo -n "Checking RAM... "
    RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    RAM_GB=$(echo "scale=1; $RAM_KB / 1024 / 1024" | bc)
    RAM_GB_INT=$(echo "$RAM_GB" | cut -d. -f1)
    echo -e "${GREEN}${RAM_GB} GB${NC}"

    if (( RAM_GB_INT < 4 )); then
        log_warn "4GB+ RAM recommended. 2GB will work but browser may be slow."
    fi
}

check_disk_space() {
    echo -n "Checking disk space... "
    AVAIL_MB=$(df -m "$INSTALL_DIR" | tail -1 | awk '{print $4}')
    AVAIL_GB=$(echo "scale=1; $AVAIL_MB / 1024" | bc)
    echo -e "${GREEN}${AVAIL_GB} GB available${NC}"

    if (( AVAIL_MB < 3000 )); then
        log_err "Need at least 3GB free disk space (Chromium ~400MB + deps)"
        exit 1
    fi
}

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
    log_warn "Active cooler recommended for sustained browser workloads"
}

check_temp() {
    echo -n "Checking temperature... "
    if command -v vcgencmd &> /dev/null; then
        TEMP=$(vcgencmd measure_temp | cut -d'=' -f2)
        echo -e "${GREEN}${TEMP}${NC}"
    else
        echo "N/A"
    fi
}

# ──────────────────────────────────────────────
# INSTALLATION STEPS
# ──────────────────────────────────────────────

update_system() {
    echo ""
    echo -e "${CYAN}[1/9] Updating system packages...${NC}"
    sudo apt-get update -qq
    sudo apt-get upgrade -y -qq
    log_ok "System updated"
}

install_python() {
    echo ""
    echo -e "${CYAN}[2/9] Installing Python 3 with venv support...${NC}"
    sudo apt-get install -y -qq \
        python3 \
        python3-pip \
        python3-venv \
        python3-full \
        python3-dev \
        build-essential \
        bc
    PYTHON_VERSION=$(python3 --version)
    log_ok "$PYTHON_VERSION installed"
}

install_node() {
    echo ""
    echo -e "${CYAN}[3/9] Installing Node.js 20 LTS...${NC}"
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1 | tr -d 'v')
        if (( NODE_MAJOR >= 20 )); then
            log_ok "Node.js $NODE_VERSION already installed"
            return
        fi
        log_warn "Node.js $NODE_VERSION is too old, upgrading..."
    fi

    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - > /dev/null 2>&1
    sudo apt-get install -y -qq nodejs
    NODE_VERSION=$(node --version)
    log_ok "Node.js $NODE_VERSION installed"
}

install_chromium_and_deps() {
    echo ""
    echo -e "${CYAN}[4/9] Installing Chromium browser and dependencies for ARM64...${NC}"

    # Install system Chromium (ARM64 native from Bookworm repos)
    # This is the primary browser that Playwright will use as a fallback
    sudo apt-get install -y -qq \
        chromium-browser \
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
        libgtk-3-0 \
        libglib2.0-0 \
        libnss3 \
        libnspr4 \
        libdbus-1-3 \
        libxext6 \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxshmfence1 \
        fonts-liberation \
        xdg-utils \
        wget \
        ca-certificates

    # Verify chromium-browser is working
    if command -v chromium-browser &> /dev/null; then
        CHROMIUM_VERSION=$(chromium-browser --version 2>/dev/null | head -1)
        log_ok "System Chromium installed: $CHROMIUM_VERSION"
    else
        log_warn "chromium-browser command not found, Playwright will use its own"
    fi

    # Install optional codecs (may not be available on all Bookworm variants)
    sudo apt-get install -y -qq chromium-codecs-ffmpeg 2>/dev/null || \
        log_warn "chromium-codecs-ffmpeg not available (non-critical)"

    log_ok "Browser dependencies installed"
}

setup_python_env() {
    echo ""
    echo -e "${CYAN}[5/9] Setting up Python virtual environment...${NC}"

    VENV_PATH="$INSTALL_DIR/backend/venv"

    # Remove existing venv if present (clean install)
    if [ -d "$VENV_PATH" ]; then
        log_info "Removing existing venv..."
        rm -rf "$VENV_PATH"
    fi

    # Create venv with system site packages for Pi compatibility
    python3 -m venv --system-site-packages "$VENV_PATH"

    # Upgrade pip and install dependencies
    "$VENV_PATH/bin/pip" install --upgrade pip wheel setuptools -q
    "$VENV_PATH/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q

    log_ok "Python environment ready"
}

setup_playwright() {
    echo ""
    echo -e "${CYAN}[6/9] Installing Playwright Chromium for ARM64...${NC}"

    VENV_PYTHON="$INSTALL_DIR/backend/venv/bin/python"

    # Install Playwright's bundled Chromium (optimized for automation)
    "$VENV_PYTHON" -m playwright install chromium 2>&1 | tail -3

    # Install system dependencies that Playwright needs
    "$VENV_PYTHON" -m playwright install-deps chromium 2>&1 | tail -3

    # Verify Playwright can launch
    echo "  Verifying Playwright browser launch..."
    if "$VENV_PYTHON" -c "
import asyncio
from playwright.async_api import async_playwright
async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = await browser.new_page()
        await page.goto('about:blank')
        title = await page.title()
        await browser.close()
        return True
result = asyncio.run(test())
print('Browser launch: OK')
" 2>/dev/null; then
        log_ok "Playwright Chromium verified and working"
    else
        log_warn "Playwright browser launch test failed"
        log_info "Trying with system Chromium as fallback..."

        # Configure Playwright to use system Chromium
        CHROMIUM_PATH=$(which chromium-browser 2>/dev/null)
        if [ -n "$CHROMIUM_PATH" ]; then
            log_info "System Chromium at: $CHROMIUM_PATH"
            log_info "Set PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=$CHROMIUM_PATH if needed"
        fi
    fi
}

setup_frontend() {
    echo ""
    echo -e "${CYAN}[7/9] Building frontend...${NC}"

    cd "$INSTALL_DIR/frontend"
    npm install -q 2>&1 | tail -3

    # Build production assets (so we don't need vite dev server in production)
    npx vite build 2>&1 | tail -3

    cd "$INSTALL_DIR"
    log_ok "Frontend ready"
}

setup_env() {
    echo ""
    echo -e "${CYAN}[8/9] Configuring environment...${NC}"

    if [ ! -f "$INSTALL_DIR/.env" ]; then
        if [ -f "$INSTALL_DIR/.env.example" ]; then
            cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
            log_ok "Created .env from template"
        else
            # Create minimal .env
            cat > "$INSTALL_DIR/.env" << 'ENVEOF'
# Planroom Genius - Pi 5 Configuration
# Fill in your credentials below

GEMINI_API_KEY=your_gemini_api_key_here
SITE_LOGIN=your_email@domain.com
SITE_PW=your_password
BIDPLANROOM_EMAIL=your_email@domain.com
BIDPLANROOM_PW=your_password
LOYD_LOGIN=your_email@domain.com
LOYD_PW=your_password
HEADLESS=true
USE_GOOGLE_DRIVE=false
ENVEOF
            log_ok "Created .env template"
        fi
        log_warn "You MUST edit .env with your actual credentials before running!"
    else
        log_ok ".env already exists (preserving existing config)"
    fi

    # Ensure HEADLESS=true is set for Pi
    if ! grep -q "HEADLESS=true" "$INSTALL_DIR/.env"; then
        echo "" >> "$INSTALL_DIR/.env"
        echo "# Raspberry Pi 5 - headless mode" >> "$INSTALL_DIR/.env"
        echo "HEADLESS=true" >> "$INSTALL_DIR/.env"
        log_info "Added HEADLESS=true to .env"
    fi
}

setup_permissions_and_dirs() {
    echo ""
    echo -e "${CYAN}[9/9] Setting up permissions and directories...${NC}"

    # Create necessary directories
    mkdir -p "$INSTALL_DIR/backend/downloads"
    mkdir -p "$INSTALL_DIR/backend/data"
    mkdir -p "$INSTALL_DIR/backend/backups"
    mkdir -p "$INSTALL_DIR/backend/playwright_profile"

    # Make scripts executable
    chmod +x "$INSTALL_DIR/start.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/stop.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/start.py" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/setup.py" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/install-service.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/pi5-setup.sh" 2>/dev/null || true

    # Ensure the Chromium user data dir exists
    mkdir -p "$HOME/.config/chromium/Default"

    log_ok "Permissions and directories configured"
}

# ──────────────────────────────────────────────
# OPTIONAL: SWAP CONFIGURATION
# ──────────────────────────────────────────────

configure_swap() {
    RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    RAM_GB_INT=$(echo "$RAM_KB / 1024 / 1024" | bc)

    if (( RAM_GB_INT <= 4 )); then
        echo ""
        echo -e "${CYAN}Optimizing swap for 4GB Pi 5...${NC}"

        CURRENT_SWAP=$(grep CONF_SWAPSIZE /etc/dphys-swapfile 2>/dev/null | grep -v "^#" | cut -d= -f2)
        if [ -n "$CURRENT_SWAP" ] && (( CURRENT_SWAP >= 2048 )); then
            log_ok "Swap already at ${CURRENT_SWAP}MB"
        else
            echo "  Browser automation benefits from 2GB+ swap on 4GB models."
            echo -n "  Increase swap to 2GB? (y/n) "
            read -r response
            if [[ "$response" =~ ^[Yy]$ ]]; then
                sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
                sudo dphys-swapfile setup
                sudo dphys-swapfile swapon
                log_ok "Swap increased to 2GB"
            fi
        fi
    fi
}

# ──────────────────────────────────────────────
# SUCCESS MESSAGE
# ──────────────────────────────────────────────

print_success() {
    IP=$(hostname -I | awk '{print $1}')

    echo ""
    echo "=================================================="
    echo -e "${GREEN}  SETUP COMPLETE!${NC}"
    echo "=================================================="
    echo ""
    echo "  Next steps:"
    echo ""
    echo "  1. Edit your credentials:"
    echo -e "     ${CYAN}nano $INSTALL_DIR/.env${NC}"
    echo ""
    echo "  2. Start the application:"
    echo -e "     ${CYAN}$INSTALL_DIR/start.sh${NC}"
    echo ""
    echo "  3. Access the dashboard:"
    echo -e "     Local:   ${CYAN}http://localhost:5173${NC}"
    echo -e "     Network: ${CYAN}http://${IP}:5173${NC}"
    echo ""
    echo "  4. (Optional) Install as system service for auto-start:"
    echo -e "     ${CYAN}$INSTALL_DIR/install-service.sh${NC}"
    echo ""
    echo "  Pi 5 Notes:"
    echo "  - App runs headless (no GUI needed)"
    echo "  - Active cooler recommended for sustained scraping"
    echo "  - Logs: journalctl -u planroom-genius -f (if using service)"
    echo "  - Stop: $INSTALL_DIR/stop.sh"
    echo ""
}

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

main() {
    echo "Pre-flight checks:"
    echo ""

    check_pi5
    check_64bit
    check_ram
    check_disk_space
    check_cooling
    check_temp

    echo ""
    echo "Ready to install Planroom Genius?"
    echo "This will install: Python 3, Node.js 20, Chromium, Playwright, and all dependencies."
    echo "Press Enter to continue or Ctrl+C to cancel..."
    read -r

    update_system
    install_python
    install_node
    install_chromium_and_deps
    setup_python_env
    setup_playwright
    setup_frontend
    setup_env
    setup_permissions_and_dirs
    configure_swap

    print_success
}

# Run
main
