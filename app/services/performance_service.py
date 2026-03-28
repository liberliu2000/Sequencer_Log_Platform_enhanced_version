from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.settings import get_settings


class PerformanceService:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_dir = Path(settings.data_dir) / "performance"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_uuid: str) -> Path:
        return self.base_dir / f"{task_uuid}.json"

    def write_summary(self, task_uuid: str, payload: dict[str, Any]) -> None:
        path = self._path(task_uuid)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    def read_summary(self, task_uuid: str) -> dict[str, Any]:
        path = self._path(task_uuid)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
