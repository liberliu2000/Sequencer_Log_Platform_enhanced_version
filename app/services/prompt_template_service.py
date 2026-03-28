from __future__ import annotations

from app.core.settings import get_settings
from app.utils.rules import load_yaml, save_yaml


class PromptTemplateService:
    def __init__(self):
        self.settings = get_settings()

    def get_templates(self) -> dict:
        data = load_yaml(self.settings.prompt_templates_path)
        data.setdefault("active_version", "v1")
        data.setdefault("templates", {})
        return data

    def get_active(self) -> dict:
        data = self.get_templates()
        active_version = data.get("active_version", "v1")
        template = data.get("templates", {}).get(active_version) or {}
        return {"active_version": active_version, "template": template, "all_versions": list(data.get("templates", {}).keys())}

    def set_active_version(self, version: str) -> dict:
        data = self.get_templates()
        if version not in data.get("templates", {}):
            raise ValueError("模板版本不存在")
        data["active_version"] = version
        save_yaml(self.settings.prompt_templates_path, data)
        return self.get_active()

    def upsert_template(self, version: str, template: dict) -> dict:
        data = self.get_templates()
        data.setdefault("templates", {})[version] = template
        if not data.get("active_version"):
            data["active_version"] = version
        save_yaml(self.settings.prompt_templates_path, data)
        return self.get_active()
