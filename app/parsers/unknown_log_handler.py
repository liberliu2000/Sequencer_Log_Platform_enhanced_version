from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.settings import get_settings
from app.utils.files import read_text_stream


TS_PATTERNS = [
    re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}(?:[.:]\d{3,6})?\b"),
    re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.:]\d{3,6})?\b"),
]
VALID_REVIEW_STATUS = {"pending_review", "submitted_for_review", "approved", "rejected", "ignored"}


@dataclass
class UnknownLogObservation:
    signature: str
    raw_text: str
    source_file: str
    source_path: str
    timestamp: str | None
    attempted_parsers: list[dict[str, Any]]
    attempted_rules: list[dict[str, Any]]
    failure_reason: str
    first_seen_at: str
    context_lines: list[str] = field(default_factory=list)
    line_no: int | None = None
    parser_selected: str | None = None


@dataclass
class UnknownLogCluster:
    signature: str
    representative_text: str
    representative_source_file: str
    representative_timestamp: str | None
    attempted_parsers: list[dict[str, Any]]
    attempted_rules: list[dict[str, Any]]
    failure_reasons: list[str]
    first_seen_at: str
    last_seen_at: str
    occurrence_count: int = 1
    source_files: dict[str, int] = field(default_factory=dict)
    context_examples: list[dict[str, Any]] = field(default_factory=list)
    review_status: str = "pending_review"
    review_history: list[dict[str, Any]] = field(default_factory=list)


class UnknownLogHandler:
    """
    未知日志兜底处理器。

    设计原则：
    1. 与现有 parser registry 低侵入兼容
    2. 任意未知日志都可落地保存，而不是只 warning
    3. 基于稳定 signature 聚合相似日志，避免待标注池爆炸
    4. 输出结构同时兼容后续本地规则归纳与 LLM 规则建议
    5. 提供可提交审核的 review_status 状态流
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_dir = Path(self.settings.data_dir) / "active_learning"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.pool_jsonl = self.base_dir / "unknown_log_pool.jsonl"
        self.cluster_json = self.base_dir / "unknown_log_clusters.json"
        self._lock = RLock()

    def handle_file_failure(
        self,
        path: Path,
        attempted_parsers: list[dict[str, Any]],
        failure_reason: str,
        parser_selected: str | None = None,
        attempted_rules: list[dict[str, Any]] | None = None,
        sample_lines: int = 20,
    ) -> None:
        lines: list[str] = []
        try:
            for _, line in enumerate(read_text_stream(path), start=1):
                if line.strip():
                    lines.append(line.strip())
                if len(lines) >= sample_lines:
                    break
        except Exception as exc:
            lines = [f"[FILE_READ_FAILED] {exc}"]

        now = datetime.utcnow().isoformat()
        for idx, line in enumerate(lines, start=1):
            context_lines = [l for l in lines[max(0, idx - 3): min(len(lines), idx + 2)] if l.strip()]
            obs = UnknownLogObservation(
                signature=self._make_signature(line),
                raw_text=line,
                source_file=path.name,
                source_path=str(path),
                timestamp=self._extract_timestamp(line),
                attempted_parsers=attempted_parsers,
                attempted_rules=attempted_rules or [],
                failure_reason=failure_reason,
                first_seen_at=now,
                context_lines=context_lines,
                line_no=idx,
                parser_selected=parser_selected,
            )
            self._persist_observation(obs)

    def handle_unknown_lines(
        self,
        path: Path,
        unknown_lines: list[dict[str, Any]],
        attempted_parsers: list[dict[str, Any]],
        failure_reason: str,
        parser_selected: str | None = None,
        attempted_rules: list[dict[str, Any]] | None = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        for row in unknown_lines:
            text = str(row.get("raw_text") or "").strip()
            if not text:
                continue
            context_lines = list(row.get("context_before") or []) + [text] + list(row.get("context_after") or [])
            obs = UnknownLogObservation(
                signature=self._make_signature(text),
                raw_text=text,
                source_file=path.name,
                source_path=str(path),
                timestamp=self._extract_timestamp(text),
                attempted_parsers=attempted_parsers,
                attempted_rules=attempted_rules or [],
                failure_reason=failure_reason,
                first_seen_at=now,
                context_lines=context_lines,
                line_no=row.get("line_no"),
                parser_selected=parser_selected,
            )
            self._persist_observation(obs)

    def list_clusters(
        self,
        limit: int = 100,
        min_occurrence: int = 1,
        review_status: str | None = None,
    ) -> list[dict[str, Any]]:
        clusters = list(self._load_clusters().values())
        rows = [row for row in clusters if int(row.get("occurrence_count", 0)) >= min_occurrence]
        if review_status:
            rows = [row for row in rows if str(row.get("review_status") or "pending_review") == review_status]
        rows.sort(key=lambda x: (-int(x.get("occurrence_count", 0)), str(x.get("representative_source_file") or "")))
        return rows[:limit]

    def update_review_status(
        self,
        signature: str,
        review_status: str,
        reviewer: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if review_status not in VALID_REVIEW_STATUS:
            raise ValueError(f"invalid review_status: {review_status}")
        with self._lock:
            clusters = self._load_clusters()
            cluster = clusters.get(signature)
            if cluster is None:
                raise KeyError(signature)
            history = list(cluster.get("review_history") or [])
            history.append(
                {
                    "review_status": review_status,
                    "reviewed_at": datetime.utcnow().isoformat(),
                    "reviewer": reviewer,
                    "notes": notes,
                }
            )
            cluster["review_status"] = review_status
            cluster["review_history"] = history[-50:]
            self._save_clusters(clusters)
            return cluster

    def _persist_observation(self, obs: UnknownLogObservation) -> None:
        with self._lock:
            payload = asdict(obs)
            payload["extracted_timestamp"] = obs.timestamp
            try:
                self._append_jsonl(self.pool_jsonl, payload)
                clusters = self._load_clusters()
            except OSError:
                # Unknown-log learning is auxiliary; it must never break primary parsing.
                return
            cluster = clusters.get(obs.signature)

            if cluster is None:
                cluster_obj = UnknownLogCluster(
                    signature=obs.signature,
                    representative_text=obs.raw_text,
                    representative_source_file=obs.source_file,
                    representative_timestamp=obs.timestamp,
                    attempted_parsers=obs.attempted_parsers,
                    attempted_rules=obs.attempted_rules,
                    failure_reasons=[obs.failure_reason],
                    first_seen_at=obs.first_seen_at,
                    last_seen_at=obs.first_seen_at,
                    occurrence_count=1,
                    source_files={obs.source_file: 1},
                    context_examples=[self._build_context_example(obs)],
                    review_status="pending_review",
                    review_history=[],
                )
                clusters[obs.signature] = asdict(cluster_obj)
            else:
                cluster["occurrence_count"] = int(cluster.get("occurrence_count", 0)) + 1
                cluster["last_seen_at"] = datetime.utcnow().isoformat()
                cluster.setdefault("source_files", {})
                cluster["source_files"][obs.source_file] = int(cluster["source_files"].get(obs.source_file, 0)) + 1

                reasons = list(cluster.get("failure_reasons") or [])
                if obs.failure_reason not in reasons:
                    reasons.append(obs.failure_reason)
                cluster["failure_reasons"] = reasons[:10]

                if not cluster.get("attempted_parsers") and obs.attempted_parsers:
                    cluster["attempted_parsers"] = obs.attempted_parsers
                if not cluster.get("attempted_rules") and obs.attempted_rules:
                    cluster["attempted_rules"] = obs.attempted_rules

                examples = list(cluster.get("context_examples") or [])
                if len(examples) < 20:
                    examples.append(self._build_context_example(obs))
                cluster["context_examples"] = examples
                cluster.setdefault("review_status", "pending_review")
                cluster.setdefault("review_history", [])
                cluster.setdefault("representative_timestamp", obs.timestamp)
            try:
                self._save_clusters(clusters)
            except OSError:
                return

    def _build_context_example(self, obs: UnknownLogObservation) -> dict[str, Any]:
        return {
            "source_file": obs.source_file,
            "line_no": obs.line_no,
            "raw_text": obs.raw_text,
            "context_lines": obs.context_lines,
            "timestamp": obs.timestamp,
            "extracted_timestamp": obs.timestamp,
            "parser_selected": obs.parser_selected,
            "failure_reason": obs.failure_reason,
        }

    def _make_signature(self, text: str) -> str:
        s = self._normalize_text(text)
        return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _normalize_text(text: str) -> str:
        s = text.lower().strip()
        s = re.sub(r"\d{4}[-/]\d{2}[-/]\d{2}", "<date>", s)
        s = re.sub(r"\d{2}:\d{2}:\d{2}(?:[.:]\d{3,6})?", "<time>", s)
        s = re.sub(r"[A-Za-z]:\\[^ ]+", "<path>", s)
        s = re.sub(r"/[^ ]+", "<path>", s)
        s = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", s)
        s = re.sub(r"\b\d+\b", "<num>", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _extract_timestamp(self, text: str) -> str | None:
        for pat in TS_PATTERNS:
            m = pat.search(text)
            if m:
                return m.group(0)
        return None

    def _append_jsonl(self, path: Path, row: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")

    def _load_clusters(self) -> dict[str, Any]:
        if not self.cluster_json.exists():
            return {}
        try:
            return json.loads(self.cluster_json.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_clusters(self, data: dict[str, Any]) -> None:
        tmp = self.cluster_json.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.cluster_json)
