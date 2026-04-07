@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

cls
echo.
echo   ========================================
echo        RemoteController Setup (Windows)
echo   ========================================
echo.

:: ── Check Python ──
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

if "!PY!"=="" (
    echo [ERROR] Python 3 is not installed!
    echo Download from: https://python.org/downloads
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('!PY! --version 2^>^&1') do echo [OK] %%v

set "SCRIPT_DIR=%~dp0"
set "AGENT_DIR=%SCRIPT_DIR%agent"

:: ── Server ──
echo.
echo -- Server --
echo.
set "SERVER_URL=https://rc.thinkerchat.com"
set /p "SERVER_URL=Relay server URL [!SERVER_URL!]: "
:: Remove trailing slash
if "!SERVER_URL:~-1!"=="/" set "SERVER_URL=!SERVER_URL:~0,-1!"

:: ── Account ──
echo.
echo -- Account --
echo.
set /p "USERNAME=Username (min 3 chars, alphanumeric): "

:: Password with masking via PowerShell
echo.
for /f "delims=" %%i in ('powershell -NoProfile -Command "$s = Read-Host 'Password (min 4 chars)' -AsSecureString; $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)"') do set "PASSWORD=%%i"

if "!USERNAME!"=="" (
    echo [ERROR] Username cannot be empty.
    pause
    exit /b 1
)
if "!PASSWORD!"=="" (
    echo [ERROR] Password cannot be empty.
    pause
    exit /b 1
)

:: ── Register ──
echo.
echo -- Registering Account --
echo.

:: Write credentials to temp file to avoid shell escaping issues
set "TMPFILE=%TEMP%\rc_setup_%RANDOM%.py"
(
echo import urllib.request, urllib.error, json, sys
echo url = sys.argv[1] + '/api/register'
echo data = json.dumps({'username': sys.argv[2], 'password': sys.argv[3]}.encode(^)
echo req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}^)
echo try:
echo     resp = urllib.request.urlopen(req^)
echo     body = json.loads(resp.read(^)^)
echo     print('TOKEN:' + body['agent_token']^)
echo except urllib.error.HTTPError as e:
echo     body = json.loads(e.read(^)^)
echo     err = body.get('error', 'Unknown error'^)
echo     print('ERROR:' + err^)
echo except Exception as e:
echo     print('CONNFAIL:' + str(e^)^)
) > "!TMPFILE!"

:: Use a separate Python script for reliable argument passing
set "TMPFILE2=%TEMP%\rc_setup_%RANDOM%.py"
> "!TMPFILE2!" (
    echo import urllib.request, urllib.error, json, os
    echo url = os.environ['RC_SERVER'] + '/api/register'
    echo data = json.dumps({'username': os.environ['RC_USER'], 'password': os.environ['RC_PASS']}).encode()
    echo req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    echo try:
    echo     resp = urllib.request.urlopen(req)
    echo     body = json.loads(resp.read())
    echo     print('TOKEN:' + body['agent_token'])
    echo except urllib.error.HTTPError as e:
    echo     body = json.loads(e.read())
    echo     err = body.get('error', 'Unknown error')
    echo     print('ERROR:' + err)
    echo except Exception as e:
    echo     print('CONNFAIL:' + str(e))
)
del "!TMPFILE!" 2>nul

set "RC_SERVER=!SERVER_URL!"
set "RC_USER=!USERNAME!"
set "RC_PASS=!PASSWORD!"

for /f "delims=" %%r in ('!PY! "!TMPFILE2!" 2^>^&1') do set "RESULT=%%r"
del "!TMPFILE2!" 2>nul

:: Parse result
set "AGENT_TOKEN="
echo !RESULT! | findstr /b "TOKEN:" >nul
if not errorlevel 1 (
    set "AGENT_TOKEN=!RESULT:TOKEN:=!"
    echo [OK] Account created successfully!
    goto :deps
)

echo !RESULT! | findstr /b "ERROR:" >nul
if not errorlevel 1 (
    set "ERR_MSG=!RESULT:ERROR:=!"
    echo !ERR_MSG! | findstr /i "already exists" >nul
    if not errorlevel 1 (
        echo [INFO] Account already exists. Verifying credentials...

        :: Verify login
        set "TMPFILE3=%TEMP%\rc_login_%RANDOM%.py"
        > "!TMPFILE3!" (
            echo import urllib.request, urllib.error, json, os
            echo url = os.environ['RC_SERVER'] + '/api/login'
            echo data = json.dumps({'username': os.environ['RC_USER'], 'password': os.environ['RC_PASS']}).encode()
            echo req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            echo try:
            echo     resp = urllib.request.urlopen(url=req)
            echo     print('OK')
            echo except:
            echo     print('FAIL')
        )
        for /f "delims=" %%r in ('!PY! "!TMPFILE3!" 2^>^&1') do set "LOGIN_RES=%%r"
        del "!TMPFILE3!" 2>nul

        if "!LOGIN_RES!" neq "OK" (
            echo [ERROR] Wrong password for existing account.
            pause
            exit /b 1
        )
        echo [OK] Credentials verified!
        echo.
        echo [NOTE] Agent token was shown only at registration.
        echo If you lost your agent token, you need to create a new account.
        echo.
        set /p "AGENT_TOKEN=Enter your agent token: "
        if "!AGENT_TOKEN!"=="" (
            echo [ERROR] Agent token required.
            pause
            exit /b 1
        )
        goto :deps
    ) else (
        echo [ERROR] !ERR_MSG!
        pause
        exit /b 1
    )
)

echo [ERROR] Could not connect to server.
echo !RESULT!
pause
exit /b 1

:deps
:: ── Install Dependencies ──
echo.
echo -- Installing Dependencies --
echo.

echo Installing Python packages...
!PY! -m pip install -q websockets psutil pyyaml 2>nul
if errorlevel 1 !PY! -m pip install --user -q websockets psutil pyyaml

echo Installing screen capture packages...
!PY! -m pip install -q mss Pillow 2>nul
if errorlevel 1 (
    !PY! -m pip install --user -q mss Pillow 2>nul
    if errorlevel 1 echo [WARNING] Could not install mss/Pillow. Remote desktop won't work.
)

:: ── Create Config ──
echo.
echo -- Creating Config --
echo.

set "WS_URL=!SERVER_URL!"
set "WS_URL=!WS_URL:https://=wss://!"
set "WS_URL=!WS_URL:http://=ws://!"
set "WS_URL=!WS_URL!/ws/agent"

> "!AGENT_DIR!\config.yaml" (
    echo relay_url: "!WS_URL!"
    echo username: "!USERNAME!"
    echo agent_token: "!AGENT_TOKEN!"
    echo heartbeat_interval: 15
    echo reconnect_base_delay: 1
    echo reconnect_max_delay: 60
    echo shell_default_cols: 120
    echo shell_default_rows: 30
    echo allowed_paths: []
    echo max_chunk_size: 524288
    echo sysinfo_cache_seconds: 2
)

echo [OK] Config saved.

echo.
echo   ========================================
echo          Setup Complete!
echo   ========================================
echo.
echo   Username: !USERNAME!
echo   Server:   !SERVER_URL!
echo.
echo   Start:    start.bat
echo   Login:    Open !SERVER_URL! on your phone
echo.
echo   IMPORTANT: Save your agent token!
echo   Token:    !AGENT_TOKEN!
echo.
pause
