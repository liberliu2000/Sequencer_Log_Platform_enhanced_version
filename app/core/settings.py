from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sequencer Log Platform"
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'sequencer_log_platform.db').as_posix()}"
    data_dir: str = str(BASE_DIR / "data")
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    export_dir: str = str(BASE_DIR / "data" / "exports")
    log_dir: str = str(BASE_DIR / "data" / "runtime_logs")
    intermediate_cache_dir: str = str(BASE_DIR / "data" / "intermediate_cache")
    temp_dir: str = str(BASE_DIR / "data" / "tmp")

    max_upload_mb: int = 512
    chunk_size: int = 65536

    # 并行/调度
    enable_parallel_parse: bool = True
    enable_threaded_prescan: bool = True
    enable_multiprocess_parse: bool = True
    enable_staged_parallel_pipeline: bool = True
    max_parallel_cpu_cores: int = 4
    max_thread_workers: int = 8
    max_process_workers: int = 4
    prescan_thread_workers: int = 8
    queue_dispatch_workers: int = 2
    parallel_min_files: int = 3
    file_scan_batch_size: int = 200
    parse_batch_size: int = 16
    load_batch_size: int = 32
    metrics_batch_size: int = 64
    failed_worker_retries: int = 1
    sqlite_write_strategy: Literal["main_process_only"] = "main_process_only"

    # 前端/数据准备性能
    enable_service_cache: bool = True
    service_cache_ttl_seconds: int = 120
    service_cache_max_entries: int = 256
    front_page_max_rows: int = 100
    table_page_default_size: int = 100
    table_page_max_size: int = 500
    lightweight_mode: bool = True
    ui_auto_refresh_seconds: int = 5
    performance_log_enabled: bool = True

    default_time_rounding: Literal["truncate", "round"] = "truncate"
    default_timezone: str = "Asia/Shanghai"

    llm_enabled: bool = False
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_api_key: str = ""
    llm_model: str = "ep-xxx"
    llm_timeout_seconds: int = 45
    llm_max_retries: int = 3
    llm_preview_timeout_seconds: int = 12
    llm_preview_max_retries: int = 1
    llm_preview_cache_ttl_seconds: int = 600
    llm_preview_max_unknown_samples: int = 4
    llm_preview_max_feedback_samples: int = 4
    llm_preview_max_parser_snippets: int = 3
    llm_diagnosis_ui_timeout_seconds: int = 120

    llm_context_pre_lines: int = 8
    llm_context_post_lines: int = 8
    llm_context_time_window_seconds: int = 90
    llm_context_related_component_limit: int = 30
    llm_context_related_cycle_limit: int = 30
    llm_context_max_stack_frames: int = 8
    llm_context_max_token_budget: int = 2200
    llm_context_stage1_token_budget: int = 1200

    api_prefix: str = "/api/v1"
    cors_allow_origins: str = "*"
    task_queue_workers: int = 2

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug(cls, value):
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if text in {"debug", "dev", "true", "1", "yes", "on"}:
                return True
        return value

    @property
    def thresholds_path(self) -> Path:
        return BASE_DIR / "config" / "thresholds.yaml"

    @property
    def parser_rules_path(self) -> Path:
        return BASE_DIR / "config" / "parser_rules.yaml"

    @property
    def error_rules_path(self) -> Path:
        return BASE_DIR / "config" / "error_rules.yaml"

    @property
    def prompt_templates_path(self) -> Path:
        return BASE_DIR / "config" / "prompt_templates.yaml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    for p in [
        settings.data_dir,
        settings.upload_dir,
        settings.export_dir,
        settings.log_dir,
        settings.intermediate_cache_dir,
        settings.temp_dir,
        str(Path(settings.data_dir) / "performance"),
    ]:
        Path(p).mkdir(parents=True, exist_ok=True)
    return settings
