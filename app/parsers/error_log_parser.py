from __future__ import annotations

import re
from pathlib import Path

from app.parsers.base import BaseParser
from app.schemas.common import RawLogRecord
from app.utils.files import read_text_stream

ERROR_RE = re.compile(
    r"^(?P<ts>\d{4}[-/]\d{2}[-/]\d{2} \d{2}:\d{2}:\d{2}[.:]\d{3,6})\s*\|\s*"
    r"(?P<level>WARN|ERROR|FATAL)\s*\|\s*(?P<thread>[^|]*)\|\s*(?P<module>[^|]*)\|\s*(?P<msg>.*)$"
)


class ErrorLogParser(BaseParser):
    name = "error_log"

    @classmethod
    def score(cls, path: Path, head_text: str) -> int:
        score = 0
        if path.name.lower().startswith("errorlogs"):
            score += 40
        if "WARN" in head_text or "ERROR" in head_text or "FATAL" in head_text:
            score += 35
        if "timeout" in head_text.lower() or "exception" in head_text.lower():
            score += 35
        if "|" in head_text:
            score += 15
        return score

    def parse(self, path: Path):
        buffer: list[str] = []
        current_header: dict | None = None
        for line in read_text_stream(path):
            m = ERROR_RE.match(line)
            if m:
                if current_header:
                    raw_text = "\n".join(buffer) if buffer else current_header["msg"]
                    yield RawLogRecord(
                        source_file=path.name,
                        parser_name=self.name,
                        raw_text=raw_text,
                        original_time_text=current_header["ts"],
                        level=current_header["level"],
                        component=current_header["module"],
                        module=current_header["module"],
                        thread=current_header["thread"],
                        message=current_header["msg"],
                        extra={"stack": "\n".join(buffer[1:]) if len(buffer) > 1 else ""},
                    )
                current_header = m.groupdict()
                buffer = [line]
            elif current_header:
                buffer.append(line)
        if current_header:
            raw_text = "\n".join(buffer) if buffer else current_header["msg"]
            yield RawLogRecord(
                source_file=path.name,
                parser_name=self.name,
                raw_text=raw_text,
                original_time_text=current_header["ts"],
                level=current_header["level"],
                component=current_header["module"],
                module=current_header["module"],
                thread=current_header["thread"],
                message=current_header["msg"],
                extra={"stack": "\n".join(buffer[1:]) if len(buffer) > 1 else ""},
            )
