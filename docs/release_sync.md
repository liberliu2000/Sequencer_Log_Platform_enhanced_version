# Release Sync

`scripts/release_sync.py` 用于自动完成版本生成、Git 提交、标签创建和远程推送。

## 功能

- 自动校验当前目录是否为 Git 仓库
- 自动校验是否存在远程仓库
- 自动读取或初始化根目录 `VERSION` 文件
- 自动过滤依赖目录、上传文件、分析结果和敏感配置
- 自动执行 `git add` -> `git commit` -> `git tag` -> `git push`
- 遇到网络错误、冲突、未初始化仓库等异常时给出明确提示并终止

## 默认排除规则

- 依赖目录：`.venv/`、`venv/`、`site-packages/`、`__pycache__/`
- 用户上传：`uploads/`、`user_files/`、`data/uploads/`
- 中间与结果数据：`analysis_results/`、`data/tmp/`、`data/intermediate_cache/`、`data/active_learning/`、`data/performance/`
- 数据文件：`*.csv`、`*.xlsx`、`*.xls`、`*.db`、`*.sqlite`、`*.sqlite3`
- 压缩包：`*.7z`、`*.zip`、`*.tar`、`*.tgz`、`*.gz`、`*.bz2`
- 敏感配置：`.env`、`.env.*`、`local_config.py`

以上规则已经同步写入根目录 `.gitignore`。

## 版本规则

- 默认格式：`vMAJOR.MINOR.PATCH`
- `--major`：主版本递增
- `--minor`：次版本递增
- `--patch`：补丁版本递增，默认值
- `--version vX.Y.Z`：手动指定版本号
- 若 `VERSION` 不存在，首次执行会初始化为 `v1.0.0`

提交信息格式固定为：

```text
Release: v1.0.1 - 自动同步项目变更
```

如果通过 `--msg` 指定说明，则格式变为：

```text
Release: v1.1.0 - 新增用户登录功能
```

## 常用命令

```bash
python scripts/release_sync.py --patch
python scripts/release_sync.py --minor --msg "新增用户登录功能"
python scripts/release_sync.py --version v1.1.0 --branch main
python scripts/release_sync.py --patch --dry-run
python scripts/release_sync.py --patch --interval-minutes 30
```

## 推荐的三端一致流程

目标是保持以下三处代码始终指向同一个提交：

- GitHub `online-version` 分支
- 本地 D 盘仓库
- Ubuntu 服务器部署目录

原则：

- 只在本地改代码并提交
- 服务器禁止手改业务代码
- 服务器只执行 `git pull --ff-only`
- `.env`、数据库、上传文件等运行态数据不提交到 GitHub

### 1. 本地先预览本次将发布什么

```powershell
python scripts/release_sync.py --patch --branch online-version --dry-run
```

建议先确认输出里的文件列表是否就是你希望上线的那一批文件。

### 2. 本地正式发布到 GitHub

```powershell
python scripts/release_sync.py --patch --branch online-version --msg "修复服务器启动超时"
```

脚本会自动完成：

- 更新 `VERSION`
- 提交允许发布的代码
- 打 Git Tag
- 推送到 GitHub `online-version`

### 3. 服务器只拉取同一分支同一提交

在 Ubuntu 服务器仓库根目录执行：

```bash
bash scripts/deploy_server.sh online-version
```

这个脚本会自动完成：

- `git fetch origin online-version --tags`
- `git checkout online-version`
- `git pull --ff-only origin online-version`
- `docker compose -f docker-compose.prod.yml up -d --build`
- 输出当前提交 SHA
- 访问 `http://127.0.0.1:8000/api/v1/health` 做健康检查

### 4. 核对三端是否一致

本地查看：

```powershell
git rev-parse HEAD
```

服务器查看：

```bash
git rev-parse HEAD
```

GitHub 上查看 `online-version` 最新提交 SHA。

只要这三个 SHA 完全一致，就说明 GitHub、本地和服务器代码完全一致。

## 服务器排障建议

如果服务器仍然出现 `504 Gateway Time-out`，优先按下面顺序检查：

1. 先看容器是否真的启动成功：

```bash
docker compose -f docker-compose.prod.yml ps
```

2. 再看 API 本地健康检查是否正常：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

3. 如果 API 正常但网页访问仍然 504，重点排查 Nginx 反向代理配置是否指向了正确端口。

4. 如果 API 启动慢，查看容器日志确认是否卡在启动阶段：

```bash
docker compose -f docker-compose.prod.yml logs api --tail=200
docker compose -f docker-compose.prod.yml logs web --tail=200
```

5. 如果是长接口超时，而不是启动超时，再检查 Nginx 的 `proxy_read_timeout` 是否过短。

## 定时执行建议

Windows 计划任务可直接执行：

```powershell
python D:\VScode1\MyProjects\CycleDash\sequencer_log_platform_V43\scripts\release_sync.py --patch
```

如果希望脚本自身循环检查，也可以使用：

```powershell
python scripts/release_sync.py --patch --interval-minutes 30
```
