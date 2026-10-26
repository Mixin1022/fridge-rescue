@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
call .venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto failed
call .venv\Scripts\python.exe setup_local.py
if errorlevel 1 goto failed
echo Installation complete. Read README.md for configuration.
pause
exit /b 0
:failed
echo Installation failed. Keep this window open.
pause
exit /b 1
