from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.bootstrap import bootstrap_for_local_run

PROJECT_ROOT = bootstrap_for_local_run()

from app.db.base import Base  # noqa: E402
from app.db.migrations import migrate_sqlite_schema  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.models import db_models  # noqa: F401,E402


def init_and_migrate() -> None:
    Base.metadata.create_all(bind=engine)
    migration_result = migrate_sqlite_schema(engine)
    Base.metadata.create_all(bind=engine)
    print("DB initialized successfully.")
    print(f"project_root={PROJECT_ROOT}")
    print(f"migration={migration_result}")


if __name__ == "__main__":
    init_and_migrate()
