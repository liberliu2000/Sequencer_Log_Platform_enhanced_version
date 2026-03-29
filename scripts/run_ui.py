from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.bootstrap import bootstrap_for_local_run

PROJECT_ROOT = bootstrap_for_local_run()


if __name__ == "__main__":
    target = PROJECT_ROOT / "ui" / "streamlit_app.py"
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT))
    print(f"Starting Streamlit from project_root={PROJECT_ROOT}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(target),
            "--server.address=127.0.0.1",
            "--server.port=8501",
            "--server.headless=true",
            "--browser.serverAddress=127.0.0.1",
            "--browser.serverPort=8501",
        ],
        check=True,
        env=env,
    )
