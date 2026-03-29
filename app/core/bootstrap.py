from __future__ import annotations

import os
import sys
from pathlib import Path

from app.core.runtime import ensure_runtime_layout, runtime_root

PROJECT_ROOT = runtime_root()


def ensure_project_root_on_path() -> Path:
    root = PROJECT_ROOT
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def ensure_working_directory(project_root: Path | None = None) -> Path:
    root = project_root or PROJECT_ROOT
    os.chdir(root)
    return root


def bootstrap_for_local_run() -> Path:
    root = ensure_runtime_layout()
    ensure_project_root_on_path()
    ensure_working_directory(root)
    return root
