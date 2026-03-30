from pathlib import Path

from app.parsers.registry import ParserRegistry


def test_registry_choose_csv(tmp_path: Path):
    p = tmp_path / "workflow.csv"
    p.write_text("2,2026/03/18 09:45:18.644,2026/03/18 09:45:18.000,Info,System,Script started. TEST\n", encoding="utf-8")
    parser = ParserRegistry().choose(p)
    assert parser.name in {"csv_workflow", "metrics_csv"}


def test_registry_choose_service(tmp_path: Path):
    p = tmp_path / "service.log"
    p.write_text(
        "2026-03-18 09:46:49.1052 | INFO | 242 | Script294 | SetCamDirection is success . 1-1-0-0 | | SetCameraDirection | D:\\Code\\VGiraffeOpticsBoard.cs:445\n",
        encoding="utf-8",
    )
    parser = ParserRegistry().choose(p)
    assert parser.name == "service_log"
