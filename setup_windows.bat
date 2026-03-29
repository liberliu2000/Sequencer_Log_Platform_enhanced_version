@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ==================================================
echo CycleDash Windows setup launcher
echo Project root: %CD%
echo ==================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup_windows.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Setup completed successfully.
) else (
    echo Setup failed with exit code %EXIT_CODE%.
)
echo.
echo Press any key to close this window...
pause >nul
exit /b %EXIT_CODE%
