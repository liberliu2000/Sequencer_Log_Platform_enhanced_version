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

## 定时执行建议

Windows 计划任务可直接执行：

```powershell
python D:\VScode1\MyProjects\CycleDash\sequencer_log_platform_V43\scripts\release_sync.py --patch
```

如果希望脚本自身循环检查，也可以使用：

```powershell
python scripts/release_sync.py --patch --interval-minutes 30
```
