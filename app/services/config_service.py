from __future__ import annotations

from app.core.settings import get_settings
from app.utils.rules import load_yaml, save_yaml
from app.services.analysis_depth_manager import AnalysisDepthManager
from app.services.env_file_service import EnvFileService
from app.services.prompt_template_service import PromptTemplateService
from app.services.solution_repository import MODULE_PREFIXES, MODULE_TREE


class ConfigService:
    def __init__(self):
        self.settings = get_settings()

    def get_all(self) -> dict:
        return {
            "thresholds": load_yaml(self.settings.thresholds_path),
            "parser_rules": load_yaml(self.settings.parser_rules_path),
            "error_rules": load_yaml(self.settings.error_rules_path),
            "prompt_templates": PromptTemplateService().get_templates(),
            "env_file": {
                "items": EnvFileService().list_items(),
            },
            "llm": {
                "enabled": self.settings.llm_enabled,
                "base_url": self.settings.llm_base_url,
                "model": self.settings.llm_model,
                "timeout_seconds": self.settings.llm_timeout_seconds,
                "max_retries": self.settings.llm_max_retries,
                "diagnosis_ui_timeout_seconds": self.settings.llm_diagnosis_ui_timeout_seconds,
                "preview": {
                    "timeout_seconds": self.settings.llm_preview_timeout_seconds,
                    "max_retries": self.settings.llm_preview_max_retries,
                    "cache_ttl_seconds": self.settings.llm_preview_cache_ttl_seconds,
                    "max_unknown_samples": self.settings.llm_preview_max_unknown_samples,
                    "max_feedback_samples": self.settings.llm_preview_max_feedback_samples,
                    "max_parser_snippets": self.settings.llm_preview_max_parser_snippets,
                },
                "context": {
                    "pre_lines": self.settings.llm_context_pre_lines,
                    "post_lines": self.settings.llm_context_post_lines,
                    "time_window_seconds": self.settings.llm_context_time_window_seconds,
                    "related_component_limit": self.settings.llm_context_related_component_limit,
                    "related_cycle_limit": self.settings.llm_context_related_cycle_limit,
                    "max_stack_frames": self.settings.llm_context_max_stack_frames,
                    "max_token_budget": self.settings.llm_context_max_token_budget,
                    "stage1_token_budget": self.settings.llm_context_stage1_token_budget,
                },
                "analysis_depths": AnalysisDepthManager().list_strategies(),
            },
            "solution_repository": {
                "module_tree": MODULE_TREE,
                "module_prefixes": MODULE_PREFIXES,
            },
        }

    def update_thresholds(self, data: dict) -> dict:
        save_yaml(self.settings.thresholds_path, data)
        return data
