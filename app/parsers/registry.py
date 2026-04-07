from __future__ import annotations

from itertools import chain
from pathlib import Path
from typing import Iterable, Type

from app.core.settings import get_settings
from app.parsers.base import BaseParser
from app.parsers.csv_workflow_parser import CsvWorkflowParser
from app.parsers.error_log_parser import ErrorLogParser
from app.parsers.metrics_csv_parser import MetricsCsvParser
from app.parsers.runerror_parser import RunErrorParser
from app.parsers.service_log_parser import ServiceLogParser
from app.parsers.unknown_log_handler import UnknownLogHandler
from app.utils.files import read_text_stream
from app.utils.rules import load_yaml


class ParserRegistry:
    """
    Incremental optimization goals:
    1. keep the existing parser score workflow intact
    2. avoid materializing the whole file into a list in the hot path
    3. skip expensive line-level unknown-log sampling for huge files
    """

    def __init__(self):
        self.parsers: list[Type[BaseParser]] = [
            MetricsCsvParser,
            CsvWorkflowParser,
            ServiceLogParser,
            ErrorLogParser,
            RunErrorParser,
        ]
        self._parser_by_name = {parser_cls.name: parser_cls for parser_cls in self.parsers}
        self.settings = get_settings()
        self.rules = load_yaml(self.settings.parser_rules_path)
        self.unknown_handler = UnknownLogHandler()
        self.unknown_scan_max_bytes = max(
            0,
            int(
                ((self.rules.get("active_learning", {}) or {}).get("unknown_handling", {}) or {}).get(
                    "max_scan_bytes",
                    getattr(self.settings, "unknown_log_max_scan_bytes", 4 * 1024 * 1024),
                )
            ),
        )

    def choose(self, path: Path) -> BaseParser:
        scored = self.score_candidates(path)
        _, best_cls = scored[0]
        return best_cls()

    def score_candidates(self, path: Path, head_text: str | None = None) -> list[tuple[int, Type[BaseParser]]]:
        if head_text is None:
            try:
                with path.open("r", encoding="utf-8", errors="replace") as f:
                    head_text = f.read(4096)
            except Exception:
                head_text = path.name

        scored = [(parser_cls.score(path, head_text), parser_cls) for parser_cls in self.parsers]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def parse_file(
        self,
        path: Path,
        *,
        parser_name_hint: str | None = None,
        encoding_hint: str | None = None,
        chunk_start: int | None = None,
        chunk_end: int | None = None,
    ):
        """
        Returns: (parser_name, iterable_of_raw_records)

        Behavior summary:
        - if the best parser score is too low, the file is routed to unknown_log_handler
        - parser exceptions still feed unknown_log_handler, then bubble up
        - empty parse results still feed unknown_log_handler
        - unmatched-line collection remains enabled only for smaller text files
        """

        chunked = (chunk_start not in (None, 0)) or chunk_end is not None
        hinted_cls = self._parser_by_name.get(str(parser_name_hint or "").strip() or "")
        scored = self.score_candidates(path) if hinted_cls is None else [(100, hinted_cls)]
        attempted = [{"parser_name": cls.name, "score": score} for score, cls in scored]
        min_score_threshold = int(
            (self.rules.get("active_learning", {}) or {}).get("unknown_handling", {}).get("min_score_threshold", 20)
        )
        attempted_rules = list((self.rules.get("custom_candidates") or [])[:10])

        best_score, best_cls = scored[0]
        parser = best_cls()

        if hinted_cls is None and best_score < min_score_threshold:
            self.unknown_handler.handle_file_failure(
                path=path,
                attempted_parsers=attempted,
                attempted_rules=attempted_rules,
                failure_reason=f"best parser score too low: {best_score} < {min_score_threshold}",
                parser_selected=best_cls.name,
            )
            return "unknown_log", iter(())

        try:
            iterator = iter(
                parser.parse_segment(
                    path,
                    encoding=encoding_hint,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                )
            )
        except Exception as exc:
            self.unknown_handler.handle_file_failure(
                path=path,
                attempted_parsers=attempted,
                attempted_rules=attempted_rules,
                failure_reason=f"parser exception: {exc}",
                parser_selected=best_cls.name,
            )
            raise

        try:
            first_record = next(iterator)
        except StopIteration:
            self.unknown_handler.handle_file_failure(
                path=path,
                attempted_parsers=attempted,
                attempted_rules=attempted_rules,
                failure_reason="parser returned 0 records",
                parser_selected=best_cls.name,
            )
            return best_cls.name, iter(())

        if not chunked and self._should_collect_unmatched_lines(path):
            records = [first_record, *list(iterator)]
            self._collect_unmatched_text_lines(
                path,
                parser_name=best_cls.name,
                records=records,
                attempted_parsers=attempted,
                attempted_rules=attempted_rules,
            )
            return best_cls.name, iter(records)

        return best_cls.name, chain((first_record,), iterator)

    def _should_collect_unmatched_lines(self, path: Path) -> bool:
        if path.suffix.lower() == ".csv":
            return False
        if self.unknown_scan_max_bytes <= 0:
            return False
        try:
            return int(path.stat().st_size) <= self.unknown_scan_max_bytes
        except Exception:
            return False

    def _collect_unmatched_text_lines(
        self,
        path: Path,
        parser_name: str,
        records: Iterable,
        attempted_parsers: list[dict],
        attempted_rules: list[dict],
    ) -> None:
        try:
            all_lines = list(read_text_stream(path))
        except Exception:
            return

        matched = {getattr(r, "raw_text", "").strip() for r in records if getattr(r, "raw_text", "").strip()}
        unknown_lines: list[dict] = []
        context_radius = int(
            (self.rules.get("active_learning", {}) or {}).get("unknown_handling", {}).get("context_window_lines", 2)
        )

        for idx, line in enumerate(all_lines, start=1):
            text = line.strip()
            if not text or text in matched:
                continue

            before = [x.strip() for x in all_lines[max(0, idx - 1 - context_radius) : idx - 1] if x.strip()]
            after = [x.strip() for x in all_lines[idx : idx + context_radius] if x.strip()]
            unknown_lines.append(
                {
                    "raw_text": text,
                    "line_no": idx,
                    "context_before": before,
                    "context_after": after,
                }
            )

        if unknown_lines:
            self.unknown_handler.handle_unknown_lines(
                path=path,
                unknown_lines=unknown_lines,
                attempted_parsers=attempted_parsers,
                attempted_rules=attempted_rules,
                failure_reason=f"{parser_name} left unmatched text lines",
                parser_selected=parser_name,
            )
