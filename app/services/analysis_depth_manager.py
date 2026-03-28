from __future__ import annotations

from typing import Any

from app.core.settings import get_settings


class AnalysisDepthManager:
    def __init__(self):
        settings = get_settings()
        self._strategies = {
            "low": {
                "label": "Low",
                "description": "快速初判，优先输出最可能原因、模块归属和优先检查项。",
                "context_stage": "light",
                "token_budget": min(settings.llm_context_stage1_token_budget, 1200),
                "history_case_limit": 1,
                "max_source_snippets": 2,
                "max_source_chars": 900,
                "output_max_chars": 1200,
                "reasoning_granularity": "brief",
            },
            "medium": {
                "label": "Medium",
                "description": "常规分析，补充关键证据、责任部门和排查路径。",
                "context_stage": "medium",
                "token_budget": max(settings.llm_context_stage1_token_budget, 1800),
                "history_case_limit": 3,
                "max_source_snippets": 3,
                "max_source_chars": 1800,
                "output_max_chars": 2200,
                "reasoning_granularity": "standard",
            },
            "high": {
                "label": "High",
                "description": "复杂问题深入分析，强调分层根因、证据链、修复路径与风险提示。",
                "context_stage": "deep",
                "token_budget": max(settings.llm_context_max_token_budget, 2600),
                "history_case_limit": 5,
                "max_source_snippets": 5,
                "max_source_chars": 3200,
                "output_max_chars": 3600,
                "reasoning_granularity": "deep",
            },
        }

    def get(self, depth: str | None) -> dict[str, Any]:
        key = str(depth or "medium").strip().lower()
        return {"depth": key if key in self._strategies else "medium", **self._strategies.get(key, self._strategies["medium"])}

    def list_strategies(self) -> dict[str, dict[str, Any]]:
        return {key: {"depth": key, **value} for key, value in self._strategies.items()}
