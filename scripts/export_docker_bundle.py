from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = ("app", "config", "frontend", "scripts", "ui")
INCLUDE_FILES = (
    ".dockerignore",
    ".env.example",
    ".env.docker.example",
    "docker-compose.oneclick.yml",
    "Dockerfile.api",
    "Dockerfile.streamlit",
    "README.md",
    "requirements.txt",
    "VERSION",
)
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".next",
    ".pytest_cache",
    ".pytype",
    ".venv",
    ".vercel",
    "node_modules",
}
SKIP_FILE_NAMES = {
    ".DS_Store",
    ".env",
    ".env.local",
    ".env.production",
    "tsconfig.tsbuildinfo",
}


def _ignore(_source: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in SKIP_DIR_NAMES or name in SKIP_FILE_NAMES:
            ignored.add(name)
    return ignored


def _copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=_ignore, dirs_exist_ok=True)


def _replace_env_value(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    updated = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            updated.append(f"{prefix}{value}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"{prefix}{value}")
    return updated


def _write_runtime_env(target_root: Path, public_api_base_url: str) -> None:
    env_example = (target_root / ".env.docker.example").read_text(encoding="utf-8").splitlines()
    env_example = _replace_env_value(env_example, "NEXT_PUBLIC_API_BASE_URL", public_api_base_url)
    env_example = _replace_env_value(env_example, "STREAMLIT_API_BASE", "http://api:8000/api/v1")
    (target_root / ".env.docker").write_text("\n".join(env_example) + "\n", encoding="utf-8")


def export_bundle(target_root: Path, public_api_base_url: str) -> None:
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    for relative_dir in INCLUDE_DIRS:
        _copy_tree(PROJECT_ROOT / relative_dir, target_root / relative_dir)

    for relative_file in INCLUDE_FILES:
        shutil.copy2(PROJECT_ROOT / relative_file, target_root / relative_file)

    _write_runtime_env(target_root, public_api_base_url)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a slim Docker deployment bundle.")
    parser.add_argument("target", help="Target directory for the deployment bundle.")
    parser.add_argument(
        "--public-api-base-url",
        default="http://127.0.0.1:8000/api/v1",
        help="Public API base URL baked into the Next.js frontend bundle.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    export_bundle(Path(args.target).resolve(), str(args.public_api_base_url).strip())
    print(f"Bundle exported to {Path(args.target).resolve()}")


if __name__ == "__main__":
    main()
