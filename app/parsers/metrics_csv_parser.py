from __future__ import annotations

import csv
from pathlib import Path

from app.parsers.base import BaseParser
from app.schemas.common import RawLogRecord
from app.utils.files import detect_encoding
from app.utils.text import infer_chip_name, infer_cycle_from_text


class MetricsCsvParser(BaseParser):
    name = "metrics_csv"

    @classmethod
    def score(cls, path: Path, head_text: str) -> int:
        score = 0
        if path.suffix.lower() == ".csv":
            score += 10
        lowered = head_text.lower()
        if any(k in lowered for k in ["cycle", "fov", "scanner", "board", "chip_name", "slide", "flowcell id"]):
            score += 50
        if "imagingmetrics" in str(path).lower() or "fovmetrics" in str(path).lower():
            score += 40
        return score

    def parse(self, path: Path):
        encoding = detect_encoding(path)
        with path.open("r", encoding=encoding, errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                row = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None}
                if not row:
                    continue
                source_hint = f"{path.name} row={idx}"
                file_text = f"{path.name} {' '.join(f'{k}={v}' for k, v in row.items())}"
                ts = row.get("DateTime") or row.get("time") or row.get("timestamp") or row.get("datetime")
                level = (row.get("level") or "INFO").upper()
                component = row.get("board") or row.get("scanner") or row.get("module")
                component = component or ("FOVMetrics" if "Flowcell Id" in row else "ImagingMetrics")
                cycle_no = row.get("Cycle") or infer_cycle_from_text(path.name)
                chip_name = row.get("Flowcell Id") or row.get("chip_name") or infer_chip_name(path.name, file_text)

                if component == "ImagingMetrics":
                    for metric_name, metric_value in row.items():
                        yield RawLogRecord(
                            source_file=path.name,
                            parser_name=self.name,
                            raw_text=source_hint,
                            original_time_text=ts,
                            level=level,
                            component=component,
                            module=component,
                            message=f"imaging metric {metric_name}={metric_value}",
                            extra={
                                **row,
                                "metric_name": metric_name,
                                "metric_value": metric_value,
                                "Cycle": cycle_no,
                                "chip_name": chip_name,
                            },
                        )
                else:
                    text = " | ".join(f"{k}={v}" for k, v in row.items())
                    yield RawLogRecord(
                        source_file=path.name,
                        parser_name=self.name,
                        raw_text=text,
                        original_time_text=ts,
                        level=level,
                        component=component,
                        module=component,
                        message=text,
                        extra={**row, "Cycle": cycle_no, "chip_name": chip_name},
                    )
