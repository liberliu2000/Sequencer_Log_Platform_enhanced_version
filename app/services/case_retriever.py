from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.services.solution_repository import SolutionRepositoryService

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {token.lower() for token in _TOKEN_RE.findall(str(text)) if token.strip()}


def _overlap_score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _error_code_prefix(value: str | None) -> str:
    text = str(value or "").strip().upper().replace("-", "")
    prefix = "".join(ch for ch in text if ch.isalpha())
    return prefix[:2]


class CaseRetriever:
    def __init__(self, db: Session):
        self.db = db
        self.repository = SolutionRepositoryService(db)

    def retrieve_similar_cases(
        self,
        *,
        normalized_signature: str | None,
        message: str | None,
        module: str | None,
        error_code: str | None,
        trigger_scenario: str | None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        candidate_limit = max(limit * 8, 20)
        candidates = self.repository.list_records(
            module=module or None,
            normalized_signature=normalized_signature or None,
            error_code=error_code or None,
            limit=candidate_limit,
        )
        if not candidates:
            candidates = self.repository.list_records(limit=candidate_limit)

        msg_tokens = _tokenize(message)
        scenario_tokens = _tokenize(trigger_scenario)
        out: list[dict[str, Any]] = []
        for row in candidates:
            score = self._score_case(
                row,
                normalized_signature=normalized_signature,
                message=message,
                module=module,
                error_code=error_code,
                msg_tokens=msg_tokens,
                scenario_tokens=scenario_tokens,
            )
            row_out = {
                "case_id": row["id"],
                "error_name": row["error_name"],
                "normalized_signature": row.get("normalized_signature"),
                "module": row["module"],
                "error_code": row.get("error_code"),
                "trigger_scenario_summary": row.get("trigger_scenario_summary"),
                "root_cause_summary": row.get("root_cause_summary"),
                "solution_summary": row.get("solution_summary"),
                "success_flag": bool(row.get("reusable")) and str(row.get("review_status")) == "approved",
                "similarity_score": round(score, 4),
            }
            out.append(row_out)
        out.sort(key=lambda item: item["similarity_score"], reverse=True)
        return [row for row in out if row["similarity_score"] > 0][: max(1, min(limit, 10))]

    def _score_case(
        self,
        row: dict[str, Any],
        *,
        normalized_signature: str | None,
        message: str | None,
        module: str | None,
        error_code: str | None,
        msg_tokens: set[str],
        scenario_tokens: set[str],
    ) -> float:
        score = 0.0
        row_sig = str(row.get("normalized_signature") or "")
        row_message = str(row.get("message") or "")
        row_scenario = str(row.get("trigger_scenario") or "")
        row_error_code = str(row.get("error_code") or "")

        if normalized_signature and row_sig:
            if row_sig == normalized_signature:
                score += 0.45
            else:
                score += 0.2 * SequenceMatcher(None, row_sig, normalized_signature).ratio()

        if error_code and row_error_code:
            if row_error_code == error_code:
                score += 0.25
            elif _error_code_prefix(row_error_code) and _error_code_prefix(row_error_code) == _error_code_prefix(error_code):
                score += 0.12

        if module and str(row.get("module") or "") == module:
            score += 0.1

        message_ratio = SequenceMatcher(None, row_message, str(message or "")).ratio() if message and row_message else 0.0
        score += 0.1 * message_ratio
        score += 0.07 * _overlap_score(msg_tokens, _tokenize(row_message))
        score += 0.08 * _overlap_score(scenario_tokens, _tokenize(row_scenario))

        if row.get("reusable"):
            score += 0.03
        if str(row.get("review_status")) == "approved":
            score += 0.02
        return min(score, 0.99)

    def summarize_for_llm(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "similar_error_name": row.get("error_name"),
                "similar_normalized_signature": row.get("normalized_signature"),
                "historical_module": row.get("module"),
                "historical_error_code": row.get("error_code"),
                "historical_trigger_scenario_summary": row.get("trigger_scenario_summary"),
                "historical_root_cause_summary": row.get("root_cause_summary"),
                "historical_solution_summary": row.get("solution_summary"),
                "historical_successful_fix": row.get("success_flag"),
                "similarity_score": row.get("similarity_score"),
            }
            for row in cases
        ]
