from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.db_models import (
    ErrorClusterModel,
    LLMAnalysisResultModel,
    NormalizedEventModel,
    ParameterResultModel,
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

    @staticmethod
    def _iter_chunks(items: Iterable[Any], batch_size: int) -> Iterable[list[Any]]:
        batch: list[Any] = []
        for item in items:
            batch.append(item)
            if len(batch) >= max(1, int(batch_size)):
                yield batch
                batch = []
        if batch:
            yield batch

    @staticmethod
    def _iter_insert_mappings(
        rows: Iterable[Any],
        *,
        task_id: int,
        field_names: tuple[str, ...],
    ) -> Iterable[dict[str, Any]]:
        for row in rows:
            if isinstance(row, dict):
                mapping = {key: row.get(key) for key in field_names if key in row}
            else:
                mapping = {key: getattr(row, key, None) for key in field_names}
            for key, value in list(mapping.items()):
                if isinstance(value, (dict, list)) and (key.endswith("_json") or key.endswith("_evidence")):
                    mapping[key] = json.dumps(value, ensure_ascii=False, default=str)
            mapping["task_id"] = task_id
            yield mapping

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
        self.db.flush()
        self.db.add(
            TaskAuditLogModel(
                task_id=task.id,
                task_uuid=task_uuid,
                action="upload_created",
                status="success",
                stage="上传",
                detail=f"文件: {filename}",
            )
        )
        self.db.commit()
        self.db.refresh(task)
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
        audit: bool = True,
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
        if audit and (current_stage or message):
            self.db.add(
                TaskAuditLogModel(
                    task_id=task.id,
                    task_uuid=task.task_uuid,
                    action="progress_update",
                    status="info",
                    stage=current_stage,
                    detail=message,
                )
            )
        self.db.commit()

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
        self.db.add(
            TaskAuditLogModel(
                task_id=task.id,
                task_uuid=task.task_uuid,
                action="task_completed",
                status="success",
                stage="完成",
                detail=f"events={total_events}, errors={total_errors}",
            )
        )
        self.db.commit()

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

    def save_events(self, task_id: int, events: Iterable[NormalizedEventModel | dict[str, Any]], batch_size: int = 1000) -> None:
        field_names = tuple(column.name for column in NormalizedEventModel.__table__.columns if column.name != "id")
        for batch in self._iter_chunks(
            self._iter_insert_mappings(events, task_id=task_id, field_names=field_names),
            batch_size,
        ):
            self.db.execute(insert(NormalizedEventModel), batch)
        self.db.commit()

    def save_step_summaries(self, task_id: int, steps: Iterable[StepSummaryModel | dict[str, Any]], batch_size: int = 1000) -> None:
        self.db.execute(delete(StepSummaryModel).where(StepSummaryModel.task_id == task_id))
        field_names = tuple(column.name for column in StepSummaryModel.__table__.columns if column.name != "id")
        for batch in self._iter_chunks(
            self._iter_insert_mappings(steps, task_id=task_id, field_names=field_names),
            batch_size,
        ):
            self.db.execute(insert(StepSummaryModel), batch)
        self.db.commit()

    def replace_error_clusters(self, task_id: int, rows: Iterable[ErrorClusterModel | dict[str, Any]], batch_size: int = 500) -> None:
        self.db.execute(delete(ErrorClusterModel).where(ErrorClusterModel.task_id == task_id))
        field_names = tuple(column.name for column in ErrorClusterModel.__table__.columns if column.name != "id")
        for batch in self._iter_chunks(
            self._iter_insert_mappings(rows, task_id=task_id, field_names=field_names),
            batch_size,
        ):
            self.db.execute(insert(ErrorClusterModel), batch)
        self.db.commit()

    def replace_parameter_results(
        self,
        task_id: int,
        rows: Iterable[ParameterResultModel | dict[str, Any]],
        batch_size: int = 500,
    ) -> None:
        self.db.execute(delete(ParameterResultModel).where(ParameterResultModel.task_id == task_id))
        field_names = tuple(column.name for column in ParameterResultModel.__table__.columns if column.name != "id")
        for batch in self._iter_chunks(
            self._iter_insert_mappings(rows, task_id=task_id, field_names=field_names),
            batch_size,
        ):
            self.db.execute(insert(ParameterResultModel), batch)
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
        self.db.query(ParameterResultModel).filter(ParameterResultModel.task_id == task_id).delete()
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
