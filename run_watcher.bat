@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py watcher.py
) else (
    python watcher.py
)

if not %errorlevel%==0 (
    echo.
    echo Failed to launch watcher.py
    pause
)

endlocal
