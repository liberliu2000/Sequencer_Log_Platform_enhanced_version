from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.common import RawLogRecord


class BaseParser(ABC):
    name = "base"
    supports_parallel_chunks = False

    @classmethod
    @abstractmethod
    def score(cls, path: Path, head_text: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def parse(self, path: Path, *, encoding: str | None = None):
        raise NotImplementedError

    def parse_segment(
        self,
        path: Path,
        *,
        encoding: str | None = None,
        chunk_start: int | None = None,
        chunk_end: int | None = None,
    ):
        if (chunk_start not in (None, 0)) or chunk_end is not None:
            raise NotImplementedError(f"{self.name} does not support chunked parsing")
        return self.parse(path, encoding=encoding)
