@echo off
setlocal

:: Find Git Bash
set "GITBASH=%ProgramFiles%\Git\git-bash.exe"
if not exist "%GITBASH%" set "GITBASH=%ProgramFiles(x86)%\Git\git-bash.exe"
if not exist "%GITBASH%" (
    echo ERROR: Git Bash not found. Install Git for Windows:
    echo   https://git-scm.com/downloads
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    echo ERROR: .env not found. Run the setup wizard first:
    echo   setup.bat
    echo.
    pause
    exit /b 1
)

:: Launch in Git Bash
"%GITBASH%" --cd="%CD%" -c "bash core/loop.sh; exec bash"
