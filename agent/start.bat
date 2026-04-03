@echo off
cd /d "%~dp0"
pip install -r requirements.txt -q 2>nul
start "" pythonw.exe run.pyw
echo Agent started in background.
timeout /t 3 >nul
