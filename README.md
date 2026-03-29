# Sequencer Log Platform

面向测序仪多源日志的整理、关联分析、异常诊断与反馈沉淀平台。

当前项目采用 `FastAPI + Streamlit + SQLite` 架构，默认提供：

- `FastAPI` API 服务，用于日志上传、任务管理、数据查询、导出与配置维护
- `Streamlit` Web 界面，用于分析结果查看、规则审核、LLM 诊断与日常运维
- `SQLite` 本地数据存储，用于任务、事件、异常聚类、方案库与反馈记录管理

## 项目目标

本项目用于把分散的日志、CSV、运行记录和诊断信息统一接入到一个分析平台中，帮助使用者完成：

- 批量上传日志并发起异步分析任务
- 统一事件流整理与按任务追踪
- Cycle、步骤、参数、错误趋势等维度的分析
- 错误聚类、异常家族识别和同类问题归档
- 基于上下文和历史案例的 LLM 诊断
- 主动学习、未知日志聚类、规则建议与人工审核
- 方案库沉淀、复用和导出报表

## 核心功能

### 1. 日志接入与异步处理

- 支持多文件批量上传
- 为每次上传生成独立 `task_uuid`
- 提供任务队列、状态跟踪、进度百分比和阶段信息
- 支持并行解析、预扫描和分阶段流水线处理

### 2. 统一分析视图

- 统一事件流查询
- Cycle 列表与汇总分析
- 步骤耗时分析
- 参数结果与运行指标分析
- 运动时间轴和错误点位展示
- 原始文件预览

### 3. 错误分析与诊断

- 错误聚类和错误趋势统计
- 异常家族规则识别
- 相似案例检索
- 基于上下文的单签名 LLM 诊断
- LLM 历史结果查询与最新结果读取

### 4. 主动学习与知识沉淀

- 未知日志聚类池
- 反馈记录与反馈簇审核
- 规则建议预览与审核
- LLM 辅助规则建议
- 方案库记录维护
- 方案审核流与导出

### 5. 导出与运维

- 导出事件 CSV
- 导出错误分析 CSV
- 导出参数结果 CSV
- 导出 JSON / HTML / Excel / PDF 报告
- 环境变量项在线查看、更新和重置
- 阈值、规则与 Prompt 模板配置查看

## 技术栈

- 后端：`FastAPI`、`SQLAlchemy`、`Pydantic`
- 前端：`Streamlit`、`Plotly`、`Pandas`
- 数据存储：`SQLite`
- 配置：`.env` + `YAML`
- 测试：`pytest`
- 部署：本地脚本 / Docker / Docker Compose

## 运行方式

### 本地快速开始

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

### 启动 Web 界面

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

该脚本会依次：

- 安装依赖
- 初始化数据库
- 分别启动 FastAPI 与 Streamlit

## Docker 运行

### 使用 Docker Compose

```powershell
docker compose up --build
```

默认映射端口：

- `8000` -> FastAPI
- `8501` -> Streamlit

挂载目录：

- `./data:/workspace/data`
- `./config:/workspace/config`

## 配置说明

项目通过 `.env` 控制运行参数，建议从 `.env.example` 复制生成：

```powershell
Copy-Item .env.example .env
```

重点配置项包括：

- 基础运行：`APP_ENV`、`APP_HOST`、`APP_PORT`、`DEBUG`
- 数据目录：`DATABASE_URL`、`DATA_DIR`、`UPLOAD_DIR`、`EXPORT_DIR`
- 上传限制：`MAX_UPLOAD_MB`、`CHUNK_SIZE`
- 并行处理：`MAX_PARALLEL_CPU_CORES`、`MAX_THREAD_WORKERS`、`MAX_PROCESS_WORKERS`
- UI/缓存：`UI_AUTO_REFRESH_SECONDS`、`ENABLE_SERVICE_CACHE`
- LLM：`LLM_ENABLED`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`
- API：`API_PREFIX`、`CORS_ALLOW_ORIGINS`

## API 与页面能力概览

API 前缀默认为：

```text
/api/v1
```

主要接口能力包括：

- `GET /health`：服务健康检查
- `POST /tasks/upload`：上传日志并创建异步任务
- `GET /tasks` / `GET /tasks/{task_uuid}/status`：任务列表与状态
- `GET /tasks/{task_uuid}/dashboard`：任务仪表盘汇总
- `GET /tasks/{task_uuid}/events`：事件流查询
- `GET /tasks/{task_uuid}/cycles` / `steps` / `cycle-summary`：周期与步骤分析
- `GET /tasks/{task_uuid}/errors` / `errors/trend`：错误聚类与趋势
- `POST /tasks/{task_uuid}/errors/{signature}/analyze`：LLM 诊断
- `GET /config` / `PUT /config/thresholds`：配置查看与阈值维护
- `GET /solution-repository/records`：方案库查询
- `GET /tasks/{task_uuid}/export/*`：分析结果导出

Streamlit 页面覆盖的主要场景包括：

- 首页仪表盘
- 历史项目中心
- 文件上传
- 统一事件流
- 耗时分析
- 事件流时间轴
- 错误分析
- 参数趋势分析
- LLM 诊断
- 原始文件预览
- 未知日志待标注池
- 规则建议审核视图
- 配置页面
- 导出页面

## 目录结构

```text
sequencer_log_platform_V43/
├── app/                         # API、服务层、解析器、数据库与核心逻辑
├── ui/                          # Streamlit 前端
├── config/                      # YAML 配置
├── scripts/                     # 启动、初始化、发布与规则学习脚本
├── docs/                        # 补充文档
├── tests/                       # 自动化测试
├── data/                        # SQLite、上传文件、导出文件与运行数据
├── requirements.txt             # Python 依赖
├── Dockerfile                   # Docker 镜像构建
├── docker-compose.yml           # Docker Compose 配置
├── .env.example                 # 环境变量示例
├── VERSION                      # 版本号
└── README.md
```

## 关键模块

- `app/main.py`：FastAPI 应用入口
- `app/api/routes.py`：主要 API 路由
- `app/core/settings.py`：环境变量与运行配置
- `app/services/ingestion_service.py`：日志接入与处理主流程
- `app/services/llm_service.py`：LLM 诊断服务
- `app/services/solution_repository.py`：方案库服务
- `app/services/feedback_service.py`：反馈与主动学习服务
- `ui/streamlit_app.py`：Streamlit 应用入口
- `scripts/init_db.py`：数据库初始化
- `scripts/run_api.py`：本地 API 启动脚本
- `scripts/run_ui.py`：本地 UI 启动脚本
- `scripts/release_sync.py`：版本发布与 Git 同步脚本

## 测试

执行全部测试：

```powershell
pytest tests
```

当前测试覆盖的重点模块包括：

- API 基础可用性
- 日志提取与解析
- 错误检测
- 配对与时间解析
- 方案工作流
- 环境变量服务
- 发布同步脚本
- 设计系统基础逻辑

## 发布与同步

项目包含自动发布脚本：

```powershell
python scripts/release_sync.py --patch
```

该脚本会自动完成：

- 版本号更新
- Git 提交
- Git Tag 创建
- 推送到远程仓库

更多说明见：

- `docs/release_sync.md`

## 当前默认访问地址

- FastAPI 文档：`http://127.0.0.1:8000/docs`
- Streamlit 页面：`http://127.0.0.1:8501`

## 注意事项

- `.env`、数据库文件、上传日志、运行缓存和导出结果不应直接提交到仓库
- 如需开启 LLM 诊断，必须补充有效的 `LLM_API_KEY` 和对应模型配置
- SQLite 适合单机轻量部署；若后续并发规模扩大，可考虑升级数据库方案
