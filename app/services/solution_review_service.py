from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.models.db_models import SolutionReviewRecordModel
from app.schemas.common import SolutionReviewResult
from app.services.solution_repository import SolutionRepositoryService


def _json_load(text: str | None, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


class SolutionReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = SolutionRepositoryService(db)
        self.client = LLMClient()

    def submit_for_review(
        self,
        payload: dict[str, Any],
        *,
        attachments: list[dict[str, Any]] | None = None,
        auto_store_if_approved: bool = True,
    ) -> dict[str, Any]:
        validation_errors = self._basic_validate(payload)
        if validation_errors:
            review = SolutionReviewResult(
                review_status="needs_revision",
                review_reason="基础校验未通过",
                revision_suggestions=validation_errors,
                completeness_score=0.35,
                reusability_score=0.25,
                clarity_score=0.3,
                llm_used=False,
            )
        else:
            review = self._review_with_llm(payload)

        now = datetime.utcnow()
        row = SolutionReviewRecordModel(
            task_uuid=str(payload.get("task_uuid") or "").strip() or None,
            normalized_signature=str(payload.get("normalized_signature") or "").strip() or None,
            module=str(payload.get("module") or "").strip() or None,
            submodule=str(payload.get("submodule") or "").strip() or None,
            submission_type=str(payload.get("submission_type") or "solution_record"),
            proposed_payload=json.dumps(payload, ensure_ascii=False),
            attachments_json=json.dumps(attachments or [], ensure_ascii=False),
            review_status=review.review_status,
            review_reason=review.review_reason,
            revision_suggestions=json.dumps(review.revision_suggestions, ensure_ascii=False),
            completeness_score=review.completeness_score,
            reusability_score=review.reusability_score,
            clarity_score=review.clarity_score,
            review_payload=json.dumps(review.model_dump(), ensure_ascii=False),
            review_history_json=json.dumps(
                [
                    {
                        "review_status": review.review_status,
                        "review_reason": review.review_reason,
                        "revision_suggestions": review.revision_suggestions,
                        "reviewed_by": "llm" if review.llm_used else "heuristic",
                        "reviewed_at": now.isoformat(),
                    }
                ],
                ensure_ascii=False,
            ),
            created_by=str(payload.get("submitter") or payload.get("created_by") or "").strip() or None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

        if review.review_status == "approved" and auto_store_if_approved:
            created = self.repository.create_record(payload)
            row.linked_solution_id = created["id"]
            row.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(row)

        return self.serialize(row)

    def list_reviews(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        stmt = select(SolutionReviewRecordModel).order_by(SolutionReviewRecordModel.updated_at.desc(), SolutionReviewRecordModel.id.desc())
        if status:
            stmt = stmt.where(SolutionReviewRecordModel.review_status == status)
        rows = list(self.db.scalars(stmt.limit(max(1, min(limit, 500)))))
        return [self.serialize(row) for row in rows]

    def manually_review(
        self,
        review_id: int,
        *,
        review_status: str,
        reviewer: str | None,
        notes: str | None,
        auto_store_if_approved: bool = True,
    ) -> dict[str, Any]:
        row = self.db.get(SolutionReviewRecordModel, review_id)
        if not row:
            raise KeyError("review record not found")
        if review_status not in {"approved", "needs_revision", "rejected"}:
            raise ValueError("invalid review_status")

        history = _json_load(row.review_history_json, [])
        history.append(
            {
                "review_status": review_status,
                "review_reason": notes or "",
                "revision_suggestions": [],
                "reviewed_by": reviewer or "manual",
                "reviewed_at": datetime.utcnow().isoformat(),
            }
        )
        row.review_status = review_status
        row.review_reason = notes or row.review_reason
        row.reviewed_by = reviewer
        row.review_history_json = json.dumps(history[-50:], ensure_ascii=False)
        row.updated_at = datetime.utcnow()

        payload = _json_load(row.proposed_payload, {})
        if review_status == "approved" and auto_store_if_approved and not row.linked_solution_id:
            created = self.repository.create_record(payload)
            row.linked_solution_id = created["id"]

        self.db.commit()
        self.db.refresh(row)
        return self.serialize(row)

    def serialize(self, row: SolutionReviewRecordModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "task_uuid": row.task_uuid,
            "normalized_signature": row.normalized_signature,
            "module": row.module,
            "submodule": row.submodule,
            "submission_type": row.submission_type,
            "proposed_payload": _json_load(row.proposed_payload, {}),
            "attachments": _json_load(row.attachments_json, []),
            "review_status": row.review_status,
            "review_reason": row.review_reason,
            "revision_suggestions": _json_load(row.revision_suggestions, []),
            "completeness_score": row.completeness_score,
            "reusability_score": row.reusability_score,
            "clarity_score": row.clarity_score,
            "review_payload": _json_load(row.review_payload, {}),
            "review_history": _json_load(row.review_history_json, []),
            "reviewed_by": row.reviewed_by,
            "linked_solution_id": row.linked_solution_id,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def _basic_validate(self, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        required = ["error_name", "module"]
        for field in required:
            if not str(payload.get(field) or "").strip():
                errors.append(f"{field} 不能为空")
        if not str(payload.get("message") or "").strip() and not str(payload.get("normalized_signature") or "").strip():
            errors.append("message 或 normalized_signature 至少填写一项")
        try:
            self.repository.validate_case_payload(payload)
        except Exception as exc:
            errors.append(str(exc))
        if str(payload.get("message") or "").strip() and len(str(payload.get("message") or "").strip()) < 6:
            errors.append("message 过于模糊，建议补充关键异常内容")
        if not str(payload.get("root_cause_analysis") or "").strip():
            errors.append("root_cause_analysis 为空，建议补充根因描述")
        if not str(payload.get("verified_solution") or "").strip():
            errors.append("verified_solution 为空，建议补充已验证解决方案")
        return list(dict.fromkeys(errors))

    def _review_with_llm(self, payload: dict[str, Any]) -> SolutionReviewResult:
        heuristic = self._heuristic_review(payload)
        if not self.client.enabled():
            return heuristic

        fallback = heuristic.model_dump()
        system_prompt = (
            "你是错误案例库审核助手。只返回 JSON，字段包括 "
            '{"review_status":"","review_reason":"","revision_suggestions":[],"completeness_score":0.0,"reusability_score":0.0,"clarity_score":0.0,"llm_used":true}'
        )
        user_prompt = (
            "请审核以下错误案例是否适合进入解决方案数据库。"
            "需要判断描述是否清晰、是否指向具体问题、是否具备可复用性、是否存在冲突或歧义、解决方案是否可操作。"
            "review_status 只能是 approved / needs_revision / rejected。\n"
            f"payload={json.dumps(payload, ensure_ascii=False)}"
        )
        data, _, _ = self.client.request_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
            temperature=0.0,
            timeout_seconds=min(self.client.settings.llm_timeout_seconds, 30),
            max_retries=1,
        )
        try:
            parsed = SolutionReviewResult.model_validate(data)
            parsed.llm_used = True
            return parsed
        except Exception:
            return heuristic

    def _heuristic_review(self, payload: dict[str, Any]) -> SolutionReviewResult:
        scenario = str(payload.get("trigger_scenario") or "").strip()
        root_cause = str(payload.get("root_cause_analysis") or "").strip()
        solution = str(payload.get("verified_solution") or "").strip()
        message = str(payload.get("message") or "").strip()
        reusable_hits = sum(
            1
            for value in [scenario, root_cause, solution, message, str(payload.get("normalized_signature") or "").strip()]
            if len(value) >= 8
        )
        clarity_score = min(1.0, round((len(message) + len(root_cause)) / 180, 2))
        completeness_score = min(1.0, round(reusable_hits / 5, 2))
        reusable_points = sum(1 for value in [solution, root_cause, scenario] if len(value) > 10)
        reusability_score = min(1.0, round(reusable_points / 3, 2))

        suggestions: list[str] = []
        status = "approved"
        if not scenario:
            suggestions.append("补充触发场景、前置条件和复现步骤")
        if len(root_cause) < 8:
            suggestions.append("根因分析需要更具体，最好指向具体模块/函数/配置")
        if len(solution) < 8:
            suggestions.append("解决方案需要更可操作，建议写出修复动作和验证结果")
        if not payload.get("module"):
            suggestions.append("需要明确所属模块")

        if completeness_score < 0.45 or clarity_score < 0.35:
            status = "needs_revision"
        if len(message) < 4 and len(root_cause) < 4 and len(solution) < 4:
            status = "rejected"

        reason = {
            "approved": "信息较完整，具备复用价值，可入库",
            "needs_revision": "存在信息缺口，建议补充后再入库",
            "rejected": "信息过于缺失，暂不建议入库",
        }[status]
        return SolutionReviewResult(
            review_status=status,
            review_reason=reason,
            revision_suggestions=suggestions,
            completeness_score=completeness_score,
            reusability_score=reusability_score,
            clarity_score=clarity_score,
            llm_used=False,
        )
