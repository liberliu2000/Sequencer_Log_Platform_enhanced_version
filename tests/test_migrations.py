from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.migrations import migrate_sqlite_schema
from app.models.db_models import SolutionRecordModel


def _build_engine(tmp_path):
    db_path = tmp_path / "migration-test.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(bind=engine)
    return engine


def _insert_solution_record(engine, *, error_name: str, message: str) -> int:
    with Session(engine) as db:
        row = SolutionRecordModel(
            error_name=error_name,
            module="database",
            message=message,
            review_status="approved",
            reusable=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)


def test_migrate_sqlite_schema_reuses_existing_solution_fts_index(tmp_path):
    engine = _build_engine(tmp_path)
    solution_id = _insert_solution_record(engine, error_name="Timeout", message="upstream timeout")

    first_result = migrate_sqlite_schema(engine)

    assert first_result["fts"]["exists"] is True
    assert first_result["fts"]["reindexed"] is True
    assert first_result["fts"]["solution_count"] == 1
    assert first_result["fts"]["fts_count"] == 1

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE solution_search_fts SET search_text = 'sentinel' WHERE solution_id = :solution_id"),
            {"solution_id": solution_id},
        )

    second_result = migrate_sqlite_schema(engine)

    assert second_result["fts"]["exists"] is True
    assert second_result["fts"]["reindexed"] is False
    assert second_result["migrated"] is False

    with engine.begin() as conn:
        persisted_text = conn.execute(
            text("SELECT search_text FROM solution_search_fts WHERE solution_id = :solution_id"),
            {"solution_id": solution_id},
        ).scalar_one()

    assert persisted_text == "sentinel"


def test_migrate_sqlite_schema_rebuilds_solution_fts_when_counts_drift(tmp_path):
    engine = _build_engine(tmp_path)
    solution_id = _insert_solution_record(engine, error_name="Timeout", message="upstream timeout")
    migrate_sqlite_schema(engine)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM solution_search_fts WHERE solution_id = :solution_id"),
            {"solution_id": solution_id},
        )

    result = migrate_sqlite_schema(engine)

    assert result["fts"]["exists"] is True
    assert result["fts"]["reindexed"] is True
    assert result["fts"]["solution_count"] == 1
    assert result["fts"]["fts_count"] == 1

    with engine.begin() as conn:
        restored_text = conn.execute(
            text("SELECT search_text FROM solution_search_fts WHERE solution_id = :solution_id"),
            {"solution_id": solution_id},
        ).scalar_one()

    assert "upstream timeout" in restored_text
