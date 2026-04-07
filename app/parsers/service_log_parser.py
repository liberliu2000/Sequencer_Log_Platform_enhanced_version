from __future__ import annotations

import re
from pathlib import Path

from app.parsers.base import BaseParser
from app.schemas.common import build_raw_log_record
from app.utils.files import read_text_byte_range, read_text_stream

TIMESTAMP_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2} \d{2}:\d{2}:\d{2}[.:]\d{3,6}$")
LEVEL_RE = re.compile(r"^[A-Z]+$")
FIELD_SPLIT_RE = re.compile(r"\s*\|\s*")


def _split_service_fields(line: str) -> list[str]:
    return [part.strip() for part in FIELD_SPLIT_RE.split(line.rstrip("\r\n"), maxsplit=8)]


def _extract_line_no(path_text: str, fallback: str | None = None) -> int | None:
    text = str(path_text or "").strip()
    if ":" in text and text.rsplit(":", 1)[-1].isdigit():
        return int(text.rsplit(":", 1)[-1])
    raw_fallback = str(fallback or "").strip()
    return int(raw_fallback) if raw_fallback.isdigit() else None


class ServiceLogParser(BaseParser):
    name = "service_log"
    supports_parallel_chunks = True

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

    def parse(self, path: Path, *, encoding: str | None = None):
        yield from self.parse_segment(path, encoding=encoding)

    def parse_segment(
        self,
        path: Path,
        *,
        encoding: str | None = None,
        chunk_start: int | None = None,
        chunk_end: int | None = None,
    ):
        source_iter = (
            read_text_byte_range(path, encoding=encoding or "utf-8", start=chunk_start or 0, end=chunk_end)
            if (chunk_start not in (None, 0) or chunk_end is not None)
            else read_text_stream(path, encoding=encoding)
        )
        for line in source_iter:
            fields = _split_service_fields(line)
            if len(fields) < 8 or not TIMESTAMP_RE.match(fields[0]):
                continue

            ts = fields[0]
            component = None
            module = None
            level = None
            thread = None
            class_name = None
            method_name = None
            path_text = ""
            message = ""
            fallback_line_no = None

            if len(fields) >= 9 and LEVEL_RE.match(fields[2].upper()):
                component = fields[1] or None
                module = component
                level = fields[2].upper()
                fallback_line_no = fields[3]
                thread = fields[4] or None
                message = fields[5]
                class_name = fields[6] or None
                method_name = fields[7] or None
                path_text = fields[8]
            elif LEVEL_RE.match(fields[1].upper()):
                level = fields[1].upper()
                fallback_line_no = fields[2]
                thread = fields[3] or None
                message = fields[4]
                class_name = fields[5] or None
                method_name = fields[6] or None
                path_text = fields[7]
            else:
                continue

            yield build_raw_log_record(
                source_file=path.name,
                parser_name=self.name,
                raw_text=line,
                original_time_text=ts,
                level=level,
                component=component,
                module=module,
                thread=thread,
                class_name=class_name,
                method_name=method_name,
                source_path=path_text,
                line_no=_extract_line_no(path_text, fallback_line_no),
                message=message.strip(),
            )
