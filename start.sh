#!/bin/bash
# Planroom Genius - Linux/Raspberry Pi startup script
# This is a wrapper that calls the Python startup script

# Change to script directory
cd "$(dirname "$0")"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "If you are on Raspberry Pi, please run: cd pi5_build && ./setup_pi.sh"
    exit 1
fi

# Check if we are in pi5_build environment
if [ -d "pi5_build" ] && [ ! -d "backend/venv" ]; then
    echo "Warning: Root 'backend/venv' not found."
    echo "It looks like you might be trying to run from the root on a Pi."
    echo "Please try running the optimized Pi startup:"
    echo "  cd pi5_build && ./start_pi.sh"
    echo ""
    echo "Or run setup locally: python3 setup.py"
    exit 1
fi

# Check if setup was run
if [ ! -d "backend/venv" ]; then
    echo "Error: Virtual environment not found (backend/venv)"
    echo "Please run setup first: python3 setup.py"
    exit 1
fi

# Run the Python startup script
python3 start.py
