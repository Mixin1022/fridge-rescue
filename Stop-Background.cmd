@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0pc_background.ps1" -Action stop
if errorlevel 1 pause
