from __future__ import annotations

from dataclasses import dataclass
import errno
from pathlib import Path
import re

from app.core.settings import BASE_DIR, get_settings


SENSITIVE_KEYWORDS = ("api", "key", "token", "secret", "password")
ENV_LINE_RE = re.compile(
    r"^(?P<leading>\s*)(?:(?P<export>export)(?P<export_ws>\s+))?(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<separator>\s*=\s*)(?P<value_and_comment>.*?)(?P<newline>\r?\n?)$"
)


@dataclass
class EnvEntry:
    key: str
    value: str
    original_value: str
    line_index: int
    line: str
    leading: str
    export_prefix: str
    separator: str
    value_prefix: str
    value_suffix: str
    inline_comment: str
    newline: str


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def _split_value_and_comment(raw: str) -> tuple[str, str]:
    quote_char: str | None = None
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote_char is not None:
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote_char is None:
                quote_char = char
            elif quote_char == char:
                quote_char = None
            continue
        if char == "#" and quote_char is None:
            return raw[:index], raw[index:]
    return raw, ""


def _mask_value(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * max(4, len(text) - 4)}{text[-2:]}"


def _unescape_quoted_value(text: str, quote: str) -> str:
    result: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            if char in {"\\", quote}:
                result.append(char)
            else:
                result.extend(["\\", char])
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        result.append(char)
    if escaped:
        result.append("\\")
    return "".join(result)


def _decode_env_value(raw_value: str) -> str:
    stripped = raw_value.strip()
    if len(stripped) < 2 or stripped[0] != stripped[-1] or stripped[0] not in {"'", '"'}:
        return raw_value
    return _unescape_quoted_value(stripped[1:-1], stripped[0])


def _quote_value(value: str, quote: str) -> str:
    escaped = value.replace("\\", "\\\\")
    if quote == '"':
        escaped = escaped.replace('"', '\\"')
    else:
        escaped = escaped.replace("'", "\\'")
    return f"{quote}{escaped}{quote}"


def _should_quote_value(value: str) -> bool:
    if value == "":
        return False
    return (
        value != value.strip()
        or any(char.isspace() for char in value)
        or any(char in value for char in ("#", "\n", "\r", '"', "'"))
    )


def _render_env_value(source_value: str, new_value: str) -> str:
    stripped = source_value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return _quote_value(new_value, stripped[0])
    if _should_quote_value(new_value):
        return _quote_value(new_value, '"')
    return new_value


class EnvFileService:
    def __init__(self, env_path: Path | None = None, example_path: Path | None = None):
        self.env_path = env_path or (BASE_DIR / ".env")
        self.example_path = example_path or (BASE_DIR / ".env.example")

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        try:
            tmp_path.replace(path)
        except OSError as exc:
            if exc.errno not in {errno.EBUSY, errno.EXDEV, errno.EPERM, errno.EACCES}:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise
            path.write_text(text, encoding="utf-8")
            tmp_path.unlink(missing_ok=True)

    def _parse_entries(self, text: str) -> tuple[list[str], dict[str, EnvEntry]]:
        lines = text.splitlines(keepends=True)
        if text and not lines:
            lines = [text]
        entries: dict[str, EnvEntry] = {}
        for index, line in enumerate(lines):
            match = ENV_LINE_RE.match(line)
            if not match:
                continue
            key = match.group("key")
            value_and_comment = match.group("value_and_comment") or ""
            value_part, inline_comment = _split_value_and_comment(value_and_comment)
            value_prefix_len = len(value_part) - len(value_part.lstrip(" \t"))
            value_prefix = value_part[:value_prefix_len]
            value_with_suffix = value_part[value_prefix_len:]
            value_suffix_len = len(value_with_suffix) - len(value_with_suffix.rstrip(" \t"))
            value = value_with_suffix[: len(value_with_suffix) - value_suffix_len] if value_suffix_len else value_with_suffix
            value_suffix = value_with_suffix[len(value):]
            export_prefix = ""
            if match.group("export"):
                export_prefix = f"{match.group('export')}{match.group('export_ws') or ' '}"
            entries[key] = EnvEntry(
                key=key,
                value=_decode_env_value(value),
                original_value=value,
                line_index=index,
                line=line,
                leading=match.group("leading") or "",
                export_prefix=export_prefix,
                separator=match.group("separator") or "=",
                value_prefix=value_prefix,
                value_suffix=value_suffix,
                inline_comment=inline_comment,
                newline=match.group("newline") or "",
            )
        return lines, entries

    def _read_entries(self) -> tuple[list[str], dict[str, EnvEntry]]:
        return self._parse_entries(self._read_text(self.env_path))

    def _read_example_defaults(self) -> dict[str, str]:
        _lines, entries = self._parse_entries(self._read_text(self.example_path))
        return {key: entry.value for key, entry in entries.items()}

    def _build_item(self, key: str, current_value: str, default_value: str | None) -> dict:
        is_sensitive = _is_sensitive_key(key)
        return {
            "key": key,
            "value": current_value,
            "display_value": _mask_value(current_value) if is_sensitive else current_value,
            "default_value": default_value,
            "default_display_value": _mask_value(default_value) if is_sensitive and default_value is not None else default_value,
            "is_sensitive": is_sensitive,
            "has_default": default_value is not None,
            "is_modified": default_value is not None and current_value != default_value,
        }

    @staticmethod
    def _render_new_entry_line(key: str, value: str) -> str:
        return f"{key}={_render_env_value('', value)}\n"

    def list_items(self) -> list[dict]:
        _lines, entries = self._read_entries()
        defaults = self._read_example_defaults()
        items: list[dict] = []
        ordered_keys = list(dict.fromkeys([*entries.keys(), *defaults.keys()]))
        for key in ordered_keys:
            entry = entries.get(key)
            current_value = entry.value if entry is not None else str(defaults.get(key) or "")
            items.append(self._build_item(key, current_value, defaults.get(key)))
        return items

    def get_item(self, key: str) -> dict:
        _lines, entries = self._read_entries()
        defaults = self._read_example_defaults()
        entry = entries.get(key)
        if entry is None and key not in defaults:
            raise KeyError(key)
        default_value = defaults.get(key)
        current_value = entry.value if entry is not None else str(default_value or "")
        return self._build_item(key, current_value, default_value)

    def update_item(self, key: str, value: str) -> dict:
        lines, entries = self._read_entries()
        entry = entries.get(key)
        if entry is None:
            new_line = self._render_new_entry_line(key, str(value))
            if lines and not lines[-1].endswith(("\n", "\r\n")):
                lines[-1] = f"{lines[-1]}\n"
            lines.append(new_line)
        else:
            rendered_value = _render_env_value(entry.original_value, str(value))
            lines[entry.line_index] = (
                f"{entry.leading}{entry.export_prefix}{entry.key}{entry.separator}{entry.value_prefix}"
                f"{rendered_value}{entry.value_suffix}{entry.inline_comment}{entry.newline}"
            )
        self._write_text(self.env_path, "".join(lines))
        get_settings.cache_clear()
        return self.get_item(key)

    def reset_item(self, key: str) -> dict:
        defaults = self._read_example_defaults()
        if key not in defaults:
            raise KeyError(key)
        return self.update_item(key, defaults[key])
