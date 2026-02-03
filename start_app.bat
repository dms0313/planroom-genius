@echo off
echo ===================================================
echo 🚀 STARTING PLANROOM GENIUS SYSTEM
echo ===================================================

:: Start Backend (API + Scheduler)
echo.
echo [1/2] Launching Backend Server...
start "Planroom Backend" cmd /k "cd /d %~dp0 && call backend\venv\Scripts\activate && python backend\run.py"

:: Start Frontend
echo.
echo [2/2] Launching Frontend Dashboard...
start "Planroom Frontend" cmd /k "cd /d %~dp0\frontend && npm run dev"

echo.
echo ✅ System started! 
echo    - Backend API: http://localhost:8000
echo    - Dashboard:   http://localhost:3000
echo.
echo To stop, close the opened terminal windows.
pause
