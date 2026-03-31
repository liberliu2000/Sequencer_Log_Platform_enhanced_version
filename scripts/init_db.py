from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.core.bootstrap import bootstrap_for_local_run
    from app.core.bootstrap_data import initialize_application_data

    PROJECT_ROOT = bootstrap_for_local_run()

    from app.db.base import Base  # noqa: E402
    from app.db.migrations import migrate_sqlite_schema  # noqa: E402
    from app.db.session import engine  # noqa: E402
    from app.models import db_models  # noqa: F401,E402
except ModuleNotFoundError as exc:
    missing_package = str(getattr(exc, "name", "") or "unknown")
    raise SystemExit(
        "\n".join(
            [
                f"缺少 Python 依赖：{missing_package}",
                f"当前解释器：{sys.executable}",
                "请先安装项目依赖，或使用仓库虚拟环境执行：",
                "  .venv\\Scripts\\python.exe -m pip install -r requirements.txt",
                "  .venv\\Scripts\\python.exe -m scripts.init_db",
            ]
        )
    ) from exc


def init_and_migrate() -> None:
    Base.metadata.create_all(bind=engine)
    migration_result = migrate_sqlite_schema(engine)
    Base.metadata.create_all(bind=engine)
    initialize_application_data()
    print("DB initialized successfully.")
    print(f"project_root={PROJECT_ROOT}")
    print(f"migration={migration_result}")


if __name__ == "__main__":
    init_and_migrate()
