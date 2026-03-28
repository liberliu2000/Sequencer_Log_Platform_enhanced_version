from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    root = ensure_project_root_on_path()
    ensure_working_directory(root)
    return root
