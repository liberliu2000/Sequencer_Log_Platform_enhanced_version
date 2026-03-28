from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
