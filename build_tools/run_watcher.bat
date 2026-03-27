@echo off
setlocal

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set ROOT_DIR=%%~fI
cd /d "%ROOT_DIR%"

where py >nul 2>nul
if %errorlevel%==0 (
    py src\watcher.py
) else (
    python src\watcher.py
)

if not %errorlevel%==0 (
    echo.
    echo Failed to launch src\watcher.py
    pause
)

endlocal
