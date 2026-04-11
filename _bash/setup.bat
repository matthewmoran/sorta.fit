@echo off
setlocal

echo ================================================
echo   Sorta.Fit Setup
echo ================================================
echo.

:: Check Node.js
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js is not installed.
    echo Download from https://nodejs.org
    echo.
    pause
    exit /b 1
)

:: Check Git
where git >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git is not installed.
    echo Download from https://git-scm.com/downloads
    echo.
    pause
    exit /b 1
)

echo Dependencies found.
echo.

:: Install npm dependencies if needed
if exist "package.json" (
    if not exist "node_modules" (
        echo Installing dependencies...
        call npm install
        echo.
    )
)

:: Launch setup server
echo Starting setup wizard...
echo Opening http://localhost:3456 in your browser...
echo.
echo Press Ctrl+C to stop.
echo.

node setup/server.js
