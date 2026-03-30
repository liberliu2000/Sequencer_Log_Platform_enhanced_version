from __future__ import annotations

import pytest

from scripts.release_sync import bump_version, is_excluded_path, normalize_version, parse_status_paths


def test_normalize_version_accepts_semver() -> None:
    assert normalize_version("v1.2.3") == "v1.2.3"


@pytest.mark.parametrize("value", ["1.2.3", "v1.2", "v1.2.x", "vx.y.z"])
def test_normalize_version_rejects_invalid_values(value: str) -> None:
    with pytest.raises(Exception):
        normalize_version(value)


def test_bump_version_respects_semver_rules() -> None:
    assert bump_version("v1.2.3", "patch") == "v1.2.4"
    assert bump_version("v1.2.3", "minor") == "v1.3.0"
    assert bump_version("v1.2.3", "major") == "v2.0.0"


@pytest.mark.parametrize(
    ("path_text", "expected"),
    [
        ("app/main.py", False),
        ("README.md", False),
        ("config/parser_rules.yaml", False),
        (".env.example", False),
        (".venv/Lib/site-packages/pip/__init__.py", True),
        ("tests/__pycache__/test_api_basic.cpython-312.pyc", True),
        ("data/uploads/log.7z", True),
        ("analysis_results/output.json", True),
        ("metrics/report.csv", True),
        ("uploads/user.docx", True),
        ("pytest-cache-files-123/state.txt", True),
        (".env", True),
        ("local_config.py", True),
    ],
)
def test_is_excluded_path_matches_release_rules(path_text: str, expected: bool) -> None:
    assert is_excluded_path(path_text) is expected


def test_parse_status_paths_extracts_regular_and_renamed_files() -> None:
    status_output = "\n".join(
        [
            " M app/main.py",
            "?? VERSION",
            "R  scripts/old_name.py -> scripts/new_name.py",
            " D scripts/obsolete.py",
        ]
    )

    assert parse_status_paths(status_output) == [
        "app/main.py",
        "VERSION",
        "scripts/old_name.py",
        "scripts/new_name.py",
        "scripts/obsolete.py",
    ]
