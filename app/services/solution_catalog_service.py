from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.db_models import ModuleConfigModel, TaskClusterModel


SYSTEM_MODULES: list[dict[str, str]] = [
    {"module_key": "optics", "display_name": "optics / 光学", "prefix": "OP", "description": "光学链路、成像与激发相关问题"},
    {"module_key": "fluidics", "display_name": "fluidics / 流路", "prefix": "FL", "description": "流路、阀体、试剂与管路相关问题"},
    {"module_key": "motion_control", "display_name": "motion_control / 运动控制", "prefix": "MC", "description": "运动平台、驱动与执行机构相关问题"},
    {"module_key": "scheduler", "display_name": "scheduler / 调度", "prefix": "SC", "description": "任务编排、调度状态机相关问题"},
    {"module_key": "algorithm", "display_name": "algorithm / 算法", "prefix": "AL", "description": "识别、分析与算法处理相关问题"},
    {"module_key": "ui", "display_name": "ui / 界面", "prefix": "UI", "description": "前端界面、交互与可视化相关问题"},
    {"module_key": "database", "display_name": "database / 数据库", "prefix": "DB", "description": "数据库、存储与索引相关问题"},
    {"module_key": "other", "display_name": "other / 其他", "prefix": "OT", "description": "暂未归类或跨模块问题"},
]

SYSTEM_TASK_CLUSTERS: list[dict[str, str]] = [
    {"cluster_key": "system_bootstrap", "display_name": "系统启动", "description": "开机、自检、初始化与启动链路"},
    {"cluster_key": "sample_loading", "display_name": "样本装载", "description": "样本放置、识别、装载与前处理"},
    {"cluster_key": "run_execution", "display_name": "流程执行", "description": "主流程运行、任务推进与过程控制"},
    {"cluster_key": "calibration_alignment", "display_name": "校准对位", "description": "对位、校准、标定与定位链路"},
    {"cluster_key": "data_processing", "display_name": "数据处理", "description": "识别分析、结果计算与数据转换"},
    {"cluster_key": "report_export", "display_name": "结果导出", "description": "报表生成、导出与归档"},
]


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "cluster"


class SolutionCatalogService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_defaults(self) -> None:
        now = utcnow()
        for item in SYSTEM_MODULES:
            existing = self.db.scalar(select(ModuleConfigModel).where(ModuleConfigModel.module_key == item["module_key"]))
            if existing:
                if existing.is_active is False:
                    existing.is_active = True
                    existing.updated_at = now
                continue
            self.db.add(
                ModuleConfigModel(
                    module_key=item["module_key"],
                    display_name=item["display_name"],
                    prefix=item["prefix"],
                    description=item["description"],
                    is_active=True,
                    is_system=True,
                    created_by="system",
                    updated_by="system",
                    created_at=now,
                    updated_at=now,
                )
            )

        for item in SYSTEM_TASK_CLUSTERS:
            existing = self.db.scalar(select(TaskClusterModel).where(TaskClusterModel.cluster_key == item["cluster_key"]))
            if existing:
                if existing.review_status != "approved" or existing.is_active is False:
                    existing.review_status = "approved"
                    existing.is_active = True
                    existing.updated_at = now
                continue
            self.db.add(
                TaskClusterModel(
                    cluster_key=item["cluster_key"],
                    display_name=item["display_name"],
                    description=item["description"],
                    review_status="approved",
                    is_active=True,
                    is_system=True,
                    created_by="system",
                    reviewed_by="system",
                    reviewed_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        self.db.commit()

    def serialize_module(self, row: ModuleConfigModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "module_key": row.module_key,
            "display_name": row.display_name,
            "prefix": row.prefix,
            "description": row.description,
            "is_active": row.is_active,
            "is_system": row.is_system,
            "created_by": row.created_by,
            "updated_by": row.updated_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def serialize_task_cluster(self, row: TaskClusterModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "cluster_key": row.cluster_key,
            "display_name": row.display_name,
            "description": row.description,
            "review_status": row.review_status,
            "is_active": row.is_active,
            "is_system": row.is_system,
            "created_by": row.created_by,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def list_modules(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        stmt = select(ModuleConfigModel).order_by(ModuleConfigModel.prefix.asc(), ModuleConfigModel.display_name.asc())
        if active_only:
            stmt = stmt.where(ModuleConfigModel.is_active.is_(True))
        return [self.serialize_module(row) for row in self.db.scalars(stmt)]

    def list_task_clusters(self, *, include_pending: bool = False) -> list[dict[str, Any]]:
        stmt = select(TaskClusterModel).order_by(TaskClusterModel.display_name.asc(), TaskClusterModel.id.asc())
        if not include_pending:
            stmt = stmt.where(TaskClusterModel.review_status == "approved", TaskClusterModel.is_active.is_(True))
        return [self.serialize_task_cluster(row) for row in self.db.scalars(stmt)]

    def resolve_module(self, module_value: str) -> ModuleConfigModel:
        text = str(module_value or "").strip()
        if not text:
            raise ValueError("module 不能为空。")
        stmt = select(ModuleConfigModel).where(
            or_(
                ModuleConfigModel.module_key == text,
                ModuleConfigModel.display_name == text,
                ModuleConfigModel.prefix == text.upper(),
            )
        )
        row = self.db.scalar(stmt)
        if not row:
            raise ValueError(f"未找到模块配置: {text}")
        if not row.is_active:
            raise ValueError(f"模块已停用: {text}")
        return row

    def create_or_update_module(self, *, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        module_key = _slugify(str(payload.get("module_key") or payload.get("display_name") or ""))
        display_name = str(payload.get("display_name") or module_key).strip()
        prefix = str(payload.get("prefix") or "").strip().upper()
        if len(prefix) != 2:
            raise ValueError("模块前缀必须为 2 位大写字母。")
        now = utcnow()
        row = None
        if payload.get("id"):
            row = self.db.get(ModuleConfigModel, int(payload["id"]))
        if not row:
            row = self.db.scalar(select(ModuleConfigModel).where(ModuleConfigModel.module_key == module_key))
        if not row:
            row = ModuleConfigModel(
                module_key=module_key,
                display_name=display_name,
                prefix=prefix,
                description=str(payload.get("description") or "").strip() or None,
                is_active=bool(payload.get("is_active", True)),
                is_system=False,
                created_by=actor,
                updated_by=actor,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.display_name = display_name
            row.prefix = prefix
            row.description = str(payload.get("description") or "").strip() or None
            row.is_active = bool(payload.get("is_active", True))
            row.updated_by = actor
            row.updated_at = now
        self.db.commit()
        self.db.refresh(row)
        return self.serialize_module(row)

    def create_task_cluster(self, *, display_name: str, description: str | None, actor: str, auto_approve: bool) -> dict[str, Any]:
        display_name = str(display_name or "").strip()
        if len(display_name) < 2:
            raise ValueError("任务簇名称至少需要 2 个字符。")
        cluster_key = _slugify(display_name)
        existing = self.db.scalar(select(TaskClusterModel).where(TaskClusterModel.cluster_key == cluster_key))
        if existing:
            return self.serialize_task_cluster(existing)
        now = utcnow()
        row = TaskClusterModel(
            cluster_key=cluster_key,
            display_name=display_name,
            description=str(description or "").strip() or None,
            review_status="approved" if auto_approve else "pending_review",
            is_active=True,
            is_system=False,
            created_by=actor,
            reviewed_by=actor if auto_approve else None,
            reviewed_at=now if auto_approve else None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self.serialize_task_cluster(row)

    def review_task_cluster(self, *, cluster_id: int, review_status: str, actor: str) -> dict[str, Any]:
        row = self.db.get(TaskClusterModel, cluster_id)
        if not row:
            raise ValueError("任务簇不存在。")
        if review_status not in {"approved", "rejected", "disabled"}:
            raise ValueError("review_status 无效。")
        row.review_status = review_status
        row.is_active = review_status == "approved"
        row.reviewed_by = actor
        row.reviewed_at = utcnow()
        row.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(row)
        return self.serialize_task_cluster(row)
