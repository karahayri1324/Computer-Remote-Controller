@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "AGENT_DIR=%SCRIPT_DIR%agent"

:: Check config exists
if not exist "%AGENT_DIR%\config.yaml" (
    echo Config not found. Run setup.bat first.
    pause
    exit /b 1
)

:: Find Python
set "PY="
where python >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
) else (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        set "PY=python3"
    )
)

if "%PY%"=="" (
    echo [ERROR] Python 3 is not installed!
    pause
    exit /b 1
)

echo Starting RemoteController Agent...
echo Press Ctrl+C to stop.
echo.

cd /d "%AGENT_DIR%"
%PY% main.py
