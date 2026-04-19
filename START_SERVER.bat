@echo off
title Cambio Express Server
color 1F

echo.
echo  ================================================
echo    CAMBIO EXPRESS — MSB Manager
echo    Starting local server...
echo  ================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found.
    echo  Install from https://python.org — check "Add Python to PATH"
    pause
    exit /b 1
)

cd /d "%~dp0"
echo  Installing dependencies...
pip install -r requirements.txt -q

echo.
echo  ================================================
echo    Running at: http://localhost:5000
echo.
echo    Logins:
echo      Superadmin : superadmin / super2025!
echo      Store Admin: admin      / cambio2025!
echo.
echo    Change passwords immediately in Users section.
echo    Press Ctrl+C to stop.
echo  ================================================
echo.

python app.py
pause
