@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

set "PYTHON_CMD=python"
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%PROJECT_ROOT%\.venv\Scripts\python.exe"
)

set "ENV_FILE=%PROJECT_ROOT%\.env"
set "APP_PORT=8000"
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        if /I "%%~A"=="APP_PORT" set "APP_PORT=%%~B"
    )
)

set "API_DOCS_URL=http://127.0.0.1:%APP_PORT%/docs"
set "API_HEALTH_URL=http://127.0.0.1:%APP_PORT%/api/v1/health"
set "STREAMLIT_URL=http://127.0.0.1:8501"

echo [1/3] Install requirements
"%PYTHON_CMD%" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/3] Initialize database
"%PYTHON_CMD%" "%PROJECT_ROOT%\scripts\init_db.py"
if errorlevel 1 goto :error

echo [3/3] Launch FastAPI and Streamlit
start "Sequencer API" powershell -NoExit -Command "& '%PYTHON_CMD%' '%PROJECT_ROOT%\scripts\run_api.py'"
start "Sequencer UI" powershell -NoExit -Command "& '%PYTHON_CMD%' '%PROJECT_ROOT%\scripts\run_ui.py'"

echo Waiting for FastAPI: %API_HEALTH_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(60); $ready=$false; while((Get-Date)-lt $deadline){ try { $resp=Invoke-WebRequest -Uri '%API_HEALTH_URL%' -UseBasicParsing -TimeoutSec 5; if($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500){ $ready=$true; break } } catch {} Start-Sleep -Seconds 2 }; if($ready){ Start-Process '%API_DOCS_URL%'; exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo FastAPI did not become ready within 60 seconds. Open manually if needed: %API_DOCS_URL%
) else (
    echo Opened FastAPI docs: %API_DOCS_URL%
)

echo Waiting for Streamlit: %STREAMLIT_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(90); $ready=$false; while((Get-Date)-lt $deadline){ try { $resp=Invoke-WebRequest -Uri '%STREAMLIT_URL%' -UseBasicParsing -TimeoutSec 5; if($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500){ $ready=$true; break } } catch {} Start-Sleep -Seconds 2 }; if($ready){ Start-Process '%STREAMLIT_URL%'; exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo Streamlit did not become ready within 90 seconds. Open manually if needed: %STREAMLIT_URL%
) else (
    echo Opened Streamlit UI: %STREAMLIT_URL%
)

goto :eof

:error
echo Startup failed. Please review the error output above.
exit /b 1
