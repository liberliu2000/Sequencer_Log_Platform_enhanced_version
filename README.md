# Sequencer Log Platform

面向测序仪多源异构日志的企业级日志整理、异常参数分析与问题反馈平台。系统用于处理大批量 workflow / service / error / metrics 日志，并通过可配置并行流水线提升吞吐量，同时保持结果一致性、SQLite 写入安全和 UI 层低耦合。

---

## 1. 项目概述

本项目服务于测序仪控制系统、流路、光学、运动、调度、算法与 metrics 联合分析场景，目标是将多源异构日志整理为统一事件流，并进一步输出：

- 跨文件、跨模块统一时间流
- cycle / sub-step / 参数级耗时统计
- 错误归一化、聚类与趋势分析
- LLM 最小必要上下文分析
- 交互式 UI 与多格式报告导出

新版重点引入**分阶段并行处理架构**，专门优化大目录、多文件、压缩包场景下的处理性能与资源利用。

---

## 2. 核心功能

### 2.1 日志接入与解析

- 支持单文件、多文件、压缩包上传
- 支持 zip / tar / gz / tgz / bz2 / 7z
- 自动文件识别、编码检测、解析器路由
- 插件式 Parser Registry

### 2.2 标准化与关联分析

- 标准事件模型 `NormalizedEvent`
- start/end 步骤配对
- cycle 缺失推断
- metrics 文件聚合
- 各 cycle 参数统计

### 2.3 错误分析与 LLM

- 错误归一化与簇聚合
- 错误簇趋势（日 / 周）
- LLM 最小必要上下文压缩
- 429 限流治理、缓存优先、指数退避

### 2.4 UI 与导出

- FastAPI + Streamlit
- 历史任务管理、审计日志、原始文件预览
- CSV / JSON / Excel / PDF 导出
- 参数趋势分析、Substep-Cycle 分面图

### 2.5 主动学习 / 规则迭代

- 未知日志兜底收集：未命中 parser / parser_rules 的日志不会丢弃，而是进入待标注池
- 用户纠错反馈落地：解析修正会保存为可检索的反馈记录与反馈簇
- 规则建议生成：支持本地归纳与可选 LLM 候选建议
- 审核流：未知日志簇、反馈簇、规则建议都只能进入 review-only 状态流，不会自动覆盖生产规则
- LLM 历史诊断：历史诊断结果持久化保存，可在 UI 中重复查看详情

### 2.6 UI 使用逻辑补充

#### 未知日志待标注池

建议按下面顺序使用：

1. 先看出现次数与代表性样本，判断是否为真实新日志类型
2. 打开上下文样本，确认是否只是现有规则漏匹配
3. 对需要处理的未知簇执行“提交审核”
4. 审核通过后，再进入“规则建议审核视图”生成或筛选候选规则

#### 规则建议审核视图

建议按下面顺序使用：

1. 先查看本地统计生成的规则建议
2. 仅在本地建议不足时，再开启 LLM 候选建议
3. LLM 只接收最小必要上下文，不会直接读取整份超大日志
4. 对候选建议执行提交审核 / 批准 / 驳回 / 忽略
5. 审核通过后，由人工将候选项合并到 `parser_rules.yaml` 或对应 parser 代码

#### LLM 诊断页

- 上半部分用于查看当前任务下的过往诊断信息
- 下半部分用于发起新的错误簇诊断
- 若某个错误簇已经诊断过，可先查看历史记录，再决定是否强制重跑
- 当前版本已缩小诊断时的候选上下文范围，优先按错误签名、时间窗、同 component / 同 cycle / 同 chip 定向取样，减少大任务下的超时风险

---

## 3. 新版并行处理架构说明

## 3.1 为什么需要并行改造

旧版在大文件 / 多文件场景下的主要瓶颈：

1. **文件预扫描串行**
   - 编码检测、文件头读取、类型识别逐个执行
   - 对大目录扫描时 I/O 延迟累积明显

2. **单文件解析与标准化串行**
   - 单文件解析、正则提取、标准事件转换全部在主流程顺序执行
   - CPU 密集阶段无法利用多核

3. **中间结果集中在主内存**
   - 多个文件解析结果直接堆在主进程列表中
   - 易形成大对象、增加峰值内存与 GC 压力

4. **SQLite 不适合高并发写**
   - 如果多 worker 直接写库，容易出现锁冲突和结果不一致

5. **跨文件关联阶段依赖强**
   - cycle 推断、错误簇合并、参数统计本质上需要全局视角
   - 不适合盲目并行

---

## 3.2 并行化原则

本项目不是“到处加线程”，而是按任务特征分阶段处理：

| 阶段 | 处理模式 | 选择原因 |
|---|---|---|
| 文件发现与压缩包展开 | 串行 | 需要统一临时目录策略，避免同名覆盖与解压冲突 |
| 文件预扫描 | 多线程 | 编码检测、文件头读取、解析器识别以 I/O 为主 |
| 单文件解析 + 标准化 | 多进程 | 正则匹配、消息抽取、标准事件转换 CPU 占比高 |
| metrics 聚合 | 串行 | 依赖全局事件流和跨文件 cycle 上下文 |
| error 聚类预处理 | 局部并行 + 主进程合并 | 可局部计算，但最终签名聚类需统一汇总 |
| 各 cycle 参数统计 | 串行 | 依赖完整标准事件流 |
| 图表数据预计算 | 串行 | 数据量远小于解析阶段，并发收益有限 |

---

## 3.3 任务 DAG / 阶段依赖

```text
上传任务
  -> 输入发现 / 压缩包展开（串行）
  -> 文件预扫描（线程池）
  -> 单文件解析 + 标准化（进程池）
  -> 主进程读取中间结果 JSONL
  -> 跨文件 cycle 推断（串行）
  -> 错误归一化 / 聚类（串行主合并）
  -> metrics / 参数统计（串行）
  -> 图表基础数据预计算（串行）
  -> 主进程统一写 SQLite
```

必须先完成单文件解析，才能做跨文件 cycle 推断；必须先完成标准化，才能做错误簇归一化和参数统计。本项目显式保留这些顺序依赖，不做盲目并行。

---

## 3.4 并行安全策略

### 共享状态隔离

- 每个 worker 只处理自己的输入文件
- 不共享全局事件列表、全局 DataFrame、全局缓存字典
- worker 输出独立 JSONL 中间文件
- 主进程统一汇总结果并做后续分析

### 文件写入隔离

- 每个 worker 的输出文件使用唯一文件名
- 压缩包展开目录、工作目录、中间结果目录按 `task_id` 隔离
- 避免同名覆盖与并发写损坏

### SQLite 写入策略

- **只允许主进程统一写入 SQLite**
- worker 不直接写数据库
- 避免 SQLite 高并发写锁和事务冲突

### 日志输出策略

- 并发 worker 不直接向共享 stdout 打印大量调试信息
- 关键阶段统一记录到主流程审计日志

---

## 3.5 Worker 输入输出模型

### 预扫描 worker

输入：文件路径
输出：

- path
- file_name
- size_bytes
- suffix
- encoding
- parser_name
- supported
- skip_reason

### 解析 worker

输入：

- path
- output_path
- parser_name_hint

输出：

- output_path
- parser_name
- event_count
- ok
- error
- traceback_text

解析 worker 只负责：

- 读取单文件
- 调用 parser
- 做标准事件转换
- 输出 JSONL 中间结果

不负责：

- SQLite 写入
- 全局 cycle 推断
- 全局错误聚类
- 图表生成

---

## 4. 项目结构

```text
sequencer_log_platform/
├─ app/
│  ├─ api/
│  │  └─ routes.py
│  ├─ core/
│  │  ├─ settings.py
│  │  ├─ logging_config.py
│  │  └─ bootstrap.py
│  ├─ db/
│  │  ├─ base.py
│  │  ├─ session.py
│  │  └─ migrations.py
│  ├─ models/
│  │  └─ db_models.py
│  ├─ schemas/
│  │  └─ common.py
│  ├─ parsers/
│  │  ├─ base.py
│  │  ├─ registry.py
│  │  ├─ csv_workflow_parser.py
│  │  ├─ service_log_parser.py
│  │  ├─ error_log_parser.py
│  │  ├─ runerror_parser.py
│  │  └─ metrics_csv_parser.py
│  ├─ normalizers/
│  │  └─ event_normalizer.py
│  ├─ correlators/
│  │  └─ pairing.py
│  ├─ detectors/
│  │  └─ error_detection.py
│  ├─ repositories/
│  │  └─ task_repository.py
│  ├─ services/
│  │  ├─ ingestion_service.py
│  │  ├─ pipeline_parallel.py
│  │  ├─ task_queue.py
│  │  ├─ task_state_cache.py
│  │  ├─ cycle_service.py
│  │  ├─ cycle_inference.py
│  │  ├─ query_service.py
│  │  ├─ llm_service.py
│  │  ├─ config_service.py
│  │  ├─ prompt_template_service.py
│  │  ├─ export_service.py
│  │  └─ parameter_definitions.py
│  ├─ llm/
│  │  ├─ client.py
│  │  ├─ prompts.py
│  │  └─ context.py
│  ├─ utils/
│  │  ├─ files.py
│  │  ├─ timeparse.py
│  │  ├─ text.py
│  │  └─ rules.py
│  └─ main.py
├─ ui/
│  └─ streamlit_app.py
├─ config/
│  ├─ thresholds.yaml
│  ├─ parser_rules.yaml
│  ├─ error_rules.yaml
│  └─ prompt_templates.yaml
├─ scripts/
│  ├─ init_db.py
│  ├─ run_api.py
│  ├─ run_ui.py
│  ├─ start_local.bat
│  └─ start_local.ps1
├─ tests/
├─ data/
├─ requirements.txt
├─ .env.example
├─ Dockerfile
├─ docker-compose.yml
└─ README.md
```

---

## 5. 安装说明

### 5.1 创建虚拟环境

Linux / macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 5.2 安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5.3 初始化数据库与迁移

```bash
python -m scripts.init_db
```

该命令会：

- 创建缺失表
- 对旧 SQLite 执行轻量补列迁移
- 准备运行目录

---

## 6. 配置说明

## 6.1 `.env` 配置

复制模板：

```bash
cp .env.example .env
```

Windows:

```powershell
copy .env.example .env
```

关键并行配置项建议如下：

```env
MAX_PARALLEL_CPU_CORES=4
ENABLE_MULTIPROCESS_PARSE=true
ENABLE_THREADED_PRESCAN=true
ENABLE_STAGED_PARALLEL_PIPELINE=true
PRESCAN_THREAD_WORKERS=8
PARALLEL_MIN_FILES=2
FILE_SCAN_BATCH_SIZE=200
PARSE_BATCH_SIZE=8
FAILED_WORKER_RETRIES=1
SQLITE_WRITE_STRATEGY=main_process_only
INTERMEDIATE_CACHE_DIR=./data/intermediate_cache
TEMP_DIR=./data/tmp
QUEUE_DISPATCH_WORKERS=2
```

## 6.2 配置解释

- `MAX_PARALLEL_CPU_CORES`：允许任务使用的最大 CPU 核心数上限
- `ENABLE_MULTIPROCESS_PARSE`：是否启用多进程单文件解析
- `ENABLE_THREADED_PRESCAN`：是否启用多线程预扫描
- `ENABLE_STAGED_PARALLEL_PIPELINE`：是否启用分阶段并行
- `PRESCAN_THREAD_WORKERS`：预扫描线程池大小
- `PARALLEL_MIN_FILES`：文件数达到该阈值才启用多进程解析
- `FILE_SCAN_BATCH_SIZE`：大目录扫描时批量预扫描的批大小
- `PARSE_BATCH_SIZE`：提交给进程池的单批文件数
- `FAILED_WORKER_RETRIES`：失败文件回退串行重试次数
- `SQLITE_WRITE_STRATEGY`：当前固定为 `main_process_only`
- `INTERMEDIATE_CACHE_DIR`：worker 中间 JSONL 输出目录
- `TEMP_DIR`：压缩包解压和临时工作目录
- `QUEUE_DISPATCH_WORKERS`：后台任务队列并发 worker 数

---

## 7. 启动方式

### 7.1 本地启动

```bash
python -m scripts.init_db
python -m scripts.run_api
python -m scripts.run_ui
```

访问：

- FastAPI 文档：`http://127.0.0.1:8000/docs`
- Streamlit：`http://127.0.0.1:8501`

### 7.2 Windows 推荐启动方式

```powershell
python -m scripts.init_db
python -m scripts.run_api
python -m scripts.run_ui
```

或使用：

- `scripts/start_local.bat`
- `scripts/start_local.ps1`

### 7.3 Docker 启动

```bash
docker compose up --build
```

---

## 8. 如何处理大量文件

推荐流程：

1. 按任务打包上传，避免多个零散批次同时并发
2. 在 UI 上传时指定合理 `CPU 核心数`
3. 压缩包中尽量排除明显无关文件
4. 对超大目录，优先在上传前做一次业务筛选
5. 处理中不要重复点击上传按钮，等待当前任务完成或查看队列状态

系统处理顺序：

- 先解压与发现输入文件
- 再预扫描识别 parser
- 再进入多进程单文件解析
- 最后在主进程做全局推断和汇总

---

## 9. 并行参数调优建议

### 小批量任务（< 10 文件）

建议：

- `cpu_cores = 1 ~ 2`
- 可关闭多进程，减少进程创建开销

### 中等批量任务（10 ~ 100 文件）

建议：

- `cpu_cores = 2 ~ 4`
- 开启线程预扫描 + 多进程解析

### 大批量任务（100+ 文件）

建议：

- `cpu_cores = 4 ~ 8`（受机器物理核数限制）
- 适当增大 `PARSE_BATCH_SIZE`
- 观察内存与磁盘 IO，而不是只盯 CPU 占用

### 不建议的设置

- 在 2 核机器上强行设置 8 个解析进程
- 同时启动多套 API / UI 指向同一 SQLite
- 把 SQLite 当成高频状态总线

---

## 10. 性能与资源占用建议

### 10.1 CPU

- 多进程解析会明显提高 CPU 利用率
- 推荐 worker 数接近物理核心数，而不是逻辑线程数上限

### 10.2 内存

- worker 不返回大 DataFrame
- 统一写 JSONL 中间结果，降低进程间大对象拷贝
- 主进程统一聚合，避免多个全局大对象同时存在

### 10.3 磁盘

- 中间结果落盘到 `INTERMEDIATE_CACHE_DIR`
- 大任务时该目录会增长，应定期清理历史任务缓存

### 10.4 SQLite

- 只允许主进程写数据库
- UI 状态轮询优先走内存缓存
- 避免多进程直接并发写 SQLite

---

## 11. 结果一致性说明

并行化后，为保证结果正确性，本项目遵循以下一致性规则：

1. 单文件解析结果彼此独立
2. 跨文件关联只在主进程进行
3. 所有数据库写入只在主进程进行
4. 错误簇合并、cycle 推断、参数统计都在全量标准事件集上完成

因此：

- 并行只提升吞吐量
- 不改变业务统计口径
- 不引入多 worker 争用全局状态

---

## 12. 如何验证并行处理结果正确性

建议使用同一批输入文件做两次对比：

### 方法一：串行 vs 并行对比

- 一次 `cpu_cores=1`
- 一次 `cpu_cores=4`

对比以下输出是否一致：

- 总事件数
- 总错误数
- Top 错误簇
- Cycle 总耗时
- 参数趋势图
- 导出 JSON / CSV 内容

### 方法二：审计日志检查

在任务审计日志中检查：

- 预扫描阶段文件数
- 解析阶段成功/失败文件数
- 总耗时
- worker 数

---

## 13. 常见错误与排查

### 13.1 `database is locked`

原因：SQLite 被高频状态写入或多进程并发写占用。  
排查：

- 确认只有主进程写 SQLite
- 不要同时启动多套 API
- 降低 UI 自动刷新频率

### 13.2 `No module named openpyxl`

执行：

```bash
python -m pip install openpyxl
```

### 13.3 `No module named reportlab`

执行：

```bash
python -m pip install reportlab
```

### 13.4 `.7z` 无法解析

执行：

```bash
python -m pip install py7zr
```

### 13.5 Windows 下多进程启动异常

Windows 默认使用 `spawn`，不是 Linux 下的 `fork`。因此必须：

- 避免在模块导入阶段直接启动进程池
- 把多进程 worker 函数放在可导入模块顶层
- 使用 `if __name__ == "__main__"` 的启动入口脚本
- 建议通过 `scripts/run_api.py` 启动，而不是从交互环境直接起进程池

### 13.6 上传后任务一直排队

检查：

- `QUEUE_DISPATCH_WORKERS`
- 当前是否已有其他任务占用队列
- `/api/v1/health` 中 `queue_pending`

---

## 14. Windows / Linux 差异说明

### Windows

- 多进程默认使用 `spawn`
- 进程启动成本高于 Linux
- 更应避免在 worker 中传递大型对象
- 推荐用 JSONL 中间结果文件做主进程聚合

### Linux

- 多进程行为更接近 `fork`
- 启动成本较低
- 但仍然不建议让 worker 直接写 SQLite

---

## 15. 如何避免资源占用过高

1. 不要把 CPU 核心数直接拉满
2. 对超大任务分批处理，而不是所有目录一次全上
3. 控制 `PARSE_BATCH_SIZE`
4. 定期清理 `data/intermediate_cache/` 与 `data/tmp/`
5. UI 层不要重复触发同一任务分析

---

## 16. 开发与扩展建议

### 新增解析器

- 在 `app/parsers/` 下增加新 parser
- 在 `registry.py` 注册
- parser 只负责单文件解析，不参与并发调度

### 新增并行阶段

如需进一步扩展，建议继续遵守：

- worker 只处理局部输入
- 结果对象序列化后交给主进程
- 主进程做全局合并、最终写库

### 不建议做的改造

- 多进程直接并发写 SQLite
- UI 层直接控制进程池
- 在 worker 中共享全局 DataFrame
- 为了“看起来更快”而打乱 DAG 顺序依赖

---

## 17. 适合团队内部交付的运维建议

- 固定使用项目根目录启动
- 将 `.env` 与 `config/*.yaml` 纳入配置管理
- 对大任务保留审计日志和导出 JSON 报告用于复核
- 在上线前对典型大目录做 `cpu_cores=1` 与 `cpu_cores=N` 的结果一致性校验

---

## 18. 总结

新版并行架构采用“**局部并行 + 主进程聚合 + 主进程写库**”策略：

- 速度提升主要来自多线程预扫描和多进程单文件解析
- 正确性来自主进程统一做跨文件关联与数据库写入
- 工程可维护性来自清晰的职责边界：
  - ingestion 负责调度
  - parser worker 负责单文件处理
  - aggregator / analytics 负责统一汇总
  - plotting/UI 只消费结构化结果

这也是当前项目在 Python + SQLite + FastAPI + Streamlit 组合下更稳妥的并行化落地方式。


## LLM Token 优化与最小必要上下文

当前版本对 LLM 诊断链路进一步做了 Token 优化。核心原则是先缩小候选上下文，再进行去重、优先级排序、关键行保留和消息截断，最后才将压缩后的最小必要上下文送入模型。

### 当前压缩策略

1. 先按错误签名直接命中的事件作为锚点。
2. 再按时间窗、同 component、同 cycle、同 chip 做有限扩展，而不是全表扫描。
3. 对候选上下文执行去重，自动移除大量重复行和低价值 INFO completed 行。
4. 对 warning/error/exception/timeout/failed 等高价值行赋予更高优先级。
5. 对长堆栈只保留顶部关键帧，并对 message 做截断压缩。
6. Prompt 采用紧凑 JSON，不再使用大段缩进格式。

### UI 可见指标

在“LLM 诊断”页面，无论是历史诊断还是新发起诊断，都可看到：

- 最终总 Token
- Prompt Token
- 输出 Token
- 压缩效率
- 上下文原始/压缩 Token 估算
- 是否在预算内

说明：

- 若 LLM 服务返回 usage，则展示真实 token 消耗。
- 若服务未返回 usage，则系统自动回退为估算值。
- 压缩效率 = 1 - 压缩后上下文 token / 原始候选上下文 token。
