from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.common import RawLogRecord


class BaseParser(ABC):
    name = "base"

    @classmethod
    @abstractmethod
    def score(cls, path: Path, head_text: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def parse(self, path: Path):
        raise NotImplementedError
