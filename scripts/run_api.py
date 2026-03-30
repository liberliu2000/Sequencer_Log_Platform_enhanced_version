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
    subprocess.run([str(venv_python), "-m", "scripts.run_api"], check=True, env=env)
    raise SystemExit(0)

_maybe_reexec_in_venv()

import uvicorn
from app.core.bootstrap import bootstrap_for_local_run

PROJECT_ROOT = bootstrap_for_local_run()

from app.core.settings import get_settings  # noqa: E402


if __name__ == "__main__":
    settings = get_settings()
    print(f"Starting FastAPI from project_root={PROJECT_ROOT}")
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "dev",
    )
