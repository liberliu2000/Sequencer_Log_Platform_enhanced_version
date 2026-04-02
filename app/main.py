from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.auth_routes import router as auth_router
from app.api.dependencies import PUBLIC_API_PREFIXES, authenticate_request
from app.api.routes import router
from app.api.solution_meta_routes import router as solution_meta_router
from app.core.bootstrap_data import initialize_application_data
from app.core.logging_config import configure_logging
from app.core.settings import get_settings
from app.db.base import Base
from app.db.migrations import migrate_sqlite_schema
from app.db.session import engine
from app.models import db_models  # noqa: F401
from app.services.task_queue import queue
from app.web.landing import render_root_console

settings = get_settings()
configure_logging()
Base.metadata.create_all(bind=engine)
migrate_sqlite_schema(engine)
Base.metadata.create_all(bind=engine)
initialize_application_data()

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(solution_meta_router, prefix=settings.api_prefix)
app.mount("/web-assets", StaticFiles(directory=Path(__file__).resolve().parent / "web" / "static"), name="web-assets")


@app.get("/")
def root():
    return HTMLResponse(render_root_console(settings))


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.middleware("http")
async def auth_guard(request, call_next):
    path = request.url.path
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json"):
        return await call_next(request)
    if not path.startswith(settings.api_prefix):
        return await call_next(request)
    if path in PUBLIC_API_PREFIXES:
        return await call_next(request)

    user = authenticate_request(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期。"})
    request.state.current_user = user
    return await call_next(request)

queue.start()
