from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

from app.schemas.common import SourceContextSnippet

_TEXT_EXTENSIONS = {
    ".py",
    ".cs",
    ".js",
    ".ts",
    ".tsx",
    ".java",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".toml",
    ".xml",
    ".txt",
    ".md",
    ".cfg",
    ".conf",
}


def _guess_language(path: Path) -> str | None:
    suffix = path.suffix.lower()
    return {
        ".py": "python",
        ".cs": "csharp",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".java": "java",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".xml": "xml",
        ".toml": "toml",
        ".ini": "ini",
    }.get(suffix)


class SourceContextSelector:
    def select_relevant_snippets(
        self,
        files: list[Path],
        *,
        cluster: dict[str, Any],
        trigger_scenario: str | None,
        module: str | None,
        depth_config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        max_snippets = int(depth_config.get("max_source_snippets", 2))
        max_chars = int(depth_config.get("max_source_chars", 1200))
        keywords = self._build_keywords(cluster, trigger_scenario, module)
        snippets: list[SourceContextSnippet] = []
        for path in files:
            if not path.exists() or not path.is_file():
                continue
            if not self._is_text_file(path):
                continue
            snippet = self._extract_best_snippet(path, keywords)
            if snippet is not None:
                snippets.append(snippet)
        snippets.sort(key=lambda item: item.score, reverse=True)
        trimmed: list[dict[str, Any]] = []
        remaining_chars = max_chars
        for item in snippets[: max_snippets * 2]:
            excerpt = item.excerpt[:remaining_chars]
            if not excerpt.strip():
                continue
            payload = item.model_dump()
            payload["excerpt"] = excerpt
            trimmed.append(payload)
            remaining_chars -= len(excerpt)
            if len(trimmed) >= max_snippets or remaining_chars <= 0:
                break
        return trimmed

    @staticmethod
    def _is_text_file(path: Path) -> bool:
        if path.suffix.lower() in _TEXT_EXTENSIONS:
            return True
        mime = mimetypes.guess_type(path.name)[0] or ""
        return mime.startswith("text/")

    @staticmethod
    def _build_keywords(cluster: dict[str, Any], trigger_scenario: str | None, module: str | None) -> list[str]:
        values = [
            cluster.get("normalized_signature"),
            cluster.get("representative_message"),
            cluster.get("representative_exception"),
            cluster.get("component"),
            cluster.get("error_code"),
            trigger_scenario,
            module,
        ]
        text = " ".join(str(v or "") for v in values)
        tokens = [token.strip() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{2,}|\d{2,}|[\u4e00-\u9fff]{2,}", text)]
        seen: set[str] = set()
        out: list[str] = []
        for token in tokens:
            lower = token.lower()
            if lower in seen:
                continue
            seen.add(lower)
            out.append(token)
        return out[:18]

    def _extract_best_snippet(self, path: Path, keywords: list[str]) -> SourceContextSnippet | None:
        text = self._read_text(path)
        if not text:
            return None
        lines = text.splitlines()
        best_score = 0.0
        best_start = 0
        best_end = min(len(lines), 30)
        best_reason = "fallback"
        lowered_lines = [line.lower() for line in lines]
        for idx, line in enumerate(lowered_lines):
            score = 0.0
            hits: list[str] = []
            for keyword in keywords:
                kw = keyword.lower()
                if kw and kw in line:
                    score += 1.0
                    hits.append(keyword)
            if any(token in line for token in ["throw", "raise", "exception", "error", "return", "message", "code"]):
                score += 0.4
            if score > best_score:
                best_score = score
                best_start = max(0, idx - 4)
                best_end = min(len(lines), idx + 8)
                best_reason = f"keyword hits: {', '.join(hits[:4])}" if hits else "likely exception-related block"
        if best_score <= 0:
            preview = "\n".join(lines[: min(len(lines), 18)])
            return SourceContextSnippet(
                file_name=path.name,
                snippet_reason="fallback preview",
                language=_guess_language(path),
                line_start=1,
                line_end=min(len(lines), 18),
                excerpt=preview,
                score=0.05,
            )
        excerpt = "\n".join(lines[best_start:best_end])
        return SourceContextSnippet(
            file_name=path.name,
            snippet_reason=best_reason,
            language=_guess_language(path),
            line_start=best_start + 1,
            line_end=best_end,
            excerpt=excerpt,
            score=best_score,
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gbk", "latin1"):
            try:
                return path.read_text(encoding=encoding, errors="replace")
            except Exception:
                continue
        return ""
