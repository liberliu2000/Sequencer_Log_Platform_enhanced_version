from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_reviewer_user
from app.db.session import get_db
from app.services.solution_catalog_service import SolutionCatalogService


router = APIRouter()


@router.get("/solution-repository/modules")
def list_solution_modules(include_inactive: bool = Query(default=False), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    items = SolutionCatalogService(db).list_modules(active_only=not include_inactive)
    return {"items": items, "total": len(items), "current_user": current_user}


@router.post("/solution-repository/modules")
def create_or_update_solution_module(payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(require_reviewer_user)):
    try:
        item = SolutionCatalogService(db).create_or_update_module(payload=payload, actor=str(current_user.get("username") or "reviewer"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "item": item}


@router.get("/solution-repository/task-clusters")
def list_task_clusters(
    include_pending: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    viewer_is_reviewer = bool(current_user.get("is_reviewer") or current_user.get("is_admin"))
    items = SolutionCatalogService(db).list_task_clusters(include_pending=include_pending and viewer_is_reviewer)
    return {"items": items, "total": len(items)}


@router.post("/solution-repository/task-clusters")
def create_task_cluster(payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    auto_approve = bool(current_user.get("is_reviewer") or current_user.get("is_admin"))
    try:
        item = SolutionCatalogService(db).create_task_cluster(
            display_name=str(payload.get("display_name") or ""),
            description=payload.get("description"),
            actor=str(current_user.get("username") or "user"),
            auto_approve=auto_approve,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "item": item}


@router.post("/solution-repository/task-clusters/{cluster_id}/review")
def review_task_cluster(cluster_id: int, payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(require_reviewer_user)):
    try:
        item = SolutionCatalogService(db).review_task_cluster(
            cluster_id=cluster_id,
            review_status=str(payload.get("review_status") or ""),
            actor=str(current_user.get("username") or "reviewer"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "item": item}
