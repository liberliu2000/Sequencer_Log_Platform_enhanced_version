from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Iterable

from app.core.bootstrap import bootstrap_for_local_run
from app.core.settings import get_settings


PROJECT_ROOT = bootstrap_for_local_run()


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def _wait_http_ready(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(1.0)
    return False


def _child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT))
    if extra:
        env.update(extra)
    return env


def _spawn_child(args: Iterable[str], *, extra_env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    executable = Path(sys.executable).resolve()
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        [str(executable), *args],
        cwd=str(PROJECT_ROOT),
        env=_child_env(extra_env),
        creationflags=creationflags,
    )


def run_api() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )


def run_ui() -> None:
    from streamlit.web import bootstrap

    target = str(PROJECT_ROOT / "ui" / "streamlit_app.py")
    api_base = os.getenv("STREAMLIT_API_BASE", f"http://127.0.0.1:{get_settings().app_port}/api/v1")
    os.environ.setdefault("STREAMLIT_API_BASE", api_base)
    bootstrap.run(target, False, [], {})


def run_desktop() -> int:
    settings = get_settings()
    api_port = settings.app_port
    ui_port = int(os.getenv("STREAMLIT_SERVER_PORT", "8501"))

    api_process = _spawn_child(["--mode", "api"])
    ui_process = _spawn_child(
        ["--mode", "ui"],
        extra_env={
            "STREAMLIT_SERVER_HEADLESS": "true",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
            "STREAMLIT_SERVER_PORT": str(ui_port),
            "STREAMLIT_API_BASE": f"http://127.0.0.1:{api_port}/api/v1",
        },
    )

    api_ready = _wait_http_ready("127.0.0.1", api_port, 60)
    ui_ready = _wait_http_ready("127.0.0.1", ui_port, 90)

    if not api_ready:
        print(f"FastAPI did not become ready on port {api_port}.")

    if ui_ready:
        webbrowser.open(f"http://localhost:{ui_port}")
    else:
        print(f"Streamlit did not become ready on port {ui_port}.")

    try:
        while True:
            api_code = api_process.poll()
            ui_code = ui_process.poll()
            if api_code is not None or ui_code is not None:
                return api_code or ui_code or 0
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0
    finally:
        for process in (api_process, ui_process):
            if process.poll() is None:
                process.terminate()
        for process in (api_process, ui_process):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sequencer Log Platform desktop launcher")
    parser.add_argument(
        "--mode",
        choices=("desktop", "api", "ui"),
        default="desktop",
        help="desktop launches both API and Streamlit; api/ui launch a single service",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "api":
        run_api()
        return 0
    if args.mode == "ui":
        run_ui()
        return 0
    return run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
