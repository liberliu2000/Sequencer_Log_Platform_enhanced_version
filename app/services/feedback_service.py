from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.settings import get_settings

VALID_REVIEW_STATUS = {"pending_review", "submitted_for_review", "approved", "rejected", "ignored"}


class FeedbackService:
    """
    用户纠错反馈记录服务。

    目标：
    1. 所有修正动作可落地、可查询、可复用
    2. 形成规则优化数据池，而不是只打印日志
    3. 保持低侵入，不强制修改现有主解析链
    4. 为审核流提供 record / cluster 两层 review_status 更新能力
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_dir = Path(settings.data_dir) / "active_learning"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.feedback_jsonl = self.base_dir / "feedback_records.jsonl"
        self.feedback_index_json = self.base_dir / "feedback_clusters.json"
        self._lock = RLock()

    def record_feedback(
        self,
        *,
        raw_log: str,
        original_parse_result: dict[str, Any] | None,
        corrected_result: dict[str, Any] | None,
        correction_type: str,
        source_file: str,
        user_id: str | None = None,
        notes: str | None = None,
        task_uuid: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "feedback_id": self._make_feedback_id(raw_log, correction_type, source_file),
            "raw_log": raw_log,
            "original_parse_result": original_parse_result or {},
            "corrected_result": corrected_result or {},
            "correction_type": correction_type,
            "source_file": source_file,
            "user_id": user_id,
            "task_uuid": task_uuid,
            "notes": notes,
            "corrected_at": datetime.utcnow().isoformat(),
            "review_status": "pending_review",
            "review_history": [],
            "data_pool": "feedback_learning",
        }

        with self._lock:
            self._append_jsonl(self.feedback_jsonl, row)
            self._update_feedback_index(row, increment_count=True)

        return row

    def list_feedback(
        self,
        limit: int = 200,
        correction_type: str | None = None,
        source_file: str | None = None,
        task_uuid: str | None = None,
        review_status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.feedback_jsonl.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.feedback_jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if correction_type and row.get("correction_type") != correction_type:
                    continue
                if source_file and row.get("source_file") != source_file:
                    continue
                if task_uuid and row.get("task_uuid") != task_uuid:
                    continue
                if review_status and str(row.get("review_status") or "pending_review") != review_status:
                    continue
                rows.append(row)
        return rows[-limit:]

    def list_feedback_clusters(self, limit: int = 100, review_status: str | None = None) -> list[dict[str, Any]]:
        index = self._load_index()
        rows = list(index.values())
        if review_status:
            rows = [row for row in rows if str(row.get("review_status") or "pending_review") == review_status]
        rows.sort(key=lambda x: (-int(x.get("count", 0)), str(x.get("correction_type") or "")))
        return rows[:limit]

    def update_feedback_review_status(
        self,
        *,
        review_status: str,
        reviewer: str | None = None,
        notes: str | None = None,
        feedback_id: str | None = None,
        cluster_key: str | None = None,
        scope: str = "record",
    ) -> dict[str, Any]:
        if review_status not in VALID_REVIEW_STATUS:
            raise ValueError(f"invalid review_status: {review_status}")
        if scope not in {"record", "cluster"}:
            raise ValueError(f"invalid scope: {scope}")
        if scope == "record":
            if not feedback_id:
                raise ValueError("feedback_id is required for record scope")
            return self._update_record_status(feedback_id=feedback_id, review_status=review_status, reviewer=reviewer, notes=notes)
        if not cluster_key:
            raise ValueError("cluster_key is required for cluster scope")
        return self._update_cluster_status(cluster_key=cluster_key, review_status=review_status, reviewer=reviewer, notes=notes)

    def _update_record_status(self, *, feedback_id: str, review_status: str, reviewer: str | None, notes: str | None) -> dict[str, Any]:
        rows = self.list_feedback(limit=100000)
        updated: dict[str, Any] | None = None
        for row in rows:
            if row.get("feedback_id") == feedback_id:
                history = list(row.get("review_history") or [])
                history.append(
                    {
                        "review_status": review_status,
                        "reviewed_at": datetime.utcnow().isoformat(),
                        "reviewer": reviewer,
                        "notes": notes,
                    }
                )
                row["review_status"] = review_status
                row["review_history"] = history[-50:]
                updated = row
                break
        if updated is None:
            raise KeyError(feedback_id)
        with self._lock:
            self._rewrite_feedback_jsonl(rows)
            self._update_feedback_index(updated, increment_count=False)
        return updated

    def _update_cluster_status(self, *, cluster_key: str, review_status: str, reviewer: str | None, notes: str | None) -> dict[str, Any]:
        with self._lock:
            index = self._load_index()
            item = index.get(cluster_key)
            if item is None:
                raise KeyError(cluster_key)
            history = list(item.get("review_history") or [])
            history.append(
                {
                    "review_status": review_status,
                    "reviewed_at": datetime.utcnow().isoformat(),
                    "reviewer": reviewer,
                    "notes": notes,
                }
            )
            item["review_status"] = review_status
            item["review_history"] = history[-50:]
            self._save_index(index)
            return item

    def _append_jsonl(self, path: Path, row: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")

    def _rewrite_feedback_jsonl(self, rows: list[dict[str, Any]]) -> None:
        tmp = self.feedback_jsonl.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False))
                f.write("\n")
        tmp.replace(self.feedback_jsonl)

    def _update_feedback_index(self, row: dict[str, Any], increment_count: bool = True) -> None:
        index = self._load_index()

        original = row.get("original_parse_result") or {}
        corrected = row.get("corrected_result") or {}
        correction_type = row.get("correction_type") or "unknown"

        cluster_key = self._cluster_key(
            correction_type=correction_type,
            source_file=row.get("source_file") or "",
            original_parser=original.get("parser_name"),
            original_sub_step=original.get("sub_step"),
            corrected_sub_step=corrected.get("sub_step"),
        )

        item = index.get(cluster_key)
        if item is None:
            index[cluster_key] = {
                "cluster_key": cluster_key,
                "correction_type": correction_type,
                "source_file": row.get("source_file"),
                "task_uuid": row.get("task_uuid"),
                "original_parser_name": original.get("parser_name"),
                "count": 1 if increment_count else 0,
                "first_seen_at": row["corrected_at"],
                "last_seen_at": row["corrected_at"],
                "representative_raw_log": row.get("raw_log"),
                "example_original_parse_result": original,
                "example_corrected_result": corrected,
                "review_status": row.get("review_status", "pending_review"),
                "review_history": list(row.get("review_history") or []),
                "data_pool": "feedback_learning",
            }
        else:
            if increment_count:
                item["count"] = int(item.get("count", 0)) + 1
            item["last_seen_at"] = row["corrected_at"]
            item["review_status"] = row.get("review_status", item.get("review_status", "pending_review"))
            item["review_history"] = list(row.get("review_history") or item.get("review_history") or [])[-50:]
            item.setdefault("data_pool", "feedback_learning")

        self._save_index(index)

    def _cluster_key(
        self,
        *,
        correction_type: str,
        source_file: str,
        original_parser: str | None,
        original_sub_step: str | None,
        corrected_sub_step: str | None,
    ) -> str:
        return "||".join(
            [
                correction_type or "",
                source_file or "",
                original_parser or "",
                original_sub_step or "",
                corrected_sub_step or "",
            ]
        )

    @staticmethod
    def _make_feedback_id(raw_log: str, correction_type: str, source_file: str) -> str:
        text = "||".join([raw_log.strip(), correction_type.strip(), source_file.strip()])
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    def _load_index(self) -> dict[str, Any]:
        path = self.feedback_index_json
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_index(self, data: dict[str, Any]) -> None:
        tmp = self.feedback_index_json.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.feedback_index_json)
