# Sequencer Log Platform Enhanced Version

## 全链路防崩优化与实时进度面板（2026-04-02）

本次更新在不改变任何最终输出结果、数据精度、图表内容和业务逻辑的前提下，补齐了“流式后处理与聚合”以及查询/导出链路的低内存优化，并在仪表盘新增了实时任务进度面板。

### 后端优化

- `app/services/streaming_aggregation.py`
  - 流式后处理完成后，直接把完整 `ParameterResult` 批量落库到新表 `parameter_results`，后续查询、导出、绘图不再重复扫描全量事件。
  - 资源守卫从“仅内存”扩展为“CPU + 内存”联合降级，达到阈值时自动缩小批量大小、触发 `gc.collect()` 并短暂让出 CPU。
  - 保留原有 `step_summaries`、`error_clusters` 和仪表盘统计口径，最终结果与优化前完全一致。

- `app/services/query_service.py`
  - `get_parameter_results()` 优先读取轻量结果表；旧任务若还没有结果表数据，则使用数据库顺序扫描 + 增量聚合流式回填一次，避免再把 `normalized_events` 全量反序列化进内存。
  - `preview_task_file()` 改为只读取头部字节做二进制判断，并按行流式预览文本，避免大日志整文件读入。

- `app/services/export_service.py`
  - `export_events_csv()` 改为分页流式写 CSV，避免导出时一次性构造超大列表。

- `app/services/system_runtime_service.py`
  - 新增 CPU 软阈值 `system_cpu_soft_limit_percent`，调度守卫同时考虑 CPU 和内存压力。
  - 新增 `adaptive_cpu_allocation()`，任务启动前会根据系统负载自动降低并发核数，适配低核轻量服务器。

- `app/services/ingestion_service.py`
  - 任务开始时会记录自适应 CPU 分配结果，性能摘要中会保留 `runtime_allocation`、`progress_history` 和最终 `status_snapshot`。
  - 成功 / 失败都会把进度历史持久化到 `data/performance/<task_uuid>.json`，任务完成后仍可在仪表盘回看历史。

- `app/services/task_state_cache.py`
  - 状态缓存新增 `filename`、`total_events`、`total_errors`、`estimated_remaining_seconds`、`estimated_finish_at`、`progress_history`、`runtime_snapshot`。
  - ETA 基于最近进度斜率动态估算，并保留轻量历史缓冲，避免常驻大对象。

### 仪表盘新增能力

- `ui/streamlit_app.py`
  - 仪表盘页新增“实时文件处理进度”卡片，展示当前文件 / 任务名、当前阶段、`st.progress`、已用时间、预计剩余时间、预计结束时间、状态和最近处理历史。
  - `/tasks/{task_uuid}/status` 改为实时请求，不走 15 秒缓存；处理中的任务使用局部自动刷新，不影响原有布局。

### 兼容性与验证

- 新增轻量结果表：`parameter_results`
- 旧任务首次查询参数结果时会自动流式回填，不需要前端改动
- 全量测试已通过：`64 passed`

## 主进程汇总解析结果防崩修复（2026-04-02）

- `app/services/streaming_aggregation.py`
  - 将“主进程汇总解析结果”改为流式落库与流式聚合，避免一次性把所有解析结果装入内存
  - 采用“两遍有序扫描”：第一遍构建 cycle 推断上下文，第二遍逐条完成 cycle 推断、错误归一化、step 聚合、参数统计和错误簇统计
  - 中间 JSONL 文件在合并完成后立即删除，减少磁盘与文件句柄压力
- `app/services/ingestion_service.py`
  - 主任务处理流程已切换为流式汇总协调器，原有接口、前端展示和任务状态回传保持不变
  - 事件更新、步骤汇总和错误簇写入全部改为主进程分批提交，降低 SQLite 峰值压力
- 防崩与降级策略
  - 引入内存守卫：监控系统内存占用率、可用内存与进程 RSS
  - 达到软阈值时自动缩小批大小、触发 `gc.collect()` 并短暂让出 CPU，降低 OOM 与主进程卡死概率
  - 聚合阶段保持单主进程序列化执行，避免低核服务器资源争抢
- 一致性验证
  - 复用现有 cycle 推断、错误归一化、step 配对、参数规则与错误簇规则，保证最终结果口径一致
  - 新增 `tests/test_streaming_aggregation.py`，对比旧全量逻辑与新流式逻辑的事件、步骤汇总和错误簇结果完全一致

基于 `FastAPI + Streamlit + SQLite + SQLAlchemy + Pydantic` 的序列仪日志分析与方案沉淀平台。

项目面向多源日志整理、错误分析、LLM 诊断、主动学习、方案库管理、注册审核和权限控制，当前仓库已经支持：

- 日志任务上传、解析、任务队列与状态跟踪
- 错误聚类、趋势分析、时间轴与参数趋势分析
- LLM 诊断、相似案例检索、审核流
- 主动学习、未知日志池、规则建议审核
- 全局方案库、任务簇、多维索引检索、导出
- 用户注册、邮箱验证、管理员审核、角色权限

## 技术栈

- 后端：`FastAPI`、`SQLAlchemy`、`Pydantic`
- 前端：`Streamlit`、`Plotly`、`Pandas`
- 数据库：`SQLite`
- 配置：`.env` + `YAML`
- 测试：`pytest`

## 当前核心能力

### 1. 日志任务分析

- 批量上传日志文件
- 统一事件流与错误聚类
- Cycle / Step / 时间轴 / 参数趋势分析
- 原始文件预览
- 多格式导出

### 2. 全局方案库

- 方案主表独立于任务
- 支持任务关联、模块关联、任务簇关联、标签关联、message 关键词关联
- 支持方案提交、审核、复用、导出
- 支持按错误码、模块、错误名、关键词、任务簇、提交人、审核状态、时间检索
- SQLite 下启用常规索引，并支持 FTS5 全文索引

### 3. 用户与权限

- 同一登录页支持 `admin` / `reviewer` / `submitter`
- 密码哈希存储
- 登录失败限制与锁定
- 基于会话 token 的轻量鉴权
- 后端强校验，前端按角色展示页面

### 4. 注册审核

- 用户先填写注册信息并发送邮箱验证码
- 只有验证码验证成功后，才允许正式提交注册申请
- 注册申请提交成功后进入管理员审批
- 用户状态包括：
  - `pending_verification`
  - `pending_admin_approval`
  - `approved`
  - `rejected`
  - `disabled`
- 支持验证码过期、重发和频率限制

### 5. 错误码生成

- 系统自动生成错误码
- 按模块前缀 + 自增流水号格式生成
- 示例：`MC0001`
- 当前默认模块前缀：
  - `OP` optics
  - `FL` fluidics
  - `MC` motion_control
  - `SC` scheduler
  - `AL` algorithm
  - `UI` ui
  - `DB` database
  - `OT` other

## 默认管理员

首次初始化数据库时会自动创建默认管理员：

- `username = Yanbo`
- `password = MGItech2026`

说明：

- 数据库存储的是哈希值，不会明文保存密码
- 默认管理员首次登录后会收到“建议修改密码”的提示
- 可通过 `.env` 覆盖默认管理员用户名和密码

## 目录结构

```text
app/                    FastAPI 后端、服务层、模型、数据库与核心逻辑
ui/                     Streamlit 前端
config/                 YAML 配置
scripts/                启动、初始化、辅助脚本
tests/                  测试
data/                   SQLite、上传文件、导出文件与运行时数据
README.md               项目说明
.env.example            环境变量示例
requirements.txt        Python 依赖
```

## 关键文件

- `app/main.py`：FastAPI 入口，包含鉴权中间件
- `app/api/routes.py`：原有主业务接口
- `app/api/auth_routes.py`：认证、注册、用户管理接口
- `app/api/solution_meta_routes.py`：模块与任务簇管理接口
- `app/models/db_models.py`：数据库模型
- `app/services/auth_service.py`：用户、登录、注册审核、默认管理员逻辑
- `app/services/solution_repository.py`：全局方案库与索引逻辑
- `app/services/solution_review_service.py`：方案审核流
- `app/services/error_code_service.py`：错误码分配服务
- `ui/streamlit_app.py`：登录页、主系统页、方案库页、管理员页
- `scripts/init_db.py`：数据库初始化与默认数据导入

## 环境准备

建议 Python 版本：`3.12`

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## 数据库初始化

```powershell
python -m scripts.init_db
```

该步骤会自动完成：

- 建表
- SQLite 轻量迁移
- 初始化系统模块前缀
- 初始化系统任务簇
- 初始化默认管理员

## 启动方式

### 启动 API

```powershell
python -m scripts.run_api
```

默认地址：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`

### 启动 Web UI

```powershell
python -m scripts.run_ui
```

默认地址：

- `http://127.0.0.1:8501`

### 一键本地启动

```powershell
scripts\start_local.ps1
```

## 配置说明

主要环境变量见 [`.env.example`](/d:/VScode1/MyProjects/Sequencer_Log_Platform_enhanced_version-master/Sequencer_Log_Platform_enhanced_version-master/.env.example)。

重点配置：

- 基础运行：
  - `APP_ENV`
  - `APP_HOST`
  - `APP_PORT`
  - `DEBUG`
- 数据目录：
  - `DATABASE_URL`
  - `DATA_DIR`
  - `UPLOAD_DIR`
  - `EXPORT_DIR`
- LLM：
  - `LLM_ENABLED`
  - `LLM_BASE_URL`
  - `LLM_API_KEY`
  - `LLM_MODEL`
- 鉴权：
  - `AUTH_SESSION_HOURS`
  - `AUTH_MAX_FAILED_LOGINS`
  - `AUTH_LOCK_MINUTES`
  - `AUTH_DEFAULT_ADMIN_USERNAME`
  - `AUTH_DEFAULT_ADMIN_PASSWORD`
- 邮件发送：
  - `MAIL_DELIVERY_MODE`
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD`
  - `SMTP_FROM_EMAIL`

本地调试建议：

- `MAIL_DELIVERY_MODE=console`

生产或联调邮件验证码时：

- `MAIL_DELIVERY_MODE=smtp`

## 主要接口

### 认证与用户

- `POST /api/v1/auth/register/request-code`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/register/resend-code`
- `POST /api/v1/auth/register/verify-email`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users/{user_id}/status`
- `POST /api/v1/admin/users/{user_id}/roles`

### 方案库

- `GET /api/v1/solution-repository/config`
- `GET /api/v1/solution-repository/records`
- `POST /api/v1/solution-repository/records`
- `PUT /api/v1/solution-repository/records/{record_id}`
- `GET /api/v1/solution-repository/export`
- `GET /api/v1/solution-repository/modules`
- `POST /api/v1/solution-repository/modules`
- `GET /api/v1/solution-repository/task-clusters`
- `POST /api/v1/solution-repository/task-clusters`
- `POST /api/v1/solution-repository/task-clusters/{cluster_id}/review`
- `GET /api/v1/solution-reviews`
- `POST /api/v1/solution-reviews`
- `POST /api/v1/solution-reviews/{review_id}/manual-review`

### 日志分析主链路

- `GET /api/v1/health`
- `POST /api/v1/tasks/upload`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_uuid}/status`
- `GET /api/v1/tasks/{task_uuid}/dashboard`
- `GET /api/v1/tasks/{task_uuid}/events`
- `GET /api/v1/tasks/{task_uuid}/errors`
- `POST /api/v1/tasks/{task_uuid}/errors/{signature}/analyze`

## Streamlit 页面

当前前端入口仍为单文件 `ui/streamlit_app.py`，主要页面包括：

- 独立登录页
- 首页 / 仪表盘
- 历史项目中心
- 文件上传
- 统一事件流
- 错误分析
- LLM 诊断
- 方案库中心
- 用户管理
- 配置页面
- 导出

页面显示规则：

- 未登录时只能看到登录/注册/邮箱验证界面
- `submitter` 可进入主功能页和方案提交/查询页
- `reviewer` 额外可进行方案审核、任务簇审核、模块维护
- `admin` 额外拥有用户管理页

## 测试

运行全量测试：

```powershell
pytest -q
```

当前仓库已验证通过：

- `59 passed`

## 后端性能优化（2026-04）

本次后端优化严格遵循以下原则：

- 不改变接口、最终统计结果、图表数据内容、数据精度与前端展示质量
- 不修改 `.env`、部署环境变量或前端调用方式
- 优先适配低 CPU 核数、小内存服务器，降低峰值内存和 SQLite 争用

本次已落地的优化点：

- `app/services/ingestion_service.py`
  - 解析后事件入库改为分批映射插入，避免一次性构造大量 ORM 对象
  - `StepSummary` / `ErrorCluster` 同样改为分批写库，降低峰值内存
  - 错误簇首末时间改为单次遍历统计，避免 Top N 错误簇逐个全表扫描
  - 在大列表完成阶段性用途后主动释放引用并触发 `gc.collect()`
- `app/repositories/task_repository.py`
  - `save_events` / `save_step_summaries` / `replace_error_clusters` 改为批量 `insert`
  - 任务创建、进度更新、完成审计合并事务，减少 SQLite 双重提交
- `app/services/query_service.py`
  - 列表查询改为按需列投影，避免把整行 ORM 对象全部加载进内存
  - `cycle summary` 与 `substep-cycle` 聚合下推到 SQL，减少 Python 端全量聚合
  - 时间轴错误点、错误趋势、错误簇查询改为轻量字段读取
  - `operational metrics`、温控校验改为单次遍历分类，减少重复扫描
- `app/services/cycle_service.py`
  - `summarize_cycles` 改为单次聚合，不再为每个 cycle 保存整组中间列表
  - 成对匹配队列改为 `deque`，将 `pop(0)` 的线性开销降为常数开销
  - `row_scan_metric` 聚合仅保留求均值所需统计量和前 20 条样本，减少中间对象
- `app/detectors/error_detection.py`
  - 错误标注在传入 `list` 时原地更新，避免额外复制事件列表
- `app/services/export_service.py`
  - 报表构建改为复用同一个 `QueryService` 顺序生成，减少低核机器上的多线程争抢与重复缓存扫描

低资源服务器收益说明：

- 峰值内存下降：主要来自“批量 ORM 对象构造”改为“分批映射写入”
- CPU 下降：主要来自 SQL 聚合下推、单次遍历统计、`deque` 配对
- I/O 压力下降：主要来自 SQLite 提交次数减少与导出阶段并发收敛

## 同步建议

为了保持 GitHub 在线分支、本地代码和服务器代码一致，建议使用以下流程：

```powershell
git checkout <branch>
git pull --ff-only origin <branch>
pytest -q
git push origin <branch>
```

服务器端仅同步代码，不修改环境配置：

```bash
ssh ubuntu@<server>
cd <project-dir>
git fetch --all
git checkout <branch>
git pull --ff-only origin <branch>
```

说明：

- 保持服务器 `.env` 原样，不在服务器端修改环境变量配置
- 先在本地跑 `pytest -q`，确认通过后再推送和拉取
- 若服务器使用 Docker 或 systemd，请在拉取后按现有部署方式重启服务，不改运行参数

## 安全说明

- 密码仅以哈希形式保存
- 登录失败会触发锁定策略
- 验证码有有效期、重发间隔和每日次数限制
- 后端接口按角色强制鉴权
- 导出接口需要登录 token

## 后续建议

- 如果需要生产化部署，建议把 SQLite 升级到 PostgreSQL
- 如果需要更严格的下载安全，可把当前 `access_token` 下载透传改成短时签名下载
- 如果需要邮件联调，请先配置 SMTP 账号并把 `MAIL_DELIVERY_MODE` 改为 `smtp`
