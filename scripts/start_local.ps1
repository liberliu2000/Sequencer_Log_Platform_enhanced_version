$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "[1/3] 安装依赖"
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "安装依赖失败" }

Write-Host "[2/3] 初始化数据库"
python "$ProjectRoot\scripts\init_db.py"
if ($LASTEXITCODE -ne 0) { throw "初始化数据库失败" }

Write-Host "[3/3] 启动 API 与 UI"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; python '$ProjectRoot\scripts\run_api.py'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ProjectRoot'; python '$ProjectRoot\scripts\run_ui.py'"

Write-Host "FastAPI: http://127.0.0.1:8000/docs"
Write-Host "Streamlit: http://127.0.0.1:8501"
