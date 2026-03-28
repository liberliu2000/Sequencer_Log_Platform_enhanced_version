@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

echo [1/3] 安装依赖
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/3] 初始化数据库
python "%PROJECT_ROOT%\scripts\init_db.py"
if errorlevel 1 goto :error

echo [3/3] 启动 API 与 UI
start "Sequencer API" cmd /k "cd /d \"%PROJECT_ROOT%\" && python \"%PROJECT_ROOT%\scripts\run_api.py\""
start "Sequencer UI" cmd /k "cd /d \"%PROJECT_ROOT%\" && python \"%PROJECT_ROOT%\scripts\run_ui.py\""

echo FastAPI: http://127.0.0.1:8000/docs
echo Streamlit: http://127.0.0.1:8501
goto :eof

:error
echo 启动失败，请检查上面的报错信息。
exit /b 1
