from __future__ import annotations

from pathlib import Path

import app.core.runtime as runtime


def _clear_vercel_env(monkeypatch) -> None:
    for name in ("VERCEL", "VERCEL_ENV", "VERCEL_URL"):
        monkeypatch.delenv(name, raising=False)


def test_runtime_root_defaults_to_source_root(monkeypatch):
    _clear_vercel_env(monkeypatch)

    assert runtime.runtime_root() == runtime.SOURCE_ROOT


def test_runtime_root_uses_temp_directory_on_vercel(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(tmp_path))

    assert runtime.runtime_root() == tmp_path / runtime.VERCEL_RUNTIME_DIRNAME


def test_ensure_runtime_layout_creates_writable_vercel_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(tmp_path))

    root = runtime.ensure_runtime_layout()

    assert root == tmp_path / runtime.VERCEL_RUNTIME_DIRNAME
    assert (root / "config" / "thresholds.yaml").exists()
    assert (root / ".env.example").exists()
    assert (root / ".env").exists()
    assert (root / "data").is_dir()
