@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ==================================================
echo CycleDash Windows setup launcher
echo Project root: %CD%
echo ==================================================
echo.

py -3.12 -c "import sys" >nul 2>&1
if "%ERRORLEVEL%"=="0" (
    echo Preferred Python detected: 3.12
) else (
    py -3 -c "import sys; print(sys.version)" >nul 2>&1
    if "%ERRORLEVEL%"=="0" (
        echo Python 3.12 was not found. The PowerShell setup will continue checking for 3.11/3.10, but 3.12 is recommended.
    ) else (
        echo Python launcher did not report a usable Python 3 installation. setup_windows.ps1 will perform the final validation.
    )
)
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
