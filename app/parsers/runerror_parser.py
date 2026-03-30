from __future__ import annotations

import re
from pathlib import Path

from app.parsers.base import BaseParser
from app.schemas.common import RawLogRecord
from app.utils.files import read_text_stream
from app.utils.timeparse import extract_first_datetime

HEADER_RE = re.compile(r"(Exception|RunError|Traceback|Unhandled|StackTrace)", re.IGNORECASE)


class RunErrorParser(BaseParser):
    name = "runerror"

    @classmethod
    def score(cls, path: Path, head_text: str) -> int:
        score = 0
        if "Traceback" in head_text or "Exception" in head_text or "StackTrace" in head_text:
            score += 60
        return score

    def parse(self, path: Path):
        buffer: list[str] = []
        current_time: str | None = None
        level = "ERROR"
        for line in read_text_stream(path):
            ts = extract_first_datetime(line)
            if ts and HEADER_RE.search(line) and buffer:
                yield RawLogRecord(
                    source_file=path.name,
                    parser_name=self.name,
                    raw_text="\n".join(buffer),
                    original_time_text=current_time,
                    level=level,
                    component=None,
                    module=None,
                    message=buffer[0],
                    extra={"stack": "\n".join(buffer[1:])},
                )
                buffer = []
            if HEADER_RE.search(line) and not buffer:
                current_time = ts or current_time
                buffer.append(line)
                continue
            if buffer:
                buffer.append(line)
        if buffer:
            yield RawLogRecord(
                source_file=path.name,
                parser_name=self.name,
                raw_text="\n".join(buffer),
                original_time_text=current_time,
                level=level,
                component=None,
                module=None,
                message=buffer[0],
                extra={"stack": "\n".join(buffer[1:])},
            )
