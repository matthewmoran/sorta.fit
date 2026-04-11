@echo off
echo ================================================
echo   Sorta.Fit Runner
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed.
    echo Download from https://python.org
    exit /b 1
)

echo Starting runner...
echo.

python "%~dp0run.py" %*
