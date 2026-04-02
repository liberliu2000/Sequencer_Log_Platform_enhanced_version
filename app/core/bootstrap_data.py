from __future__ import annotations

from app.db.session import SessionLocal
from app.services.auth_service import AuthService
from app.services.solution_catalog_service import SolutionCatalogService


def initialize_application_data() -> None:
    db = SessionLocal()
    try:
        SolutionCatalogService(db).ensure_defaults()
        AuthService(db).ensure_default_admin()
    finally:
        db.close()
