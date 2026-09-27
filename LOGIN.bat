@echo off
title Garmin Connect Login
cd /d "%~dp0"
python garmin_login.py
echo.
echo ------------------------------------------------------------
echo Press any key to close this window.
pause >nul
