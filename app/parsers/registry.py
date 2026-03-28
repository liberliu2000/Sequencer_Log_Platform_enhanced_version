from __future__ import annotations

from pathlib import Path
from typing import Type

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
    解析器注册中心。

    本次增量优化点：
    1. 保持现有 parser score 机制不变
    2. 在 parse 失败 / 解析为空 / 行级未识别时接入 unknown_log_handler
    3. 未知日志进入“待标注池”，而不是直接丢弃
    """

    def __init__(self):
        self.parsers: list[Type[BaseParser]] = [
            MetricsCsvParser,
            CsvWorkflowParser,
            ServiceLogParser,
            ErrorLogParser,
            RunErrorParser,
        ]
        self.settings = get_settings()
        self.rules = load_yaml(self.settings.parser_rules_path)
        self.unknown_handler = UnknownLogHandler()

    def choose(self, path: Path) -> BaseParser:
        scored = self.score_candidates(path)
        _, best_cls = scored[0]
        return best_cls()

    def score_candidates(self, path: Path) -> list[tuple[int, Type[BaseParser]]]:
        head_text = ""
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                head_text = f.read(4096)
        except Exception:
            head_text = path.name

        scored = [(parser_cls.score(path, head_text), parser_cls) for parser_cls in self.parsers]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def parse_file(self, path: Path):
        """
        返回: (parser_name, iterable_of_raw_records)

        行为说明：
        - 若最佳 parser score 过低，则整文件进入 unknown_log_handler
        - 若解析器抛异常，先收集未知日志，再向上抛异常
        - 若解析结果为空，整文件进入 unknown_log_handler
        - 若文本文件存在“未识别行”，逐行进入 unknown_log_handler
        """
        scored = self.score_candidates(path)
        attempted = [{"parser_name": cls.name, "score": score} for score, cls in scored]
        min_score_threshold = int(
            (self.rules.get("active_learning", {}) or {})
            .get("unknown_handling", {})
            .get("min_score_threshold", 20)
        )
        attempted_rules = list((self.rules.get("custom_candidates") or [])[:10])

        best_score, best_cls = scored[0]
        parser = best_cls()

        if best_score < min_score_threshold:
            self.unknown_handler.handle_file_failure(
                path=path,
                attempted_parsers=attempted,
                attempted_rules=attempted_rules,
                failure_reason=f"最佳 parser 分数过低: {best_score} < {min_score_threshold}",
                parser_selected=best_cls.name,
            )
            return "unknown_log", iter(())

        try:
            records = list(parser.parse(path))
        except Exception as exc:
            self.unknown_handler.handle_file_failure(
                path=path,
                attempted_parsers=attempted,
                attempted_rules=attempted_rules,
                failure_reason=f"解析器异常: {exc}",
                parser_selected=best_cls.name,
            )
            raise

        if not records:
            self.unknown_handler.handle_file_failure(
                path=path,
                attempted_parsers=attempted,
                attempted_rules=attempted_rules,
                failure_reason="解析器返回 0 条记录",
                parser_selected=best_cls.name,
            )
            return best_cls.name, iter(())

        self._collect_unmatched_text_lines(
            path,
            parser_name=best_cls.name,
            records=records,
            attempted_parsers=attempted,
            attempted_rules=attempted_rules,
        )

        return best_cls.name, iter(records)

    def _collect_unmatched_text_lines(
        self,
        path: Path,
        parser_name: str,
        records: list,
        attempted_parsers: list[dict],
        attempted_rules: list[dict],
    ) -> None:
        """
        对于文本类日志，如果 parser 只匹配了部分行，则把未识别行送入未知日志池。
        - 只对非 CSV 文件执行
        - 仅做低侵入补收集，不改变原解析结果
        """
        if path.suffix.lower() == ".csv":
            return

        try:
            all_lines = list(read_text_stream(path))
        except Exception:
            return

        matched = {getattr(r, "raw_text", "").strip() for r in records if getattr(r, "raw_text", "").strip()}
        unknown_lines: list[dict] = []

        context_radius = int(
            (self.rules.get("active_learning", {}) or {})
            .get("unknown_handling", {})
            .get("context_window_lines", 2)
        )

        for idx, line in enumerate(all_lines, start=1):
            text = line.strip()
            if not text:
                continue
            if text in matched:
                continue

            before = [x.strip() for x in all_lines[max(0, idx - 1 - context_radius): idx - 1] if x.strip()]
            after = [x.strip() for x in all_lines[idx: idx + context_radius] if x.strip()]

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
                failure_reason=f"{parser_name} 未识别部分文本行",
                parser_selected=parser_name,
            )
