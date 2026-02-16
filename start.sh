#!/bin/bash
#
# Planroom Genius - Start Script (Linux / Raspberry Pi 5)
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/backend/venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "Error: Python venv not found. Run setup first:"
    echo "  python3 setup.py"
    exit 1
fi

echo "Starting Planroom Genius..."
exec "$PYTHON" "$SCRIPT_DIR/start.py"
