from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _has_table(inspector, table_name: str) -> bool:
    try:
        return table_name in inspector.get_table_names()
    except Exception:
        return False


def _get_columns(inspector, table_name: str) -> set[str]:
    try:
        return {c["name"] for c in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _add_columns_if_missing(engine: Engine, table_name: str, columns: Iterable[tuple[str, str]]) -> list[str]:
    added: list[str] = []
    with engine.begin() as conn:
        inspector = inspect(conn)
        if not _has_table(inspector, table_name):
            return added
        existing = _get_columns(inspector, table_name)
        for col_name, col_def in columns:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
                added.append(col_name)
    return added


def _create_indexes_if_possible(engine: Engine) -> None:
    stmts = [
        "CREATE INDEX IF NOT EXISTS idx_upload_tasks_task_uuid ON upload_tasks(task_uuid)",
        "CREATE INDEX IF NOT EXISTS idx_upload_tasks_created_at ON upload_tasks(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_task_audit_logs_task_id ON task_audit_logs(task_id)",
        "CREATE INDEX IF NOT EXISTS idx_task_audit_logs_task_uuid ON task_audit_logs(task_uuid)",
        "CREATE INDEX IF NOT EXISTS idx_task_audit_logs_created_at ON task_audit_logs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_llm_results_task_sig ON llm_analysis_results(task_id, normalized_signature)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass


def migrate_sqlite_schema(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    dialect_name = engine.dialect.name.lower()
    result: dict[str, Any] = {
        "dialect": dialect_name,
        "migrated": False,
        "added_columns": {},
        "notes": [],
    }

    if dialect_name != "sqlite":
        result["notes"].append("非 SQLite 数据库，跳过轻量补列迁移。")
        return result

    upload_task_columns = [
        ("progress_percent", "INTEGER DEFAULT 0"),
        ("current_stage", "VARCHAR(128)"),
        ("queue_position", "INTEGER"),
        ("message", "TEXT"),
    ]
    llm_result_columns = [
        ("prompt_version", "VARCHAR(64)"),
        ("analysis_stage", "VARCHAR(32)"),
    ]
    normalized_event_columns = [
        ("cycle_inferred", "BOOLEAN DEFAULT 0"),
        ("cycle_infer_method", "VARCHAR(64)"),
        ("cycle_infer_confidence", "VARCHAR(16)"),
        ("cycle_infer_reason", "VARCHAR(128)"),
    ]
    step_summary_columns = [
        ("parameter_name", "VARCHAR(64)"),
    ]

    if _has_table(inspector, "upload_tasks"):
        added = _add_columns_if_missing(engine, "upload_tasks", upload_task_columns)
        if added:
            result["added_columns"]["upload_tasks"] = added
            result["migrated"] = True

    if _has_table(inspector, "llm_analysis_results"):
        added = _add_columns_if_missing(engine, "llm_analysis_results", llm_result_columns)
        if added:
            result["added_columns"]["llm_analysis_results"] = added
            result["migrated"] = True
    if _has_table(inspector, "normalized_events"):
        added = _add_columns_if_missing(engine, "normalized_events", normalized_event_columns)
        if added:
            result["added_columns"]["normalized_events"] = added
            result["migrated"] = True
    if _has_table(inspector, "step_summaries"):
        added = _add_columns_if_missing(engine, "step_summaries", step_summary_columns)
        if added:
            result["added_columns"]["step_summaries"] = added
            result["migrated"] = True

    _create_indexes_if_possible(engine)
    result["notes"].append("SQLite 轻量迁移已检查完成。")
    return result
