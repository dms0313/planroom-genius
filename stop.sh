#!/bin/bash
#
# Planroom Genius - Stop Script (Linux / Raspberry Pi 5)
#

echo "Stopping Planroom Genius..."

# Kill backend (uvicorn on port 8000)
pkill -f "uvicorn.*api:app" 2>/dev/null && echo "Backend stopped" || echo "Backend not running"

# Kill frontend (vite on port 5173)
pkill -f "vite.*--host" 2>/dev/null && echo "Frontend stopped" || echo "Frontend not running"

# Kill any lingering chromium from playwright
pkill -f "chromium.*--headless" 2>/dev/null

echo "Done."
