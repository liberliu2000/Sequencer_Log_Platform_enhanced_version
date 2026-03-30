from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
DEFAULT_RELEASE_MESSAGE = "自动同步项目变更"
DEFAULT_GIT_BIN = r"D:\Git\Git\cmd\git.exe"
DEFAULT_REMOTE_NAME = "origin"
DEFAULT_REMOTE_URL = "https://github.com/liberliu2000/Sequencer_Log_Platform_enhanced_version.git"
ROOT_EXCLUDE_PREFIXES = (
    "analysis_results/",
    "uploads/",
    "user_files/",
    "data/uploads/",
    "data/tmp/",
    "data/intermediate_cache/",
    "data/active_learning/",
    "data/performance/",
)
EXCLUDED_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "analysis_results",
    "site-packages",
    "uploads",
    "user_files",
    "venv",
}
EXCLUDED_SUFFIXES = {
    ".7z",
    ".bz2",
    ".csv",
    ".db",
    ".gz",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tgz",
    ".xls",
    ".xlsx",
    ".zip",
}
EXCLUDED_FILENAMES = {
    ".env",
    "local_config.py",
}
EXCLUDED_PREFIXES = (
    ".env.",
    "pytest-cache-files-",
)
COMMON_GIT_PATHS = (
    ("ProgramFiles", "Git", "cmd", "git.exe"),
    ("ProgramFiles", "Git", "bin", "git.exe"),
    ("ProgramW6432", "Git", "cmd", "git.exe"),
    ("ProgramW6432", "Git", "bin", "git.exe"),
    ("ProgramFiles(x86)", "Git", "cmd", "git.exe"),
    ("ProgramFiles(x86)", "Git", "bin", "git.exe"),
    ("LocalAppData", "Programs", "Git", "cmd", "git.exe"),
)


class ReleaseSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseContext:
    repo_root: Path
    git_bin: str
    branch: str
    remote: str
    version_file: Path


@dataclass(frozen=True)
class ReleaseResult:
    version: str
    branch: str
    committed: bool
    dry_run: bool
    skipped_paths: tuple[str, ...]
    staged_paths: tuple[str, ...]
    reason: str


def discover_git_executable() -> str:
    default_git = Path(DEFAULT_GIT_BIN)
    if default_git.exists():
        return str(default_git)

    override = os.environ.get("GIT_BIN")
    if override:
        override_path = Path(override)
        if override_path.exists():
            return str(override_path)
        raise ReleaseSyncError(f"GIT_BIN 指向的 git 不存在: {override}")

    for name in ("git", "git.exe"):
        resolved = shutil.which(name)
        if resolved:
            return resolved

    for parts in COMMON_GIT_PATHS:
        base = os.environ.get(parts[0])
        if not base:
            continue
        candidate = Path(base, *parts[1:])
        if candidate.exists():
            return str(candidate)

    raise ReleaseSyncError(
        "未找到 git 可执行文件。请先安装 Git，或通过环境变量 GIT_BIN 指定 git.exe 的完整路径。"
    )


def run_git(
    git_bin: str,
    repo_root: Path,
    args: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [git_bin, *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout).strip()
        raise ReleaseSyncError(format_git_error(args, stderr))
    return completed


def format_git_error(args: Sequence[str], stderr: str) -> str:
    command = " ".join(args)
    message = stderr or "未知 Git 错误"
    lower = message.lower()

    if "not a git repository" in lower:
        return f"`git {command}` 失败: 当前目录不是 Git 仓库，请先执行 `git init` 并配置远程仓库。"
    if "could not resolve host" in lower or "failed to connect" in lower or "timed out" in lower:
        return f"`git {command}` 失败: 网络连接异常，请检查网络、代理或 GitHub 可达性后重试。"
    if "merge conflict" in lower or "conflict" in lower:
        return f"`git {command}` 失败: 检测到 Git 冲突，请先解决冲突再重新发布。"
    if "already exists" in lower and "tag" in lower:
        return f"`git {command}` 失败: 版本标签已存在，请改用新的版本号。"
    if "couldn't find remote ref" in lower or "src refspec" in lower:
        return f"`git {command}` 失败: 目标分支不存在，请先确认本地已切换到正确分支。"
    if "permission denied" in lower or "authentication failed" in lower:
        return f"`git {command}` 失败: 远程鉴权失败，请检查 GitHub 凭据或 SSH/Token 配置。"
    return f"`git {command}` 失败: {message}"


def normalize_path(path_text: str) -> str:
    normalized = path_text.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_excluded_path(path_text: str) -> bool:
    normalized = normalize_path(path_text)
    if not normalized:
        return False

    lowered = normalized.lower()
    name = PurePosixPath(normalized).name.lower()
    if name == ".env.example":
        return False
    if name in EXCLUDED_FILENAMES:
        return True
    if any(name.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return True
    if any(lowered.startswith(prefix) for prefix in ROOT_EXCLUDE_PREFIXES):
        return True

    path = PurePosixPath(lowered)
    for part in path.parts:
        if part in EXCLUDED_DIR_NAMES:
            return True
        if any(part.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            return True

    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    return False


def parse_status_paths(status_output: str) -> list[str]:
    paths: list[str] = []
    for raw_line in status_output.splitlines():
        if not raw_line:
            continue
        status = raw_line[:2]
        remainder = raw_line[3:].strip()
        if not remainder:
            continue

        if "->" in remainder and ("R" in status or "C" in status):
            old_path, new_path = [normalize_path(item) for item in remainder.split("->", 1)]
            paths.extend([old_path.strip(), new_path.strip()])
            continue

        paths.append(normalize_path(remainder))
    return paths


def normalize_version(version_text: str) -> str:
    version = version_text.strip()
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise ReleaseSyncError(f"版本号格式非法: {version_text}。请使用 vMAJOR.MINOR.PATCH，例如 v1.2.3")
    return version


def version_tuple(version_text: str) -> tuple[int, int, int]:
    normalized = normalize_version(version_text)
    match = SEMVER_RE.fullmatch(normalized)
    if not match:
        raise ReleaseSyncError(f"版本号格式非法: {version_text}。请使用 vMAJOR.MINOR.PATCH，例如 v1.2.3")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def bump_version(version_text: str, bump: str) -> str:
    major, minor, patch = version_tuple(version_text)
    if bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"v{major}.{minor}.{patch}"


def chunked(items: Sequence[str], size: int = 80) -> list[list[str]]:
    return [list(items[idx : idx + size]) for idx in range(0, len(items), size)]


def ensure_repo_context(repo_root: Path, git_bin: str, requested_branch: str | None) -> ReleaseContext:
    top_level = run_git(git_bin, repo_root, ["rev-parse", "--show-toplevel"]).stdout.strip()
    if not top_level:
        raise ReleaseSyncError("无法识别 Git 仓库根目录，请确认当前目录已经完成 `git init`。")

    resolved_root = Path(top_level).resolve()
    if resolved_root != repo_root.resolve():
        repo_root = resolved_root

    if run_git(git_bin, repo_root, ["diff", "--name-only", "--diff-filter=U"], check=False).stdout.strip():
        raise ReleaseSyncError("检测到未解决的 Git 冲突，请先处理冲突后再执行发布。")

    staged_before = run_git(git_bin, repo_root, ["diff", "--cached", "--name-only"], check=False).stdout.strip()
    if staged_before:
        raise ReleaseSyncError("检测到已有暂存区内容。为避免误提交，请先提交或取消暂存后再执行发布脚本。")

    remote_names = [line.strip() for line in run_git(git_bin, repo_root, ["remote"]).stdout.splitlines() if line.strip()]
    if not remote_names:
        run_git(git_bin, repo_root, ["remote", "add", DEFAULT_REMOTE_NAME, DEFAULT_REMOTE_URL])
        remote_names = [DEFAULT_REMOTE_NAME]
        remote = DEFAULT_REMOTE_NAME
    else:
        remote = DEFAULT_REMOTE_NAME if DEFAULT_REMOTE_NAME in remote_names else remote_names[0]
        remote_url = run_git(git_bin, repo_root, ["remote", "get-url", remote], check=False).stdout.strip()
        if not remote_url and remote == DEFAULT_REMOTE_NAME:
            run_git(git_bin, repo_root, ["remote", "set-url", DEFAULT_REMOTE_NAME, DEFAULT_REMOTE_URL], check=False)

    current_branch = run_git(git_bin, repo_root, ["branch", "--show-current"], check=False).stdout.strip()
    if requested_branch:
        branch = requested_branch.strip()
        if current_branch and branch != current_branch:
            raise ReleaseSyncError(
                f"当前分支是 `{current_branch}`，但你指定了 `{branch}`。请先切换到目标分支后再执行发布。"
            )
    elif current_branch:
        branch = current_branch
    else:
        for candidate in ("main", "master"):
            if run_git(git_bin, repo_root, ["show-ref", "--verify", f"refs/heads/{candidate}"], check=False).returncode == 0:
                branch = candidate
                break
        else:
            raise ReleaseSyncError("当前处于 detached HEAD，且未找到 main/master。请显式传入 `--branch` 并切换到该分支。")

    if run_git(git_bin, repo_root, ["show-ref", "--verify", f"refs/heads/{branch}"], check=False).returncode != 0:
        raise ReleaseSyncError(f"本地分支 `{branch}` 不存在，请先创建或切换到该分支。")

    return ReleaseContext(
        repo_root=repo_root,
        git_bin=git_bin,
        branch=branch,
        remote=remote,
        version_file=repo_root / "VERSION",
    )


def determine_release_version(
    version_file: Path,
    manual_version: str | None,
    bump: str,
) -> tuple[str, str | None]:
    current_version: str | None = None
    if version_file.exists():
        raw = version_file.read_text(encoding="utf-8").strip()
        if raw:
            current_version = normalize_version(raw)
        else:
            raise ReleaseSyncError("VERSION 文件为空，请写入合法版本号后重试。")

    if manual_version:
        next_version = normalize_version(manual_version)
        if current_version and version_tuple(next_version) <= version_tuple(current_version):
            raise ReleaseSyncError(
                f"手动指定的版本号 {next_version} 必须大于当前版本 {current_version}，以保证版本可追溯。"
            )
        return next_version, current_version

    if current_version is None:
        return "v1.0.0", None
    return bump_version(current_version, bump), current_version


def collect_releasable_paths(context: ReleaseContext) -> tuple[list[str], list[str]]:
    status_output = run_git(
        context.git_bin,
        context.repo_root,
        ["status", "--porcelain=1", "--untracked-files=all"],
    ).stdout
    changed_paths = parse_status_paths(status_output)
    allowed = sorted({path for path in changed_paths if path and not is_excluded_path(path)})
    skipped = sorted({path for path in changed_paths if path and is_excluded_path(path)})
    return allowed, skipped


def write_version(version_file: Path, version: str) -> None:
    version_file.write_text(f"{version}\n", encoding="utf-8")


def ensure_tag_available(context: ReleaseContext, version: str) -> None:
    if run_git(
        context.git_bin,
        context.repo_root,
        ["rev-parse", "-q", "--verify", f"refs/tags/{version}"],
        check=False,
    ).returncode == 0:
        raise ReleaseSyncError(f"标签 `{version}` 已存在，请使用新的版本号。")


def stage_paths(context: ReleaseContext, paths: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(normalize_path(path) for path in paths if normalize_path(path)))
    for batch in chunked(normalized):
        run_git(context.git_bin, context.repo_root, ["add", "-A", "--", *batch])
    return normalized


def commit_and_push(context: ReleaseContext, version: str, commit_message: str) -> None:
    run_git(context.git_bin, context.repo_root, ["commit", "-m", commit_message])
    run_git(context.git_bin, context.repo_root, ["tag", version])
    run_git(
        context.git_bin,
        context.repo_root,
        [
            "push",
            context.remote,
            f"refs/heads/{context.branch}:refs/heads/{context.branch}",
            f"refs/tags/{version}:refs/tags/{version}",
        ],
    )


def release_once(args: argparse.Namespace) -> ReleaseResult:
    repo_root = Path(args.repo_root).resolve()
    git_bin = discover_git_executable()
    context = ensure_repo_context(repo_root, git_bin, args.branch)
    version, current_version = determine_release_version(context.version_file, args.version, args.bump)
    ensure_tag_available(context, version)

    allowed_paths, skipped_paths = collect_releasable_paths(context)
    version_missing = not context.version_file.exists()
    has_real_changes = bool([path for path in allowed_paths if path != "VERSION"])
    if not has_real_changes and not version_missing:
        return ReleaseResult(
            version=current_version or version,
            branch=context.branch,
            committed=False,
            dry_run=args.dry_run,
            skipped_paths=tuple(skipped_paths),
            staged_paths=(),
            reason="没有检测到可发布的变更，已跳过。",
        )

    commit_note = (args.msg or DEFAULT_RELEASE_MESSAGE).strip()
    commit_message = f"Release: {version} - {commit_note}"
    stage_targets = sorted(set(allowed_paths + ["VERSION"]))

    if args.dry_run:
        return ReleaseResult(
            version=version,
            branch=context.branch,
            committed=False,
            dry_run=True,
            skipped_paths=tuple(skipped_paths),
            staged_paths=tuple(stage_targets),
            reason="Dry-run 模式：未执行文件写入、提交、打标签或推送。",
        )

    write_version(context.version_file, version)
    staged_paths = stage_paths(context, stage_targets)
    cached_diff = run_git(context.git_bin, context.repo_root, ["diff", "--cached", "--name-only"], check=False).stdout.strip()
    if not cached_diff:
        raise ReleaseSyncError("没有形成可提交的暂存区内容，发布已终止。")

    commit_and_push(context, version, commit_message)
    return ReleaseResult(
        version=version,
        branch=context.branch,
        committed=True,
        dry_run=False,
        skipped_paths=tuple(skipped_paths),
        staged_paths=staged_paths,
        reason="发布完成。",
    )


def print_result(result: ReleaseResult) -> None:
    print(result.reason)
    print(f"目标分支: {result.branch}")
    print(f"版本号: {result.version}")
    if result.staged_paths:
        print(f"纳入发布文件数: {len(result.staged_paths)}")
    if result.skipped_paths:
        print("已跳过的排除文件:")
        for path in result.skipped_paths:
            print(f"  - {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="自动检测项目变更、更新 VERSION、提交 Release Commit、打 Git 标签并推送到远程仓库。",
    )
    parser.add_argument("--repo-root", default=".", help="Git 仓库根目录，默认当前目录。")
    parser.add_argument("--version", help="手动指定版本号，例如 v1.1.0。")
    parser.add_argument("--msg", help="手动指定发布说明。")
    parser.add_argument("--branch", help="指定发布分支；默认使用当前分支，detached HEAD 时回退 main/master。")
    parser.add_argument("--major", action="store_const", const="major", dest="bump", help="递增主版本号。")
    parser.add_argument("--minor", action="store_const", const="minor", dest="bump", help="递增次版本号。")
    parser.add_argument("--patch", action="store_const", const="patch", dest="bump", help="递增补丁版本号，默认值。")
    parser.add_argument(
        "--interval-minutes",
        type=float,
        help="按分钟定时执行发布检查；适合在长驻进程场景下使用。发生错误时会终止循环。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只输出本次计划执行的版本与文件，不实际提交。")
    parser.set_defaults(bump="patch")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.interval_minutes is not None and args.interval_minutes <= 0:
        parser.error("--interval-minutes 必须大于 0")

    while True:
        try:
            result = release_once(args)
            print_result(result)
        except ReleaseSyncError as exc:
            print(f"发布失败: {exc}", file=sys.stderr)
            return 1

        if args.interval_minutes is None:
            return 0

        sleep_seconds = int(args.interval_minutes * 60)
        print(f"{sleep_seconds} 秒后开始下一轮检查。按 Ctrl+C 可终止。")
        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print("已手动终止定时发布。")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
