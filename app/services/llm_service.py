from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.llm.context import estimate_tokens
from app.llm.prompts import build_error_analysis_prompt
from app.models.db_models import LLMAnalysisResultModel
from app.repositories.task_repository import TaskRepository
from app.services.analysis_depth_manager import AnalysisDepthManager
from app.services.case_retriever import CaseRetriever
from app.services.prompt_template_service import PromptTemplateService
from app.services.query_service import QueryService
from app.services.source_context_selector import SourceContextSelector


class LLMService:
    def __init__(self, db: Session):
        self.db = db
        self.client = LLMClient()
        self.query = QueryService(db)
        self.repo = TaskRepository(db)
        self.prompt_templates = PromptTemplateService()
        self.depth_manager = AnalysisDepthManager()
        self.case_retriever = CaseRetriever(db)
        self.source_selector = SourceContextSelector()

    def analyze_signature(
        self,
        task_id: int,
        signature: str,
        *,
        force: bool = False,
        analysis_depth: str = "medium",
        trigger_scenario: str | None = None,
        module: str | None = None,
        submodule: str | None = None,
        environment_info: str | None = None,
        reproduction_steps: str | None = None,
        customer_symptom: str | None = None,
        operation_path: str | None = None,
        source_notes: str | None = None,
        existing_solution: dict[str, Any] | None = None,
        source_files: list[Path] | None = None,
    ) -> dict:
        depth_strategy = self.depth_manager.get(analysis_depth)
        analysis_request = {
            "analysis_depth": depth_strategy["depth"],
            "trigger_scenario": trigger_scenario or "",
            "module": module or "",
            "submodule": submodule or "",
            "environment_info": environment_info or "",
            "reproduction_steps": reproduction_steps or "",
            "customer_symptom": customer_symptom or "",
            "operation_path": operation_path or "",
            "source_notes": source_notes or "",
            "existing_solution": existing_solution or {},
            "source_files": [Path(p).name for p in (source_files or [])],
        }

        if not force:
            existing = self.repo.get_latest_llm_result(task_id, signature)
            if existing:
                req = self._safe_json(existing.request_payload)
                if req.get("analysis_request") == analysis_request:
                    resp = self._safe_json(existing.response_payload)
                    return {
                        "structured_result": resp.get("structured_result", resp),
                        "chinese_summary": existing.chinese_summary,
                        "request_payload": req,
                        "response_payload": resp,
                        "context_summary": req.get("context_summary", {}),
                        "analysis_stage": existing.analysis_stage or req.get("analysis_stage", depth_strategy["depth"]),
                        "prompt_version": existing.prompt_version,
                        "from_cache": True,
                        "created_at": existing.created_at.isoformat(),
                        "llm_status": req.get("llm_status", "cached"),
                        "token_summary": req.get("token_summary", {}),
                        "depth_strategy": req.get("depth_strategy", depth_strategy),
                        "similar_cases": req.get("similar_cases", []),
                        "source_context_snippets": req.get("source_context_snippets", []),
                    }

        started_at = time.monotonic()
        active_tpl = self.prompt_templates.get_active()
        cluster, context_rows, stats = self.query.get_context_for_signature(
            task_id,
            signature,
            stage=depth_strategy["context_stage"],
            token_budget=int(depth_strategy["token_budget"]),
        )
        effective_module = module or cluster.get("component") or "未指定模块"
        user_context = {
            "trigger_scenario": trigger_scenario,
            "module": effective_module,
            "submodule": submodule,
            "environment_info": environment_info,
            "reproduction_steps": reproduction_steps,
            "customer_symptom": customer_symptom,
            "operation_path": operation_path,
            "source_notes": source_notes,
            "existing_solution": existing_solution or {},
        }
        source_snippets = self.source_selector.select_relevant_snippets(
            source_files or [],
            cluster=cluster,
            trigger_scenario=trigger_scenario,
            module=effective_module,
            depth_config=depth_strategy,
        )
        raw_cases = self.case_retriever.retrieve_similar_cases(
            normalized_signature=signature,
            message=cluster.get("representative_message"),
            module=effective_module if effective_module != "未指定模块" else None,
            error_code=cluster.get("error_code"),
            trigger_scenario=trigger_scenario,
            limit=int(depth_strategy["history_case_limit"]),
        )
        similar_cases = self.case_retriever.summarize_for_llm(raw_cases)

        prompt = build_error_analysis_prompt(
            cluster,
            context_rows,
            stats,
            mode=depth_strategy["depth"],
            template=active_tpl.get("template"),
            user_context=user_context,
            source_snippets=source_snippets,
            similar_cases=similar_cases,
            depth_strategy=depth_strategy,
        )
        result, request_payload, response_payload = self.client.analyze(prompt)
        structured = result.model_dump()
        llm_status = "fallback" if self._is_fallback_response(response_payload) else "ok"
        chinese_summary = self._build_cn_summary(structured)
        enriched_context_summary = {
            **(stats.get("context_summary", {}) if isinstance(stats, dict) else {}),
            "analysis_depth": depth_strategy["depth"],
            "history_case_count": len(similar_cases),
            "source_context_count": len(source_snippets),
        }
        token_summary = self._build_token_summary(prompt, {"context_summary": enriched_context_summary}, request_payload, response_payload)
        persisted_request = {
            "analysis_stage": depth_strategy["depth"],
            "prompt_version": active_tpl.get("active_version"),
            "cluster": cluster,
            "context_summary": enriched_context_summary,
            "stats": stats,
            "compressed_context_preview": context_rows,
            "user_context": user_context,
            "source_context_snippets": source_snippets,
            "similar_cases": similar_cases,
            "depth_strategy": depth_strategy,
            "analysis_request": analysis_request,
            "llm_request": request_payload,
            "llm_status": llm_status,
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "token_summary": token_summary,
        }
        persisted_response = {"structured_result": structured, "llm_raw_response": response_payload}

        self.repo.save_llm_result(
            LLMAnalysisResultModel(
                task_id=task_id,
                normalized_signature=signature,
                model_name=self.client.settings.llm_model,
                prompt_version=active_tpl.get("active_version"),
                analysis_stage=depth_strategy["depth"],
                request_payload=json.dumps(persisted_request, ensure_ascii=False),
                response_payload=json.dumps(persisted_response, ensure_ascii=False),
                chinese_summary=chinese_summary,
            )
        )
        return {
            "structured_result": structured,
            "chinese_summary": chinese_summary,
            "request_payload": persisted_request,
            "response_payload": persisted_response,
            "context_summary": enriched_context_summary,
            "analysis_stage": depth_strategy["depth"],
            "prompt_version": active_tpl.get("active_version"),
            "from_cache": False,
            "llm_status": llm_status,
            "token_summary": token_summary,
            "depth_strategy": depth_strategy,
            "similar_cases": similar_cases,
            "source_context_snippets": source_snippets,
        }

    def list_results(self, task_id: int) -> list[dict]:
        rows = self.repo.list_llm_results(task_id)
        out = []
        for r in rows:
            req = self._safe_json(r.request_payload)
            resp = self._safe_json(r.response_payload)
            token_summary_raw = req.get("token_summary", {})
            token_summary: dict[str, Any] = token_summary_raw if isinstance(token_summary_raw, dict) else {}
            out.append(
                {
                    "normalized_signature": r.normalized_signature,
                    "model_name": r.model_name,
                    "chinese_summary": r.chinese_summary,
                    "created_at": r.created_at.isoformat(),
                    "analysis_stage": r.analysis_stage or req.get("analysis_stage", "medium"),
                    "prompt_version": r.prompt_version,
                    "context_summary": req.get("context_summary", {}),
                    "request_payload": req,
                    "response_payload": resp,
                    "llm_status": req.get("llm_status", "ok"),
                    "elapsed_seconds": req.get("elapsed_seconds"),
                    "token_summary": token_summary,
                    "final_total_tokens": token_summary.get("final_total_tokens"),
                    "compression_efficiency": token_summary.get("compression_efficiency_percent"),
                    "depth_strategy": req.get("depth_strategy", {}),
                    "similar_cases": req.get("similar_cases", []),
                    "source_context_snippets": req.get("source_context_snippets", []),
                }
            )
        return out

    @staticmethod
    def _safe_json(text: str) -> dict[str, Any]:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"raw": parsed}
        except Exception:
            return {"raw": text}

    @staticmethod
    def _is_fallback_response(response_payload: dict) -> bool:
        if not isinstance(response_payload, dict):
            return False
        if response_payload.get("fallback"):
            return True
        raw = response_payload.get("llm_raw_response")
        return isinstance(raw, dict) and bool(raw.get("fallback") or raw.get("error"))

    @staticmethod
    def _build_cn_summary(data: dict) -> str:
        return (
            f"根因摘要：{data.get('root_cause_summary', '')}\n"
            f"可能模块：{data.get('probable_module') or '; '.join(data.get('affected_modules', []))}\n"
            f"直接证据：{'; '.join(data.get('direct_evidence', [])[:3])}\n"
            f"历史经验推断：{'; '.join(data.get('historical_inferences', [])[:2])}\n"
            f"未验证假设：{'; '.join(data.get('unverified_hypotheses', [])[:2])}\n"
            f"建议检查：{'; '.join(data.get('recommended_checks', [])[:4])}\n"
            f"责任部门：{'; '.join(data.get('owner_departments', []))}\n"
            f"严重级别：{data.get('severity', '')}，置信度：{data.get('confidence', 0.0)}"
        )

    @staticmethod
    def _extract_usage(response_payload: dict[str, Any]) -> dict[str, Any]:
        usage = response_payload.get("usage") if isinstance(response_payload, dict) else None
        if not isinstance(usage, dict):
            raw = response_payload.get("llm_raw_response") if isinstance(response_payload, dict) else None
            usage = raw.get("usage") if isinstance(raw, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
            total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "usage_available": bool(usage),
            "usage_raw": usage,
        }

    def _build_token_summary(
        self,
        final_prompt: str,
        final_stats: dict[str, Any],
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        context_summary = final_stats.get("context_summary", {}) if isinstance(final_stats, dict) else {}
        usage = self._extract_usage(response_payload)
        prompt_estimated_tokens = estimate_tokens(final_prompt)
        response_text = ""
        if isinstance(response_payload, dict):
            if isinstance(response_payload.get("choices"), list) and response_payload.get("choices"):
                response_text = str((((response_payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")
            elif isinstance(response_payload.get("llm_raw_response"), dict):
                raw = response_payload.get("llm_raw_response") or {}
                if isinstance(raw.get("choices"), list) and raw.get("choices"):
                    response_text = str((((raw.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")
                elif response_payload.get("structured_result") is not None:
                    response_text = json.dumps(response_payload.get("structured_result"), ensure_ascii=False)
                elif raw.get("fallback") or raw.get("error"):
                    response_text = str(raw.get("error") or raw.get("reason") or "")
        completion_estimated_tokens = estimate_tokens(response_text) if response_text else 0

        final_prompt_tokens = usage.get("prompt_tokens") if usage.get("prompt_tokens") is not None else prompt_estimated_tokens
        final_completion_tokens = usage.get("completion_tokens") if usage.get("completion_tokens") is not None else completion_estimated_tokens
        final_total_tokens = usage.get("total_tokens") if usage.get("total_tokens") is not None else int(final_prompt_tokens or 0) + int(final_completion_tokens or 0)

        raw_tokens = int(context_summary.get("raw_estimated_tokens", 0) or 0)
        compressed_tokens = int(context_summary.get("compressed_estimated_tokens", 0) or 0)
        compression_efficiency = round((1 - compressed_tokens / max(1, raw_tokens)) * 100, 2) if raw_tokens else 0.0
        prompt_overhead_tokens = max(0, int(final_prompt_tokens or 0) - compressed_tokens)
        return {
            "context_raw_tokens_estimated": raw_tokens,
            "context_compressed_tokens_estimated": compressed_tokens,
            "prompt_estimated_tokens": prompt_estimated_tokens,
            "completion_estimated_tokens": completion_estimated_tokens,
            "prompt_overhead_tokens_estimated": prompt_overhead_tokens,
            "final_prompt_tokens": final_prompt_tokens,
            "final_completion_tokens": final_completion_tokens,
            "final_total_tokens": final_total_tokens,
            "compression_efficiency_percent": compression_efficiency,
            "compression_ratio": context_summary.get("token_compression_ratio"),
            "within_context_budget": context_summary.get("within_budget"),
            "token_budget": context_summary.get("token_budget"),
            "usage_source": "provider_usage" if usage.get("usage_available") else "estimated",
            "request_payload_tokens_estimated": estimate_tokens(json.dumps(request_payload, ensure_ascii=False, default=str)),
        }
