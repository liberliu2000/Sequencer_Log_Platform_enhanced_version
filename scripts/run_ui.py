from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _maybe_reexec_in_venv() -> None:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    current_python = Path(sys.executable).resolve()

    if not venv_python.exists():
        return

    if current_python == venv_python.resolve():
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    print(f"Switching to project virtualenv: {venv_python}")
    subprocess.run([str(venv_python), "-m", "scripts.run_ui"], check=True, env=env)
    raise SystemExit(0)

from app.core.bootstrap import bootstrap_for_local_run

_maybe_reexec_in_venv()
PROJECT_ROOT = bootstrap_for_local_run()


if __name__ == "__main__":
    target = PROJECT_ROOT / "ui" / "streamlit_app.py"
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT))
    print(f"Starting Streamlit from project_root={PROJECT_ROOT}")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(target)], check=True, env=env)
