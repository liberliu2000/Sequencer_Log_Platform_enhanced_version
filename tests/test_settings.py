from __future__ import annotations

from pathlib import Path

from app.core.settings import BASE_DIR, SQLITE_URL_PREFIX, Settings


def test_settings_resolve_relative_runtime_directories():
    settings = Settings(
        data_dir="./data",
        upload_dir="./data/uploads",
        export_dir="./data/exports",
        log_dir="./data/runtime_logs",
        intermediate_cache_dir="./data/intermediate_cache",
        temp_dir="./data/tmp",
    )

    assert Path(settings.data_dir).is_absolute()
    assert Path(settings.data_dir) == (BASE_DIR / "data").resolve()
    assert Path(settings.upload_dir) == (BASE_DIR / "data" / "uploads").resolve()
    assert Path(settings.export_dir) == (BASE_DIR / "data" / "exports").resolve()
    assert Path(settings.log_dir) == (BASE_DIR / "data" / "runtime_logs").resolve()
    assert Path(settings.intermediate_cache_dir) == (BASE_DIR / "data" / "intermediate_cache").resolve()
    assert Path(settings.temp_dir) == (BASE_DIR / "data" / "tmp").resolve()


def test_settings_resolve_relative_sqlite_database_url():
    settings = Settings(database_url="sqlite:///./data/sequencer_log_platform.db")

    assert settings.database_url == (
        f"{SQLITE_URL_PREFIX}{(BASE_DIR / 'data' / 'sequencer_log_platform.db').resolve().as_posix()}"
    )
