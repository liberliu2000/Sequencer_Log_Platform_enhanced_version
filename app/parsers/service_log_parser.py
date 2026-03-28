from __future__ import annotations

import re
from pathlib import Path

from app.parsers.base import BaseParser
from app.schemas.common import RawLogRecord
from app.utils.files import read_text_stream

SERVICE_RE = re.compile(
    r"^(?P<ts>\d{4}[-/]\d{2}[-/]\d{2} \d{2}:\d{2}:\d{2}[.:]\d{3,6})\s*\|\s*"
    r"(?P<level>[A-Z]+)\s*\|\s*(?P<thread>[^|]*)\|\s*(?P<module>[^|]*)\|\s*"
    r"(?P<msg>.*?)\s*\|\s*(?P<class_name>[^|]*)\|\s*(?P<method>[^|]*)\|\s*(?P<path>.*)$"
)


class ServiceLogParser(BaseParser):
    name = "service_log"

    @classmethod
    def score(cls, path: Path, head_text: str) -> int:
        score = 0
        if path.suffix.lower() == ".log":
            score += 20
        if "|" in head_text:
            score += 20
        if "INFO |" in head_text or "ERROR |" in head_text or ".cs:" in head_text:
            score += 50
        return score

    def parse(self, path: Path):
        for line in read_text_stream(path):
            m = SERVICE_RE.match(line)
            if not m:
                continue
            path_text = m.group("path").strip()
            line_no = None
            if ":" in path_text and path_text.rsplit(":", 1)[-1].isdigit():
                line_no = int(path_text.rsplit(":", 1)[-1])
            yield RawLogRecord(
                source_file=path.name,
                parser_name=self.name,
                raw_text=line,
                original_time_text=m.group("ts"),
                level=m.group("level").upper(),
                component=m.group("module").strip() or None,
                module=m.group("module").strip() or None,
                thread=m.group("thread").strip() or None,
                class_name=m.group("class_name").strip() or None,
                method_name=m.group("method").strip() or None,
                source_path=path_text,
                line_no=line_no,
                message=m.group("msg").strip(),
            )
