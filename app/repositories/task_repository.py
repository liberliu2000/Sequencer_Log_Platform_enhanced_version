from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.db_models import (
    ErrorClusterModel,
    LLMAnalysisResultModel,
    NormalizedEventModel,
    StepSummaryModel,
    TaskAuditLogModel,
    UploadTaskModel,
)


def _row_to_task_like(row: Any) -> SimpleNamespace:
    if isinstance(row, SimpleNamespace):
        return row
    if isinstance(row, dict):
        data = row
    elif hasattr(row, "_mapping"):
        data = dict(row._mapping)
    else:
        data = {
            "id": getattr(row, "id", None),
            "task_uuid": getattr(row, "task_uuid", None),
            "filename": getattr(row, "filename", None),
            "stored_path": getattr(row, "stored_path", None),
            "status": getattr(row, "status", None),
            "file_count": getattr(row, "file_count", 0),
            "total_events": getattr(row, "total_events", 0),
            "total_errors": getattr(row, "total_errors", 0),
            "progress_percent": getattr(row, "progress_percent", 0),
            "current_stage": getattr(row, "current_stage", None),
            "queue_position": getattr(row, "queue_position", None),
            "message": getattr(row, "message", None),
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
        }
    return SimpleNamespace(**data)


def _format_datetime_like(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_task(self, task_uuid: str, filename: str, stored_path: str) -> UploadTaskModel:
        task = UploadTaskModel(
            task_uuid=task_uuid,
            filename=filename,
            stored_path=stored_path,
            status="uploaded",
            progress_percent=0,
            current_stage="已上传",
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        self.add_audit_log(task.id, task_uuid, "upload_created", "success", "上传", f"文件: {filename}")
        return task

    def add_audit_log(
        self,
        task_id: int | None,
        task_uuid: str | None,
        action: str,
        status: str = "info",
        stage: str | None = None,
        detail: str | None = None,
        actor: str | None = None,
    ) -> None:
        self.db.add(
            TaskAuditLogModel(
                task_id=task_id,
                task_uuid=task_uuid,
                action=action,
                status=status,
                stage=stage,
                detail=detail,
                actor=actor,
            )
        )
        self.db.commit()

    def update_task_status(self, task_id: int, status: str, message: str | None = None) -> None:
        task = self.db.get(UploadTaskModel, task_id)
        if not task:
            return
        task.status = status
        task.message = message
        task.updated_at = datetime.utcnow()
        self.db.commit()

    def update_task_progress(
        self,
        task_id: int,
        status: str | None = None,
        progress_percent: int | None = None,
        current_stage: str | None = None,
        message: str | None = None,
        file_count: int | None = None,
        queue_position: int | None = None,
    ) -> None:
        task = self.db.get(UploadTaskModel, task_id)
        if not task:
            return
        if status is not None:
            task.status = status
        if progress_percent is not None:
            task.progress_percent = max(0, min(int(progress_percent), 100))
        if current_stage is not None:
            task.current_stage = current_stage
        if message is not None:
            task.message = message
        if file_count is not None:
            task.file_count = file_count
        if queue_position is not None:
            task.queue_position = queue_position
        task.updated_at = datetime.utcnow()
        self.db.commit()
        if current_stage or message:
            self.add_audit_log(task.id, task.task_uuid, "progress_update", "info", current_stage, message)

    def finalize_task(self, task_id: int, file_count: int, total_events: int, total_errors: int) -> None:
        task = self.db.get(UploadTaskModel, task_id)
        if not task:
            return
        task.status = "completed"
        task.file_count = file_count
        task.total_events = total_events
        task.total_errors = total_errors
        task.progress_percent = 100
        task.queue_position = None
        task.current_stage = "已完成"
        task.updated_at = datetime.utcnow()
        self.db.commit()
        self.add_audit_log(task.id, task.task_uuid, "task_completed", "success", "完成", f"events={total_events}, errors={total_errors}")

    def _fallback_task_select_sql(self, where_clause: str = "", limit_clause: str = "") -> str:
        return f"""
            SELECT
                id,
                task_uuid,
                filename,
                stored_path,
                status,
                file_count,
                total_events,
                total_errors,
                COALESCE(progress_percent, 0) AS progress_percent,
                current_stage,
                COALESCE(queue_position, 0) AS queue_position,
                message,
                created_at,
                updated_at
            FROM upload_tasks
            {where_clause}
            ORDER BY created_at DESC
            {limit_clause}
        """

    def list_tasks(self) -> list[SimpleNamespace]:
        try:
            rows = list(self.db.scalars(select(UploadTaskModel).order_by(UploadTaskModel.created_at.desc())))
            return [_row_to_task_like(r) for r in rows]
        except OperationalError as exc:
            msg = str(exc).lower()
            if any(tok in msg for tok in ["no such column", "queue_position", "progress_percent", "current_stage", "message"]):
                rows = self.db.execute(text(self._fallback_task_select_sql())).mappings().all()
                return [_row_to_task_like(r) for r in rows]
            raise

    def get_task_by_uuid(self, task_uuid: str) -> SimpleNamespace | None:
        try:
            row = self.db.scalar(select(UploadTaskModel).where(UploadTaskModel.task_uuid == task_uuid))
            return _row_to_task_like(row) if row else None
        except OperationalError as exc:
            msg = str(exc).lower()
            if any(tok in msg for tok in ["no such column", "queue_position", "progress_percent", "current_stage", "message"]):
                rows = self.db.execute(
                    text(self._fallback_task_select_sql(where_clause="WHERE task_uuid = :task_uuid", limit_clause="LIMIT 1")),
                    {"task_uuid": task_uuid},
                ).mappings().all()
                return _row_to_task_like(rows[0]) if rows else None
            raise

    def save_events(self, task_id: int, events: list[NormalizedEventModel]) -> None:
        for e in events:
            e.task_id = task_id
        self.db.add_all(events)
        self.db.commit()

    def save_step_summaries(self, task_id: int, steps: list[StepSummaryModel]) -> None:
        self.db.query(StepSummaryModel).filter(StepSummaryModel.task_id == task_id).delete()
        for s in steps:
            s.task_id = task_id
        self.db.add_all(steps)
        self.db.commit()

    def replace_error_clusters(self, task_id: int, rows: list[ErrorClusterModel]) -> None:
        self.db.query(ErrorClusterModel).filter(ErrorClusterModel.task_id == task_id).delete()
        for row in rows:
            row.task_id = task_id
        self.db.add_all(rows)
        self.db.commit()

    def save_llm_result(self, row: LLMAnalysisResultModel) -> None:
        self.db.add(row)
        self.db.commit()

    def get_dashboard_counts(self, task_id: int) -> dict:
        total_events = self.db.scalar(select(func.count()).select_from(NormalizedEventModel).where(NormalizedEventModel.task_id == task_id)) or 0
        total_errors = self.db.scalar(select(func.count()).select_from(NormalizedEventModel).where(NormalizedEventModel.task_id == task_id, NormalizedEventModel.normalized_signature.is_not(None))) or 0
        unique_errors = self.db.scalar(select(func.count(func.distinct(NormalizedEventModel.normalized_signature))).where(NormalizedEventModel.task_id == task_id, NormalizedEventModel.normalized_signature.is_not(None))) or 0
        return {"total_events": total_events, "total_errors": total_errors, "unique_error_count": unique_errors}

    def get_latest_llm_result(self, task_id: int, normalized_signature: str) -> LLMAnalysisResultModel | None:
        stmt = select(LLMAnalysisResultModel).where(LLMAnalysisResultModel.task_id == task_id, LLMAnalysisResultModel.normalized_signature == normalized_signature).order_by(LLMAnalysisResultModel.created_at.desc())
        return self.db.scalar(stmt)

    def list_llm_results(self, task_id: int) -> list[LLMAnalysisResultModel]:
        return list(self.db.scalars(select(LLMAnalysisResultModel).where(LLMAnalysisResultModel.task_id == task_id).order_by(LLMAnalysisResultModel.created_at.desc())))

    def list_audit_logs(self, task_id: int, limit: int = 200) -> list[TaskAuditLogModel]:
        stmt = select(TaskAuditLogModel).where(TaskAuditLogModel.task_id == task_id).order_by(TaskAuditLogModel.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def delete_task_by_uuid(self, task_uuid: str) -> bool:
        task = self.get_task_by_uuid(task_uuid)
        if not task:
            return False

        self.add_audit_log(None, task_uuid, "task_deleted", "success", "删除", "删除项目及相关记录")

        task_id = task.id
        stored_path = getattr(task, "stored_path", None)

        self.db.query(LLMAnalysisResultModel).filter(LLMAnalysisResultModel.task_id == task_id).delete()
        self.db.query(ErrorClusterModel).filter(ErrorClusterModel.task_id == task_id).delete()
        self.db.query(StepSummaryModel).filter(StepSummaryModel.task_id == task_id).delete()
        self.db.query(NormalizedEventModel).filter(NormalizedEventModel.task_id == task_id).delete()
        self.db.query(TaskAuditLogModel).filter(TaskAuditLogModel.task_id == task_id).delete()

        orm_task = self.db.get(UploadTaskModel, task_id)
        if orm_task:
            self.db.delete(orm_task)
        else:
            self.db.execute(text("DELETE FROM upload_tasks WHERE id = :task_id"), {"task_id": task_id})
        self.db.commit()

        try:
            if stored_path:
                path = Path(stored_path)
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
        return True

    def get_task_overview(self) -> dict:
        tasks = self.list_tasks()
        processing_status = {"uploaded", "queued", "processing"}
        completed_status = {"completed"}
        failed_status = {"failed", "error"}
        processing_tasks = [t for t in tasks if t.status in processing_status]
        completed_tasks = [t for t in tasks if t.status in completed_status]
        failed_tasks = [t for t in tasks if t.status in failed_status]

        def to_dict(t: Any) -> dict:
            created_at = getattr(t, "created_at", None)
            updated_at = getattr(t, "updated_at", None)
            return {
                "task_uuid": getattr(t, "task_uuid", ""),
                "filename": getattr(t, "filename", ""),
                "status": getattr(t, "status", ""),
                "file_count": getattr(t, "file_count", 0),
                "total_events": getattr(t, "total_events", 0),
                "total_errors": getattr(t, "total_errors", 0),
                "progress_percent": getattr(t, "progress_percent", 0),
                "current_stage": getattr(t, "current_stage", None),
                "queue_position": getattr(t, "queue_position", None),
                "message": getattr(t, "message", None),
                "created_at": _format_datetime_like(created_at),
                "updated_at": _format_datetime_like(updated_at),
            }

        return {
            "total_projects": len(tasks),
            "processing_projects": len(processing_tasks),
            "completed_projects": len(completed_tasks),
            "failed_projects": len(failed_tasks),
            "latest_projects": [to_dict(t) for t in tasks[:20]],
            "processing_details": [to_dict(t) for t in processing_tasks[:10]],
        }
