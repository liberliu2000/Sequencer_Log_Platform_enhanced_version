# Sequencer Log Platform Enhanced Version

基于 `FastAPI + Streamlit + Next.js + SQLite` 的测序日志分析平台。

当前仓库维护的是源码版本，适合继续开发、联调、部署与测试。本次版本在不重写现有系统的前提下，对多边日志解析、时间轴绘图、参数趋势分析、公告编辑记录、历史任务中心等能力做了增量增强。

## 项目概览

平台面向多来源测序日志的采集、解析、结构化、聚合与问题定位，核心目标包括：

- 支持大体积日志与压缩包上传
- 将多种日志格式统一为结构化事件流
- 提供时间轴、错误分析、参数趋势、Cycle 分析等可视化页面
- 提供任务状态、进度、性能快照、文件预览与导出
- 提供用户、权限、公告、方案库与审核流程

## 本次增量优化

### 1. 多边日志按边独立统计 Cycle

- 对多边运行日志按 `side / edge / board / chip` 的真实归属独立识别
- 每一边拥有独立的 cycle 序列，不再把不同边的事件混在一起统一编号
- Cycle 划分严格基于日志中的真实事件边界、真实步骤边界和真实时间顺序
- 对日志不完整的边采用保守推断策略；无法安全判断时保留不确定状态，不虚构 cycle

### 2. 甘特图改为按边分组返回与展示

- 后端时间轴接口不再只返回一个混合列表，而是按边输出 `by_side`
- 前端按边分别绘制时间轴/甘特图，每个边单独一张图
- 支持查看整机全部边的图表列表，也支持按单边筛选
- 对边归属不确定的时间轴，在每个单边图中复制展示并高亮显示

### 3. 时间轴默认使用日志原始时间

- 时间轴、事件流、参数趋势优先使用日志中的原始时间字段
- 不再为了展示而覆盖原始时间、强制归零或生成伪时间
- 若业务需要仍可保留相对时间字段，但默认图表横轴使用原始时间语义
- 兼容毫秒、微秒和多种时间文本格式，并按真实时间顺序排序

### 4. 参数趋势支持横轴模式切换

- 参数趋势分析页面支持两种横轴模式：
  - 按 cycle
  - 按时间
- 横轴模式由前端切换，但排序与数据组织由后端接口直接支持
- 按 cycle 模式下遵守“各边独立 cycle”体系
- 按时间模式下直接使用原始日志时间

### 5. 公告编辑审计

- 公告新增 `edit_history`
- 每次编辑记录编辑人、编辑时间和关键变更快照
- 页面可查看最新编辑元信息

### 6. 历史项目中心增强

- 历史任务列表展示上传人、文件大小
- 支持下载该任务原始上传文件
- 单文件直接下载，多文件目录自动打包为 zip 下载

## 当前能力

### 日志处理与分析

- 批量上传日志文件或压缩包
- 流式解析与聚合，降低大任务内存峰值
- Cycle / Step / 时间轴 / 参数趋势 / 错误分布分析
- 原始日志预览与导出
- `parameter_results` 轻量结果表，减少重复全量扫描

### 运行时与性能

- 任务实时进度、阶段、ETA、预计完成时间
- SQLite 锁竞争缓解，减少瞬时写入失败
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

## 关键接口变更说明

### 时间轴接口

`GET /api/v1/tasks/{task_uuid}/movement-timeline`

返回结构从“仅一组混合行”扩展为：

```json
{
  "rows": [],
  "side_order": ["A1", "A2", "B1"],
  "by_side": [
    {
      "side_scope": "A1",
      "side_label": "A1",
      "rows": [],
      "uncertain_count": 2
    }
  ],
  "unassigned_side_rows": []
}
```

说明：

- `rows`：完整平铺结果，兼容已有处理逻辑
- `by_side`：前端单边甘特图直接使用
- `unassigned_side_rows`：归属不确定的原始时间轴

### 时间轴错误点接口

`GET /api/v1/tasks/{task_uuid}/movement-timeline/errors`

返回结构与时间轴主接口保持一致，顶层字段为 `points` 与 `by_side`。

### 参数趋势接口

以下接口新增查询参数 `axis_mode`，支持 `cycle` / `time`：

- `GET /api/v1/tasks/{task_uuid}/parameter-series/{parameter_name}`
- `GET /api/v1/tasks/{task_uuid}/substep-cycle-series`
- `GET /api/v1/tasks/{task_uuid}/row-scan-metric-series`

返回结果统一补充：

- `x_axis_type`
- `x_axis_value`
- `x_axis_label`
- `x_axis_sort_value`
- `time_epoch_ms`
- `series_name`

### 任务列表 / 状态接口

以下接口新增任务元信息：

- `uploaded_by`
- `total_size_bytes`
- `total_size_text`

并新增下载接口：

- `GET /api/v1/tasks/{task_uuid}/download`

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

## Docker 一键启动

仓库现在提供独立的 Docker 一键启动编排，包含：

- FastAPI API：`8000`
- Next.js Web：`3000`
- Streamlit 运维界面：`8501`

推荐命令：

Linux / macOS：

```bash
cp .env.docker.example .env.docker
./scripts/docker_up.sh
```

Windows PowerShell：

```powershell
Copy-Item .env.docker.example .env.docker
powershell -ExecutionPolicy Bypass -File .\scripts\docker_up.ps1
```

说明：

- `.env.docker` 不存在时，启动脚本会自动从 `.env.docker.example` 生成
- 如果前端不是在当前机器本地浏览器打开，请把 `NEXT_PUBLIC_API_BASE_URL` 改成服务器真实地址，例如 `http://172.19.56.195:8000/api/v1`
- 一键编排文件是 `docker-compose.oneclick.yml`
- API 容器与 Streamlit 容器共享 `./data` 与 `./config`，数据会落在宿主机目录

如果需要导出一套适合直接拷贝到服务器目录的精简部署包，可执行：

```powershell
python .\scripts\export_docker_bundle.py D:\mnt\data\LogPlatform --public-api-base-url http://127.0.0.1:8000/api/v1
```

如果服务器目录已经是完整项目，也可以直接在服务器项目根目录执行一键启动：

```bash
chmod +x ./scripts/docker_up.sh
./scripts/docker_up.sh
```

说明：

- 脚本会自动创建 `data/uploads`、`data/exports`、`data/runtime_logs`、`data/intermediate_cache`、`data/tmp`
- 优先调用 `docker compose`
- 若服务器只有 `docker-compose` v1，会自动注入 `PYTHONNOUSERSITE=1`，规避用户目录 Python 包污染导致的启动失败

## 服务器迁移压缩包

如果需要把“代码 + 配置 + data 数据目录”整体打包，方便通过移动硬盘迁移到另一台服务器，可在 Linux 服务器项目根目录执行：

```bash
chmod +x ./scripts/create_migration_bundle.sh
./scripts/create_migration_bundle.sh
```

也可以指定输出目录：

```bash
./scripts/create_migration_bundle.sh /mnt/data/migration_bundles
```

脚本会生成：

- `sequencer-log-platform_migration_<hostname>_<timestamp>.tar.gz`
- 对应的 `sha256` 校验文件

打包内容：

- 项目代码
- `.env`、`.env.docker`、Compose 文件与 Dockerfile
- `config/`
- `data/` 下的数据库、上传文件、导出文件和运行日志

默认排除：

- `.git`
- `.venv` / `venv`
- `frontend/node_modules`
- `frontend/.next`
- `.deploy_backups`
- `.migration_bundles`

迁移到新服务器后的基本步骤：

```bash
mkdir -p /mnt/data/LogPlatform
tar -xzf sequencer-log-platform_migration_<hostname>_<timestamp>.tar.gz -C /mnt/data/LogPlatform
cd /mnt/data/LogPlatform
./scripts/docker_up.sh
```

## 常用配置

配置由 `app/core/settings.py` 定义，默认从项目根目录 `.env` 加载。常用项目包括：

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

建议在首次执行 `scripts.init_db` 之前就改成自己的值，不要在生产环境沿用示例默认值。

## 测试与验证

后端测试：

```powershell
pytest -q
```

若做快速验证，建议优先运行：

```powershell
pytest tests/test_api_basic.py -q
pytest tests/test_parameter_result_query.py -q
pytest tests/test_streaming_aggregation.py -q
```

前端验证：

```powershell
cd frontend
npm exec -- tsc --noEmit
```

## 关键文件

- `app/main.py`：FastAPI 入口
- `app/api/routes.py`：主要业务接口
- `app/api/auth_routes.py`：认证与用户相关接口
- `app/db/session.py`：数据库会话与 SQLite 配置
- `app/services/ingestion_service.py`：任务处理主流程
- `app/services/streaming_aggregation.py`：流式聚合、cycle 推断、多边归属
- `app/services/query_service.py`：结果查询与图表数据组织
- `app/services/task_state_cache.py`：任务状态缓存与进度
- `ui/streamlit_app.py`：Streamlit 界面
- `frontend/components/log-platform-console.tsx`：Next.js 主控制台

## 仓库说明

- 当前主分支以源码维护为主
- 安装包、打包器和一键启动产物不作为本仓库主线同步目标
- 大体积真实日志建议放在本地运行目录或对象存储，不建议直接进入源码历史
