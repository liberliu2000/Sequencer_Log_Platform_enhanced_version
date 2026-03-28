# Sequencer Log Platform

面向测序仪多源日志的整理、关联分析、异常诊断与反馈沉淀平台。项目当前以 `FastAPI + Streamlit + SQLite` 为核心，支持批量上传日志文件或压缩包，完成统一事件流构建、Cycle/Step 耗时分析、错误聚类、参数趋势分析、LLM 诊断、主动学习与结果导出。

## 功能概览

- 批量上传单文件、多文件和压缩包，支持异步排队处理
- 解析多类日志：`workflow`、`service`、`error`、`runerror`、`metrics csv`
- 将多源日志标准化为统一事件流，并做跨文件关联
- 支持 Cycle 推断、Step 配对、错误聚类、参数趋势和时间轴分析
- 提供历史任务中心、原始文件预览、配置管理和导出页面
- 内置 LLM 诊断链路，可结合上下文、历史案例和源码片段输出结构化结论
- 支持未知日志收集、反馈记录、规则建议审核和解决方案知识库
- 针对大批量文件提供“预扫描线程池 + 解析进程池 + 主进程聚合写库”的分阶段并行流水线

## 技术栈

- 后端：FastAPI、SQLAlchemy、Pydantic
- 前端：Streamlit、Plotly、Pandas
- 存储：SQLite
- 解析与导出：PyYAML、OpenPyXL、ReportLab、Py7zr
- 测试：Pytest

## 当前目录

```text
sequencer_log_platform_V43/
├─ app/                    # API、解析器、服务层、数据库模型与核心逻辑
├─ ui/                     # Streamlit 界面
├─ config/                 # 阈值、解析规则、错误规则、Prompt 模板
├─ scripts/                # 启动、初始化、规则学习、版本同步脚本
├─ tests/                  # 单元测试与接口/流程测试
├─ docs/                   # 补充文档
├─ data/                   # SQLite、上传文件、导出文件、缓存与运行数据
├─ Dockerfile
├─ docker-compose.yml
├─ requirements.txt
├─ .env.example
└─ VERSION
```

## 主要模块

- `app/main.py`：FastAPI 应用入口
- `app/api/routes.py`：主要 API 路由
- `app/parsers/`：日志解析器注册与实现
- `app/services/ingestion_service.py`：任务接入与处理编排
- `app/services/pipeline_parallel.py`：分阶段并行流水线定义
- `app/services/query_service.py`：任务结果查询
- `app/services/llm_service.py`：LLM 诊断
- `app/services/solution_repository.py`：解决方案知识库
- `ui/streamlit_app.py`：Streamlit 页面入口

## 快速开始

### 1. 创建虚拟环境

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Linux / macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. 初始化配置

```bash
cp .env.example .env
```

Windows:

```powershell
Copy-Item .env.example .env
```

### 4. 初始化数据库

```bash
python -m scripts.init_db
```

### 5. 启动 API 和 UI

分别启动：

```bash
python -m scripts.run_api
python -m scripts.run_ui
```

启动后访问：

- FastAPI 文档：`http://127.0.0.1:8000/docs`
- Streamlit 页面：`http://127.0.0.1:8501`

Windows 下也可以直接运行：

- `scripts/start_local.ps1`
- `scripts/start_local.bat`

## Docker 启动

```bash
docker compose up --build
```

默认映射端口：

- `8000`：FastAPI
- `8501`：Streamlit

并挂载：

- `./data -> /workspace/data`
- `./config -> /workspace/config`

## 配置说明

项目使用 `.env` + `config/*.yaml` 双层配置。

### 常用 `.env` 项

基础运行：

```env
APP_ENV=dev
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
DATABASE_URL=sqlite:///./data/sequencer_log_platform.db
API_PREFIX=/api/v1
```

并行处理：

```env
ENABLE_PARALLEL_PARSE=true
ENABLE_THREADED_PRESCAN=true
ENABLE_MULTIPROCESS_PARSE=true
ENABLE_STAGED_PARALLEL_PIPELINE=true
MAX_PARALLEL_CPU_CORES=4
PRESCAN_THREAD_WORKERS=8
PARSE_BATCH_SIZE=16
QUEUE_DISPATCH_WORKERS=2
SQLITE_WRITE_STRATEGY=main_process_only
```

LLM 诊断：

```env
LLM_ENABLED=false
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_API_KEY=
LLM_MODEL=ep-xxx
LLM_TIMEOUT_SECONDS=45
LLM_CONTEXT_MAX_TOKEN_BUDGET=2200
```

### YAML 配置文件

- `config/thresholds.yaml`：阈值和上下文预算
- `config/parser_rules.yaml`：时间格式、Cycle/Chip 提取规则、主动学习配置
- `config/error_rules.yaml`：错误家族归类规则
- `config/prompt_templates.yaml`：LLM Prompt 模板与启用版本

## 并行流水线

当前并行处理方案由 [`app/services/pipeline_parallel.py`](app/services/pipeline_parallel.py) 定义，阶段如下：

1. `discover`
   负责输入发现、去重和压缩包展开，串行执行
2. `prescan`
   负责编码识别和 parser 预判，线程池执行
3. `parse_normalize`
   负责单文件解析与标准化事件生成，进程池执行
4. `aggregate`
   负责跨文件关联、聚合分析和 SQLite 写入，主进程串行执行

这样做的目标是提升吞吐，同时避免多进程直接并发写 SQLite 导致锁冲突和结果不一致。

## UI 页面

`ui/streamlit_app.py` 当前包含以下主要页面：

- 首页 / 仪表盘
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
- 导出

## API 能力

主要接口集中在 `app/api/routes.py`，包括：

- 健康检查：`GET /api/v1/health`
- 上传任务：`POST /api/v1/tasks/upload`
- 任务列表与状态：`GET /api/v1/tasks`、`GET /api/v1/tasks/{task_uuid}/status`
- 仪表盘与事件查询：`/dashboard`、`/events`、`/cycles`、`/steps`
- 时间轴、参数、错误分析：`/movement-timeline`、`/parameter-series/*`、`/errors*`
- LLM 诊断与历史结果：`/errors/{signature}/analyze`、`/llm-results*`
- 原始文件与审计日志：`/files`、`/files/preview`、`/audit-logs`
- 配置管理：`/config*`
- 主动学习：`/active-learning/*`
- 解决方案知识库与审核：`/solution-repository/*`、`/solution-reviews*`
- 导出：`/export/*`

## 脚本说明

- `python -m scripts.init_db`
  初始化或迁移 SQLite 表结构
- `python -m scripts.run_api`
  启动 FastAPI
- `python -m scripts.run_ui`
  启动 Streamlit
- `python -m scripts.learn_parser_rules --mode auto`
  基于未知日志池和反馈池生成规则建议
- `python -m scripts.learn_parser_rules --write`
  将规则建议写入配置指定目录
- `python -m scripts.release_sync --patch`
  自动更新 `VERSION`、创建 release commit/tag 并推送

补充说明见 [docs/release_sync.md](docs/release_sync.md)。

## 数据目录说明

运行过程中会在 `data/` 下生成这些内容：

- `data/sequencer_log_platform.db`：SQLite 数据库
- `data/uploads/`：上传后的原始文件
- `data/exports/`：导出文件
- `data/runtime_logs/`：运行日志
- `data/intermediate_cache/`：并行解析阶段的中间 JSONL
- `data/tmp/`：临时目录
- `data/active_learning/`：未知日志池、反馈记录、规则建议与审核数据
- `data/performance/`：性能摘要

## 测试

运行全部测试：

```bash
pytest
```

当前仓库中已经包含的测试覆盖方向包括：

- 时间解析
- 解析器与提取器
- 配对与错误检测
- API 基础流程
- 规则同步与解决方案工作流

## 开发扩展

### 新增解析器

1. 在 `app/parsers/` 下新增 parser
2. 在 `app/parsers/registry.py` 中注册
3. 保持解析器职责聚焦在“单文件解析”
4. 跨文件推断、聚类和写库继续交由聚合阶段处理

### 主动学习与规则建议

当前项目已经支持：

- 未知日志落池
- 人工反馈记录
- 基于聚类与反馈生成规则建议
- LLM 辅助生成 review-only 建议
- 审核后人工合并到规则配置

建议不要让脚本直接覆盖生产规则，而是走审核流。

## 常见问题

### `database is locked`

- 确认没有多套进程同时写同一个 SQLite
- 不要同时启动多套 API 指向同一个数据库
- 保持 `SQLITE_WRITE_STRATEGY=main_process_only`

### `.7z` 无法处理

确认已安装：

```bash
python -m pip install py7zr
```

### Excel 或 PDF 导出失败

确认已安装：

```bash
python -m pip install openpyxl reportlab
```

### Windows 下多进程行为异常

- 优先通过 `python -m scripts.run_api` 启动
- 避免在交互式环境里直接拼装进程池
- 保持 worker 函数位于可导入模块中

## 版本与发布

- 当前版本号保存在根目录 `VERSION`
- 发布脚本：`scripts/release_sync.py`
- 发布说明文档：[`docs/release_sync.md`](docs/release_sync.md)

## 许可与使用

仓库内未看到单独的许可证文件。若要对外分发或商用，建议先补充明确的 License 与使用边界说明。
