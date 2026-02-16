#!/bin/bash
#
# Planroom Genius - Install Systemd Service
# For Raspberry Pi 5 auto-start on boot
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================================="
echo "  Installing Planroom Genius Systemd Service"
echo "=================================================="
echo ""

# Get current user and directory
CURRENT_USER=$(whoami)
INSTALL_DIR=$(pwd)

# Check if running as root (we need sudo for systemctl)
if [ "$EUID" -eq 0 ]; then
    echo "Please run without sudo. The script will ask for sudo when needed."
    exit 1
fi

# Create service file with correct paths
echo "Creating service file for user: $CURRENT_USER"
echo "Install directory: $INSTALL_DIR"
echo ""

# Detect RAM for memory limit
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
RAM_GB_INT=$(echo "$RAM_KB / 1024 / 1024" | bc)
if (( RAM_GB_INT >= 8 )); then
    MEM_LIMIT="4G"
else
    MEM_LIMIT="2G"
fi
echo "RAM detected: ${RAM_GB_INT}GB -> MemoryMax=${MEM_LIMIT}"

# Find python executable (Bookworm may only have python3)
if [ -f "$INSTALL_DIR/backend/venv/bin/python" ]; then
    VENV_PYTHON="$INSTALL_DIR/backend/venv/bin/python"
elif [ -f "$INSTALL_DIR/backend/venv/bin/python3" ]; then
    VENV_PYTHON="$INSTALL_DIR/backend/venv/bin/python3"
else
    echo "Error: Python venv not found. Run pi5-setup.sh first."
    exit 1
fi
echo "Python: $VENV_PYTHON"

# Generate customized service file
cat > /tmp/planroom-genius.service << EOF
[Unit]
Description=Planroom Genius - Construction Lead Intelligence
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_PYTHON $INSTALL_DIR/start.py
Restart=always
RestartSec=10
Environment="HEADLESS=true"
Environment="HOME=/home/$CURRENT_USER"
Environment="XDG_CONFIG_HOME=/home/$CURRENT_USER/.config"
Environment="PLAYWRIGHT_BROWSERS_PATH=/home/$CURRENT_USER/.cache/ms-playwright"
MemoryMax=${MEM_LIMIT}
CPUQuota=80%
NoNewPrivileges=true
PrivateTmp=true
StandardOutput=journal
StandardError=journal
SyslogIdentifier=planroom-genius
TimeoutStartSec=90
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

# Install the service
echo "Installing service..."
sudo cp /tmp/planroom-genius.service /etc/systemd/system/planroom-genius.service
sudo systemctl daemon-reload

echo ""
echo -e "${GREEN}Service installed successfully!${NC}"
echo ""
echo "Commands:"
echo "  sudo systemctl enable planroom-genius  # Enable auto-start on boot"
echo "  sudo systemctl start planroom-genius   # Start now"
echo "  sudo systemctl status planroom-genius  # Check status"
echo "  sudo systemctl stop planroom-genius    # Stop"
echo "  sudo journalctl -u planroom-genius -f  # View logs"
echo ""

# Ask to enable
read -p "Enable auto-start on boot? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl enable planroom-genius
    echo -e "${GREEN}Auto-start enabled!${NC}"
fi

# Ask to start now
read -p "Start the service now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl start planroom-genius
    sleep 2
    sudo systemctl status planroom-genius --no-pager
fi

echo ""
echo "Done! Access the dashboard at:"
IP=$(hostname -I | awk '{print $1}')
echo "  http://${IP}:5173"
