#!/bin/bash
# Planroom Genius - Linux/Raspberry Pi startup script
# This is a wrapper that calls the Python startup script

# Change to script directory
cd "$(dirname "$0")"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please run: sudo apt-get install python3"
    exit 1
fi

# Check if setup was run
if [ ! -d "backend/venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Please run setup first: python3 setup.py"
    exit 1
fi

# Run the Python startup script
python3 start.py
