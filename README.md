# Sequencer Log Platform

面向测序仪多源日志的整理、关联分析、异常诊断与反馈沉淀平台。

当前项目采用 `FastAPI + Streamlit + SQLite`，以浏览器中的 Streamlit 页面作为默认交互入口。

## 运行方式

### 快速开始

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m scripts.init_db
```

### 启动 API

```powershell
python -m scripts.run_api
```

启动后可访问：

```text
http://127.0.0.1:8000/docs
```

### 启动网页端

```powershell
python -m scripts.run_ui
```

启动后可访问：

```text
http://127.0.0.1:8501
```

### 本地一键启动

```powershell
scripts\start_local.ps1
```

## 目录结构

```text
sequencer_log_platform_V43/
├─ app/                         # API、服务层、解析器、数据库与核心逻辑
├─ ui/                          # Streamlit 网页端
├─ config/                      # YAML 配置
├─ scripts/                     # 启动与发版脚本
├─ docs/                        # 补充文档
├─ data/                        # SQLite、上传、导出、缓存与运行数据
├─ requirements.txt             # 后端 / 网页端依赖
└─ README.md
```

## 核心模块

- `app/main.py`：FastAPI 应用入口
- `ui/streamlit_app.py`：Streamlit 网页端入口
- `scripts/run_api.py`：本地 API 启动脚本
- `scripts/run_ui.py`：本地网页端启动脚本
- `scripts/init_db.py`：数据库初始化脚本

## 测试

```powershell
pytest tests
```
