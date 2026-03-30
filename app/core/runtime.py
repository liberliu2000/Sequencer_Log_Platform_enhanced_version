from __future__ import annotations

import shutil
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return SOURCE_ROOT


def runtime_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT


def ensure_runtime_layout() -> Path:
    target_root = runtime_root()
    source_root = bundle_root()

    for name in ("config",):
        source = source_root / name
        target = target_root / name
        if source.exists() and not target.exists():
            shutil.copytree(source, target)

    for name in ("VERSION", ".env.example"):
        source = source_root / name
        target = target_root / name
        if source.exists() and not target.exists():
            shutil.copy2(source, target)

    env_file = target_root / ".env"
    if not env_file.exists():
        example = target_root / ".env.example"
        if example.exists():
            shutil.copy2(example, env_file)

    for name in ("data",):
        (target_root / name).mkdir(parents=True, exist_ok=True)

    return target_root
