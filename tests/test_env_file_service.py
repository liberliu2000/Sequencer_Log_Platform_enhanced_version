from __future__ import annotations

from pathlib import Path
import shutil
import uuid

from app.services.env_file_service import EnvFileService


def _make_work_dir() -> Path:
    path = Path("data") / f"test_env_service_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_env_file_service_lists_sensitive_items_and_defaults():
    base_dir = _make_work_dir()
    try:
        env_path = base_dir / ".env"
        example_path = base_dir / ".env.example"
        env_path.write_text(
            "# base\n"
            "APP_ENV=prod\n"
            "LLM_API_KEY=secret-value\n",
            encoding="utf-8",
        )
        example_path.write_text(
            "APP_ENV=dev\n"
            "LLM_API_KEY=demo-key\n",
            encoding="utf-8",
        )

        items = EnvFileService(env_path=env_path, example_path=example_path).list_items()
        by_key = {item["key"]: item for item in items}

        assert by_key["APP_ENV"]["is_sensitive"] is False
        assert by_key["APP_ENV"]["default_value"] == "dev"
        assert by_key["APP_ENV"]["is_modified"] is True
        assert by_key["LLM_API_KEY"]["is_sensitive"] is True
        assert by_key["LLM_API_KEY"]["display_value"] != "secret-value"
        assert by_key["LLM_API_KEY"]["default_value"] == "demo-key"
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_env_file_service_preserves_comments_and_spacing_on_update():
    base_dir = _make_work_dir()
    try:
        env_path = base_dir / ".env"
        example_path = base_dir / ".env.example"
        env_path.write_text(
            "# comment block\n"
            "APP_ENV = dev  # keep this comment\n"
            'LLM_MODEL="ep-001"\n',
            encoding="utf-8",
        )
        example_path.write_text("APP_ENV=dev\nLLM_MODEL=ep-000\n", encoding="utf-8")

        service = EnvFileService(env_path=env_path, example_path=example_path)
        updated = service.update_item("APP_ENV", "prod")

        assert updated["value"] == "prod"
        assert env_path.read_text(encoding="utf-8").splitlines() == [
            "# comment block",
            "APP_ENV = prod  # keep this comment",
            'LLM_MODEL="ep-001"',
        ]
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_env_file_service_reset_uses_example_value_and_preserves_quotes():
    base_dir = _make_work_dir()
    try:
        env_path = base_dir / ".env"
        example_path = base_dir / ".env.example"
        env_path.write_text('LLM_MODEL="ep-custom"\n', encoding="utf-8")
        example_path.write_text("LLM_MODEL=ep-default\n", encoding="utf-8")

        service = EnvFileService(env_path=env_path, example_path=example_path)
        reset_item = service.reset_item("LLM_MODEL")

        assert reset_item["value"] == "ep-default"
        assert env_path.read_text(encoding="utf-8") == 'LLM_MODEL="ep-default"\n'
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_env_file_service_can_append_missing_key_from_example():
    base_dir = _make_work_dir()
    try:
        env_path = base_dir / ".env"
        example_path = base_dir / ".env.example"
        env_path.write_text("APP_ENV=dev\n", encoding="utf-8")
        example_path.write_text("APP_ENV=dev\nSYSTEM_MEMORY_SOFT_LIMIT_PERCENT=88\n", encoding="utf-8")

        service = EnvFileService(env_path=env_path, example_path=example_path)
        item = service.get_item("SYSTEM_MEMORY_SOFT_LIMIT_PERCENT")
        assert item["value"] == "88"

        updated = service.update_item("SYSTEM_MEMORY_SOFT_LIMIT_PERCENT", "90")
        assert updated["value"] == "90"
        assert "SYSTEM_MEMORY_SOFT_LIMIT_PERCENT=90" in env_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_env_file_service_quotes_special_values_and_returns_plain_text():
    base_dir = _make_work_dir()
    try:
        env_path = base_dir / ".env"
        example_path = base_dir / ".env.example"
        env_path.write_text(
            "SMTP_PASSWORD=oldpass\n"
            "SMTP_FROM_NAME=Sequencer Log Platform\n",
            encoding="utf-8",
        )
        example_path.write_text(
            "SMTP_PASSWORD=\n"
            "SMTP_FROM_NAME=Sequencer Log Platform\n"
            "CUSTOM_ALERT_MESSAGE=\n",
            encoding="utf-8",
        )

        service = EnvFileService(env_path=env_path, example_path=example_path)

        password_item = service.update_item("SMTP_PASSWORD", "abc#123")
        sender_item = service.update_item("SMTP_FROM_NAME", "Sequencer Ops #1")
        appended_item = service.update_item("CUSTOM_ALERT_MESSAGE", "line #1 ready")

        assert password_item["value"] == "abc#123"
        assert sender_item["value"] == "Sequencer Ops #1"
        assert appended_item["value"] == "line #1 ready"
        assert env_path.read_text(encoding="utf-8").splitlines() == [
            'SMTP_PASSWORD="abc#123"',
            'SMTP_FROM_NAME="Sequencer Ops #1"',
            'CUSTOM_ALERT_MESSAGE="line #1 ready"',
        ]
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
