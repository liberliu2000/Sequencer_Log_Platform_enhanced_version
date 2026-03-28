from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.db_models import SolutionRecordModel

MODULE_PREFIXES: dict[str, str] = {
    "流路系统": "FL",
    "光学系统": "OP",
    "运动平台": "MP",
    "温控系统": "TC",
    "调度系统": "SC",
    "数据算法": "DA",
    "软件控制": "SW",
    "硬件电气": "HE",
    "其他子模块": "OT",
}

MODULE_TREE: list[dict[str, Any]] = [
    {"name": "流路系统", "children": ["泵阀控制", "试剂通道", "清洗流程"]},
    {"name": "光学系统", "children": ["激发链路", "成像链路", "光源控制"]},
    {"name": "运动平台", "children": ["XYZ 平台", "夹具机构", "对位机构"]},
    {"name": "温控系统", "children": ["温区控制", "加热冷却", "传感器采样"]},
    {"name": "调度系统", "children": ["任务编排", "流程调度", "资源协调"]},
    {"name": "数据算法", "children": ["识别算法", "校准算法", "统计分析"]},
    {"name": "软件控制", "children": ["接口协议", "状态机", "异常处理"]},
    {"name": "硬件电气", "children": ["IO 控制", "板卡通信", "电源安全"]},
    {"name": "其他子模块", "children": ["自定义模块"]},
]


def _json_dump(data: Any) -> str | None:
    if data in (None, "", [], {}):
        return None
    return json.dumps(data, ensure_ascii=False)


def _json_load(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text


def _preview_text(value: str | None, limit: int = 160) -> str | None:
    if not value:
        return value
    text = " ".join(str(value).split())
    return text[:limit]


class SolutionRepositoryService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def module_tree(self) -> list[dict[str, Any]]:
        return MODULE_TREE

    def module_prefixes(self) -> dict[str, str]:
        return MODULE_PREFIXES

    def validate_case_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload or {})
        module = str(data.get("module") or "").strip()
        if not module:
            raise ValueError("module 不能为空")
        if module not in MODULE_PREFIXES:
            raise ValueError(f"module 不在已配置模块列表中: {module}")
        error_name = str(data.get("error_name") or "").strip()
        if not error_name:
            raise ValueError("error_name 不能为空")

        error_code = str(data.get("error_code") or "").strip() or None
        prefix = MODULE_PREFIXES[module]
        if error_code and not error_code.upper().startswith(prefix):
            raise ValueError(f"错误码 {error_code} 不符合模块前缀规范，应以 {prefix} 开头")

        normalized_signature = str(data.get("normalized_signature") or "").strip() or None
        message = str(data.get("message") or "").strip() or None
        if not normalized_signature and not message and not error_code:
            raise ValueError("normalized_signature、message、error_code 至少提供一个")

        reusable = data.get("reusable", True)
        if isinstance(reusable, str):
            reusable = reusable.strip().lower() not in {"false", "0", "no", "n"}

        result = {
            "error_name": error_name,
            "error_category": str(data.get("error_category") or "").strip() or None,
            "module": module,
            "submodule": str(data.get("submodule") or "").strip() or None,
            "error_code": error_code,
            "error_code_prefix": prefix,
            "message": message,
            "normalized_signature": normalized_signature,
            "exception_description": str(data.get("exception_description") or "").strip() or None,
            "trigger_scenario": str(data.get("trigger_scenario") or "").strip() or None,
            "impact_scope": str(data.get("impact_scope") or "").strip() or None,
            "report_source": str(data.get("report_source") or "").strip() or None,
            "related_logs": _json_dump(data.get("related_logs")),
            "related_source_files": _json_dump(data.get("related_source_files")),
            "root_cause_analysis": str(data.get("root_cause_analysis") or "").strip() or None,
            "verified_solution": str(data.get("verified_solution") or "").strip() or None,
            "workaround": str(data.get("workaround") or "").strip() or None,
            "owner_department": str(data.get("owner_department") or "").strip() or None,
            "submitter": str(data.get("submitter") or "").strip() or None,
            "source": str(data.get("source") or "").strip() or None,
            "review_status": str(data.get("review_status") or "approved").strip() or "approved",
            "reusable": bool(reusable),
            "similar_case_refs": _json_dump(data.get("similar_case_refs")),
            "metadata_json": _json_dump(data.get("metadata")),
        }
        return result

    def create_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.validate_case_payload(payload)
        now = datetime.utcnow()
        row = SolutionRecordModel(**data, created_at=now, updated_at=now)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self.serialize(row)

    def update_record(self, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.db.get(SolutionRecordModel, record_id)
        if not row:
            raise KeyError("solution record not found")
        data = self.validate_case_payload({**self.serialize(row), **payload})
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return self.serialize(row)

    def get_record(self, record_id: int) -> dict[str, Any]:
        row = self.db.get(SolutionRecordModel, record_id)
        if not row:
            raise KeyError("solution record not found")
        return self.serialize(row)

    def list_records(
        self,
        *,
        module: str | None = None,
        submodule: str | None = None,
        error_code: str | None = None,
        message: str | None = None,
        normalized_signature: str | None = None,
        trigger_scenario: str | None = None,
        reusable: bool | None = None,
        review_status: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(SolutionRecordModel).order_by(SolutionRecordModel.updated_at.desc(), SolutionRecordModel.id.desc())
        if module:
            stmt = stmt.where(SolutionRecordModel.module == module)
        if submodule:
            stmt = stmt.where(SolutionRecordModel.submodule == submodule)
        if error_code:
            stmt = stmt.where(SolutionRecordModel.error_code.contains(error_code))
        if message:
            stmt = stmt.where(SolutionRecordModel.message.contains(message))
        if normalized_signature:
            stmt = stmt.where(SolutionRecordModel.normalized_signature == normalized_signature)
        if trigger_scenario:
            stmt = stmt.where(SolutionRecordModel.trigger_scenario.contains(trigger_scenario))
        if reusable is not None:
            stmt = stmt.where(SolutionRecordModel.reusable == bool(reusable))
        if review_status:
            stmt = stmt.where(SolutionRecordModel.review_status == review_status)
        if search:
            stmt = stmt.where(
                or_(
                    SolutionRecordModel.error_name.contains(search),
                    SolutionRecordModel.message.contains(search),
                    SolutionRecordModel.normalized_signature.contains(search),
                    SolutionRecordModel.error_code.contains(search),
                    SolutionRecordModel.trigger_scenario.contains(search),
                    SolutionRecordModel.root_cause_analysis.contains(search),
                    SolutionRecordModel.verified_solution.contains(search),
                )
            )
        rows = list(self.db.scalars(stmt.limit(max(1, min(limit, 500)))))
        return [self.serialize(row) for row in rows]

    def serialize(self, row: SolutionRecordModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "error_name": row.error_name,
            "error_category": row.error_category,
            "module": row.module,
            "submodule": row.submodule,
            "error_code": row.error_code,
            "error_code_prefix": row.error_code_prefix,
            "message": row.message,
            "normalized_signature": row.normalized_signature,
            "exception_description": row.exception_description,
            "trigger_scenario": row.trigger_scenario,
            "impact_scope": row.impact_scope,
            "report_source": row.report_source,
            "related_logs": _json_load(row.related_logs),
            "related_source_files": _json_load(row.related_source_files),
            "root_cause_analysis": row.root_cause_analysis,
            "verified_solution": row.verified_solution,
            "workaround": row.workaround,
            "owner_department": row.owner_department,
            "submitter": row.submitter,
            "source": row.source,
            "review_status": row.review_status,
            "reusable": row.reusable,
            "similar_case_refs": _json_load(row.similar_case_refs),
            "metadata": _json_load(row.metadata_json),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "trigger_scenario_summary": _preview_text(row.trigger_scenario),
            "root_cause_summary": _preview_text(row.root_cause_analysis),
            "solution_summary": _preview_text(row.verified_solution),
        }

    def export_records(self, export_format: str = "json") -> str:
        rows = self.list_records(limit=5000)
        export_dir = Path(self.settings.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        export_format = export_format.lower()

        if export_format == "json":
            path = export_dir / f"solution_repository_{timestamp}.json"
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            return str(path)

        if export_format == "csv":
            path = export_dir / f"solution_repository_{timestamp}.csv"
            self._write_csv(path, rows)
            return str(path)

        if export_format in {"xlsx", "excel"}:
            from openpyxl import Workbook

            path = export_dir / f"solution_repository_{timestamp}.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "solutions"
            self._write_sheet(ws, rows)
            wb.save(path)
            return str(path)

        if export_format == "sqlite":
            path = export_dir / f"solution_repository_{timestamp}.sqlite"
            self._write_sqlite_backup(path, rows)
            return str(path)

        raise ValueError(f"unsupported export format: {export_format}")

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: SolutionRepositoryService._export_value(v) for k, v in row.items()})

    @staticmethod
    def _write_sheet(ws, rows: list[dict[str, Any]]) -> None:
        if not rows:
            ws.append(["empty"])
            return
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([SolutionRepositoryService._export_value(row.get(h)) for h in headers])

    @staticmethod
    def _write_sqlite_backup(path: Path, rows: list[dict[str, Any]]) -> None:
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """
                CREATE TABLE solution_records (
                    id INTEGER,
                    error_name TEXT,
                    error_category TEXT,
                    module TEXT,
                    submodule TEXT,
                    error_code TEXT,
                    error_code_prefix TEXT,
                    message TEXT,
                    normalized_signature TEXT,
                    exception_description TEXT,
                    trigger_scenario TEXT,
                    impact_scope TEXT,
                    report_source TEXT,
                    related_logs TEXT,
                    related_source_files TEXT,
                    root_cause_analysis TEXT,
                    verified_solution TEXT,
                    workaround TEXT,
                    owner_department TEXT,
                    submitter TEXT,
                    source TEXT,
                    review_status TEXT,
                    reusable INTEGER,
                    similar_case_refs TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            if rows:
                headers = list(rows[0].keys())
                columns = [h for h in headers if h != "trigger_scenario_summary" and h != "root_cause_summary" and h != "solution_summary"]
                placeholders = ",".join("?" for _ in columns)
                conn.executemany(
                    f"INSERT INTO solution_records ({','.join(columns)}) VALUES ({placeholders})",
                    [[SolutionRepositoryService._export_value(row.get(col)) for col in columns] for row in rows],
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _export_value(value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)
