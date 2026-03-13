@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set PY_CMD=py
) else (
    set PY_CMD=python
)

%PY_CMD% -m pip install --upgrade pip
if not %errorlevel%==0 goto :fail

%PY_CMD% -m pip install pyinstaller
if not %errorlevel%==0 goto :fail

%PY_CMD% -m PyInstaller --noconfirm --clean --windowed --onefile --name LostArkWatcher watcher.py
if not %errorlevel%==0 goto :fail

echo.
echo Build complete.
echo EXE path: dist\LostArkWatcher.exe
goto :end

:fail
echo.
echo Build failed.
pause

:end
endlocal
