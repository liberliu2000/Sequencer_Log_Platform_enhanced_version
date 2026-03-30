from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.logging_config import configure_logging
from app.core.settings import get_settings
from app.db.base import Base
from app.db.migrations import migrate_sqlite_schema
from app.db.session import engine
from app.models import db_models  # noqa: F401
from app.services.task_queue import queue

settings = get_settings()
configure_logging()
Base.metadata.create_all(bind=engine)
migrate_sqlite_schema(engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)

queue.start()
