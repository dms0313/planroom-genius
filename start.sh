#!/bin/bash
#
# Planroom Genius - Start Script (Linux / Raspberry Pi 5)
#

if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find python in venv (Bookworm may only have python3)
if [ -f "$SCRIPT_DIR/backend/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/backend/venv/bin/python"
elif [ -f "$SCRIPT_DIR/backend/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/backend/venv/bin/python3"
else
    echo "Error: Python venv not found. Run setup first:"
    echo "  bash pi5-setup.sh"
    exit 1
fi

echo "Starting Planroom Genius..."
exec "$PYTHON" "$SCRIPT_DIR/start.py"
