@echo off
setlocal

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set ROOT_DIR=%%~fI
cd /d "%ROOT_DIR%"

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

if exist "exe\LostArkWatcher.exe" (
    echo Stopping running LostArkWatcher.exe before build...
    for /L %%I in (1,1,3) do (
        if exist "exe\LostArkWatcher.exe" (
            taskkill /IM LostArkWatcher.exe /F >nul 2>nul
            del /F /Q "exe\LostArkWatcher.exe" >nul 2>nul
            if exist "exe\LostArkWatcher.exe" ping 127.0.0.1 -n 2 >nul
        )
    )
    if exist "exe\LostArkWatcher.exe" (
        echo.
        echo Could not replace exe\LostArkWatcher.exe because it is still locked.
        echo Close any running LostArkWatcher.exe process and try again.
        goto :fail
    )
)

%PY_CMD% -m PyInstaller --noconfirm --clean --distpath exe --workpath build "build_tools\LostArkWatcher.spec"
if not %errorlevel%==0 goto :fail

echo.
echo Build complete.
echo EXE path: exe\LostArkWatcher.exe
goto :end

:fail
echo.
echo Build failed.
pause
exit /b 1

:end
endlocal
exit /b 0
