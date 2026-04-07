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
        "CREATE INDEX IF NOT EXISTS idx_normalized_events_task_side ON normalized_events(task_id, side_scope)",
        "CREATE INDEX IF NOT EXISTS idx_normalized_events_task_chip ON normalized_events(task_id, chip_name)",
        "CREATE INDEX IF NOT EXISTS idx_step_summaries_task_side ON step_summaries(task_id, side_scope)",
        "CREATE INDEX IF NOT EXISTS idx_parameter_results_task_side ON parameter_results(task_id, side_scope)",
        "CREATE INDEX IF NOT EXISTS idx_llm_results_task_sig ON llm_analysis_results(task_id, normalized_signature)",
        "CREATE INDEX IF NOT EXISTS idx_solution_records_review_status ON solution_records(review_status)",
        "CREATE INDEX IF NOT EXISTS idx_solution_records_submitter ON solution_records(submitter)",
        "CREATE INDEX IF NOT EXISTS idx_solution_records_error_name ON solution_records(error_name)",
        "CREATE INDEX IF NOT EXISTS idx_solution_records_created_updated ON solution_records(created_at, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_solution_task_links_task_uuid ON solution_task_links(task_uuid)",
        "CREATE INDEX IF NOT EXISTS idx_solution_task_links_signature ON solution_task_links(normalized_signature)",
        "CREATE INDEX IF NOT EXISTS idx_solution_module_links_module_key ON solution_module_links(module_key)",
        "CREATE INDEX IF NOT EXISTS idx_solution_keyword_keyword ON solution_message_keywords(keyword)",
        "CREATE INDEX IF NOT EXISTS idx_task_clusters_status ON task_clusters(review_status)",
        "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)",
        "CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email_verified)",
        "CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_announcements_updated_at ON announcements(updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_announcements_pinned ON announcements(is_pinned)",
        "CREATE INDEX IF NOT EXISTS idx_email_codes_expires ON email_verification_codes(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_registration_challenges_email ON registration_challenges(email)",
        "CREATE INDEX IF NOT EXISTS idx_registration_challenges_verified ON registration_challenges(verified_at)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass


def _table_row_count(conn, table_name: str) -> int:
    try:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)
    except Exception:
        return 0


def _create_solution_search_fts(engine: Engine) -> dict[str, Any]:
    if engine.dialect.name.lower() != "sqlite":
        return {"exists": False, "reindexed": False, "solution_count": 0, "fts_count": 0}
    with engine.begin() as conn:
        inspector = inspect(conn)
        existed_before = _has_table(inspector, "solution_search_fts")
        try:
            conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS solution_search_fts
                    USING fts5(solution_id UNINDEXED, search_text)
                    """
                )
            )
        except Exception:
            return {"exists": False, "reindexed": False, "solution_count": 0, "fts_count": 0}

        solution_count = _table_row_count(conn, "solution_records")
        fts_count = _table_row_count(conn, "solution_search_fts")
        should_reindex = (not existed_before) or (solution_count != fts_count)

        if should_reindex:
            conn.execute(text("DELETE FROM solution_search_fts"))
            if solution_count > 0:
                conn.execute(
                    text(
                        """
                        INSERT INTO solution_search_fts(solution_id, search_text)
                        SELECT
                            id,
                            trim(
                                coalesce(error_name, '') || ' ' ||
                                coalesce(error_code, '') || ' ' ||
                                coalesce(module, '') || ' ' ||
                                coalesce(message, '') || ' ' ||
                                coalesce(trigger_scenario, '') || ' ' ||
                                coalesce(root_cause_analysis, '') || ' ' ||
                                coalesce(verified_solution, '') || ' ' ||
                                coalesce(submitter, '') || ' ' ||
                                coalesce(review_status, '')
                            )
                        FROM solution_records
                        """
                    )
                )
            fts_count = _table_row_count(conn, "solution_search_fts")

        return {
            "exists": True,
            "reindexed": should_reindex,
            "solution_count": solution_count,
            "fts_count": fts_count,
        }


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
        ("instrument_scope", "VARCHAR(128)"),
        ("side_scope", "VARCHAR(32)"),
        ("side_group", "VARCHAR(32)"),
        ("chip_position", "VARCHAR(32)"),
        ("chuck_no", "VARCHAR(32)"),
        ("slot_no", "VARCHAR(32)"),
        ("stage_key", "VARCHAR(32)"),
        ("side_confidence", "FLOAT"),
        ("side_evidence", "TEXT"),
    ]
    step_summary_columns = [
        ("parameter_name", "VARCHAR(64)"),
        ("instrument_scope", "VARCHAR(128)"),
        ("side_scope", "VARCHAR(32)"),
        ("side_group", "VARCHAR(32)"),
        ("chip_position", "VARCHAR(32)"),
        ("chuck_no", "VARCHAR(32)"),
        ("slot_no", "VARCHAR(32)"),
        ("stage_key", "VARCHAR(32)"),
        ("side_confidence", "FLOAT"),
        ("side_evidence", "TEXT"),
    ]
    parameter_result_columns = [
        ("instrument_scope", "VARCHAR(128)"),
        ("side_scope", "VARCHAR(32)"),
        ("side_group", "VARCHAR(32)"),
        ("chip_position", "VARCHAR(32)"),
        ("chuck_no", "VARCHAR(32)"),
        ("slot_no", "VARCHAR(32)"),
        ("stage_key", "VARCHAR(32)"),
        ("side_confidence", "FLOAT"),
        ("side_evidence", "TEXT"),
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
    if _has_table(inspector, "parameter_results"):
        added = _add_columns_if_missing(engine, "parameter_results", parameter_result_columns)
        if added:
            result["added_columns"]["parameter_results"] = added
            result["migrated"] = True

    _create_indexes_if_possible(engine)
    fts_status = _create_solution_search_fts(engine)
    if fts_status.get("exists"):
        result["fts"] = fts_status
        if fts_status.get("reindexed"):
            result["migrated"] = True
    result["notes"].append("SQLite 轻量迁移已检查完成。")
    return result
