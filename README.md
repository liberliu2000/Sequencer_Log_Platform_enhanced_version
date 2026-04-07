# Sequencer Log Platform Enhanced Version

基于 `FastAPI + Streamlit + Next.js + SQLite` 的测序日志分析平台。

当前仓库同步的是源码版本，便于继续开发、部署和调试；一键启动程序、安装包和打包产物不作为主分支源码的一部分维护。

## 项目概览

平台面向多源测序日志的整理、解析、聚合和问题定位，核心目标是：

- 支持大体积日志和压缩包的上传与解析
- 将多种日志格式统一归一为结构化事件流
- 提供时间轴、错误聚类、参数趋势、周期分析等视图
- 提供任务状态、实时进度、性能摘要和导出能力
- 提供账号、注册审核、权限控制和方案库相关能力
- 预留 LLM 诊断、规则建议和主动学习能力

## 当前能力

### 日志处理与分析

- 批量上传日志文件或压缩包
- 流式解析与聚合，降低大任务内存峰值
- Cycle / Step / 时间轴 / 参数趋势 / 错误分布分析
- 原始日志预览与导出
- `parameter_results` 轻量结果表，减少重复全量扫描

### 运行时与性能

- 任务实时进度、阶段、ETA、预计完成时间展示
- SQLite 锁竞争缓解，减少瞬时写入导致的失败
- CPU / 内存软阈值保护与自适应并发分配
- 任务进度历史和性能快照持久化

### 前端界面

- `ui/` 下的 Streamlit 运维界面
- `frontend/` 下的 Next.js Web 前端
- 根路径 `/` 提供 FastAPI 内置落地页

### 账号与治理

- 登录、注册、会话鉴权
- 注册审核与用户状态管理
- 角色与权限控制
- 方案库、审核流、错误码生成等业务能力

## 目录结构

```text
app/                    FastAPI 后端、服务层、数据模型、数据库与核心逻辑
config/                 YAML 规则与配置
frontend/               Next.js 前端
scripts/                本地运行、初始化与辅助脚本
tests/                  pytest 测试
ui/                     Streamlit 界面
data/                   运行期数据库、上传文件、导出文件与缓存
.env.example            环境变量示例
requirements.txt        Python 依赖
README.md               项目说明
```

## 技术栈

- 后端：`FastAPI`、`SQLAlchemy`、`Pydantic`
- 数据库：`SQLite`
- 运维界面：`Streamlit`、`Plotly`、`Pandas`
- Web 前端：`Next.js`、`React`、`TypeScript`
- 配置：`.env` + `YAML`
- 测试：`pytest`

## 快速开始

推荐环境：

- Python `3.12`
- Node.js `20+`

### 1. 安装 Python 依赖

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### 2. 初始化数据库

```powershell
python -m scripts.init_db
```

该步骤会执行数据库建表、SQLite 迁移和基础数据初始化。

### 3. 启动 FastAPI

```powershell
python -m scripts.run_api
```

默认地址：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/api/v1`

### 4. 启动 Streamlit 界面

```powershell
python -m scripts.run_ui
```

默认地址：

- `http://127.0.0.1:8501`

如果 API 不在默认地址，可先设置：

```powershell
$env:STREAMLIT_API_BASE="http://127.0.0.1:8000/api/v1"
```

### 5. 启动 Next.js 前端

```powershell
cd frontend
npm install
@"
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
"@ | Set-Content .env.local
npm run dev
```

常用命令：

```powershell
cd frontend
npm run lint
npm run build
```

## 常用配置

配置由 `app/core/settings.py` 定义，默认从项目根目录 `.env` 加载。常用项包括：

- `APP_ENV` / `APP_HOST` / `APP_PORT`
- `DATABASE_URL`
- `DATA_DIR` / `UPLOAD_DIR` / `EXPORT_DIR`
- `MAX_UPLOAD_MB`
- `ENABLE_STREAMING_PARSE`
- `MAX_THREAD_WORKERS` / `MAX_PROCESS_WORKERS`
- `SYSTEM_MEMORY_SOFT_LIMIT_PERCENT`
- `SYSTEM_CPU_SOFT_LIMIT_PERCENT`
- `API_PREFIX`
- `CORS_ALLOW_ORIGINS`
- `LLM_ENABLED` 及相关 LLM 参数

## 默认管理员

默认管理员账号来自 `.env` 配置：

- `AUTH_DEFAULT_ADMIN_USERNAME`
- `AUTH_DEFAULT_ADMIN_PASSWORD`

建议在首次执行 `scripts.init_db` 之前就改成你自己的值，不要在生产环境沿用示例默认值。

## 测试与验证

后端测试：

```powershell
pytest -q
```

如果只做快速验证，可优先运行：

```powershell
pytest tests/test_api_basic.py -q
pytest tests/test_auth_service.py -q
pytest tests/test_streaming_aggregation.py -q
pytest tests/test_task_state_cache.py -q
```

前端验证：

```powershell
cd frontend
npm run lint
npm run build
```

## 关键文件

- `app/main.py`：FastAPI 入口
- `app/api/routes.py`：主要业务接口
- `app/api/auth_routes.py`：认证与用户相关接口
- `app/db/session.py`：数据库会话与 SQLite 相关配置
- `app/services/ingestion_service.py`：任务处理主流程
- `app/services/streaming_aggregation.py`：流式聚合
- `app/services/query_service.py`：查询与结果读取
- `app/services/task_state_cache.py`：任务状态缓存与进度
- `ui/streamlit_app.py`：Streamlit 界面
- `frontend/`：Next.js Web 前端

## 仓库说明

- 主分支当前以源码维护为主
- 安装包、打包器和一键启动产物不作为本仓库主线同步目标
- 大体积真实日志建议放在本地运行目录或对象存储中，不建议直接进入源码历史

