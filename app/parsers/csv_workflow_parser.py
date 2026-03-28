from __future__ import annotations

import csv
from pathlib import Path

from app.parsers.base import BaseParser
from app.schemas.common import RawLogRecord
from app.utils.files import detect_encoding


class CsvWorkflowParser(BaseParser):
    name = "csv_workflow"

    @classmethod
    def score(cls, path: Path, head_text: str) -> int:
        score = 0
        if path.suffix.lower() == ".csv":
            score += 40
        else:
            return 0
        if "Script started" in head_text or "Workflow" in head_text or "span time" in head_text:
            score += 50
        if "," in head_text:
            score += 20
        if "T100_Workflow" in path.name:
            score += 30
        return score

    def parse(self, path: Path):
        encoding = detect_encoding(path)
        with path.open("r", encoding=encoding, errors="replace", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 6:
                    continue
                msg = ",".join(row[5:]).strip() if len(row) > 5 else row[-1].strip()
                if not msg:
                    continue
                yield RawLogRecord(
                    source_file=path.name,
                    parser_name=self.name,
                    raw_text=",".join(row),
                    original_time_text=row[1].strip() if len(row) > 1 else None,
                    level=(row[3].strip() if len(row) > 3 else "INFO").upper(),
                    component=row[4].strip() if len(row) > 4 else "System",
                    module=row[4].strip() if len(row) > 4 else "System",
                    message=msg,
                    extra={"csv_row": row, "workflow_stage": path.stem},
                )
