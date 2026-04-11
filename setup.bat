@echo off

echo ================================================
echo   Sorta.Fit Setup
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed.
    echo Download from https://python.org
    echo.
    pause
    exit /b 1
)

echo Starting setup wizard...
echo Opening http://localhost:3456 in your browser...
echo.
echo Press Ctrl+C to stop.
echo.

python "%~dp0setup_wizard.py"
