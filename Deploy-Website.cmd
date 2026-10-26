@echo off
cd /d "%~dp0"
if not exist wrangler-auto-address.json (
 echo Configure wrangler-auto-address.json using wrangler.example.json first.
 pause
 exit /b 1
)
call .venv\Scripts\python.exe build_cloudflare.py
if errorlevel 1 exit /b 1
call npx.cmd --yes wrangler@4 deploy --config wrangler-auto-address.json
if errorlevel 1 echo Deployment failed. Check Cloudflare login and configuration.
pause
