from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.core.settings import get_settings


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _coerce_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass
class TaskState:
    task_uuid: str
    filename: str | None = None
    status: str = "uploaded"
    progress_percent: int = 0
    current_stage: str | None = None
    file_count: int = 0
    total_events: int = 0
    total_errors: int = 0
    queue_position: int | None = None
    message: str | None = None
    cpu_cores: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float | None = None
    estimated_remaining_seconds: float | None = None
    estimated_finish_at: str | None = None
    runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    progress_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskStateCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, TaskState] = {}
        self._history_limit = max(8, int(get_settings().task_progress_history_limit))

    def init_task(self, task_uuid: str, filename: str | None = None, cpu_cores: int | None = None) -> None:
        now = _now_iso()
        with self._lock:
            state = TaskState(
                task_uuid=task_uuid,
                filename=filename,
                status="uploaded",
                progress_percent=0,
                current_stage="uploaded",
                message=f"file: {filename}" if filename else None,
                cpu_cores=cpu_cores,
                created_at=now,
                updated_at=now,
            )
            self._refresh_timing(state, now)
            self._append_history(state, now, force=True)
            self._data[task_uuid] = state

    def mark_started(self, task_uuid: str) -> None:
        now = _now_iso()
        with self._lock:
            state = self._data.setdefault(task_uuid, TaskState(task_uuid=task_uuid, created_at=now, updated_at=now))
            if state.started_at is None:
                state.started_at = now
            state.updated_at = now
            self._refresh_timing(state, now)
            self._append_history(state, now, force=True)

    def mark_finished(self, task_uuid: str, status: str = "completed") -> None:
        now = _now_iso()
        with self._lock:
            state = self._data.get(task_uuid)
            if not state:
                return
            state.status = status
            state.finished_at = now
            state.updated_at = now
            if status == "completed":
                state.progress_percent = 100
                state.queue_position = None
            state.estimated_remaining_seconds = 0.0 if status == "completed" else None
            state.estimated_finish_at = now if status == "completed" else None
            self._refresh_timing(state, now)
            self._append_history(state, now, force=True)

    def update(
        self,
        task_uuid: str,
        *,
        filename: str | None = None,
        status: str | None = None,
        progress_percent: int | None = None,
        current_stage: str | None = None,
        file_count: int | None = None,
        total_events: int | None = None,
        total_errors: int | None = None,
        queue_position: int | None = None,
        message: str | None = None,
        cpu_cores: int | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> None:
        now = _now_iso()
        with self._lock:
            state = self._data.get(task_uuid)
            if not state:
                state = TaskState(task_uuid=task_uuid, created_at=now, updated_at=now)
                self._data[task_uuid] = state

            if filename is not None:
                state.filename = filename
            if status is not None:
                state.status = status
            if progress_percent is not None:
                state.progress_percent = max(0, min(int(progress_percent), 100))
            if current_stage is not None:
                state.current_stage = current_stage
            if file_count is not None:
                state.file_count = int(file_count)
            if total_events is not None:
                state.total_events = int(total_events)
            if total_errors is not None:
                state.total_errors = int(total_errors)
            if queue_position is not None:
                state.queue_position = queue_position
            if message is not None:
                state.message = message
            if cpu_cores is not None:
                state.cpu_cores = cpu_cores
            if runtime_snapshot is not None:
                state.runtime_snapshot = dict(runtime_snapshot)
            if state.started_at is None and (state.status == "processing" or (state.progress_percent or 0) > 0):
                state.started_at = now

            state.updated_at = now
            if state.progress_percent >= 100 and state.status == "completed" and state.finished_at is None:
                state.finished_at = now
            self._refresh_timing(state, now)
            self._append_history(state, now)

    def get(self, task_uuid: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._data.get(task_uuid)
            if not state:
                return None
            now = _now_iso()
            self._refresh_timing(state, now)
            return state.to_dict()

    def remove(self, task_uuid: str) -> None:
        with self._lock:
            self._data.pop(task_uuid, None)

    def _refresh_timing(self, state: TaskState, now_text: str) -> None:
        started = _coerce_datetime(state.started_at)
        current = _coerce_datetime(state.finished_at or now_text)
        if started is not None and current is not None:
            state.elapsed_seconds = round(max((current - started).total_seconds(), 0.0), 3)
        elif state.elapsed_seconds is None:
            state.elapsed_seconds = None

        if state.status in {"completed", "failed", "error"}:
            if state.status == "completed":
                state.estimated_remaining_seconds = 0.0
                state.estimated_finish_at = state.finished_at or now_text
            else:
                state.estimated_remaining_seconds = None
                state.estimated_finish_at = None
            return

        remaining, finish_at = self._estimate_remaining(state, now_text)
        state.estimated_remaining_seconds = remaining
        state.estimated_finish_at = finish_at

    def _estimate_remaining(self, state: TaskState, now_text: str) -> tuple[float | None, str | None]:
        progress_now = max(0, min(int(state.progress_percent or 0), 100))
        if progress_now <= 0 or progress_now >= 100:
            return None, None

        now_dt = _coerce_datetime(now_text)
        if now_dt is None:
            return None, None

        recent = [entry for entry in state.progress_history if entry.get("progress_percent") is not None]
        recent = recent[-8:]
        base_time: datetime | None = None
        base_progress: int | None = None

        for entry in reversed(recent[:-1]):
            try:
                entry_progress = int(entry.get("progress_percent") or 0)
            except Exception:
                continue
            if entry_progress >= progress_now:
                continue
            entry_time = _coerce_datetime(entry.get("timestamp"))
            if entry_time is None:
                continue
            base_time = entry_time
            base_progress = entry_progress
            break

        if base_time is None or base_progress is None:
            started = _coerce_datetime(state.started_at)
            if started is None or started >= now_dt:
                return None, None
            base_time = started
            base_progress = 0

        elapsed = (now_dt - base_time).total_seconds()
        delta = progress_now - base_progress
        if elapsed <= 0 or delta <= 0:
            return None, None

        remaining = round((100 - progress_now) * (elapsed / delta), 3)
        finish_at = now_dt + timedelta(seconds=remaining)
        return remaining, finish_at.isoformat(timespec="seconds")

    def _append_history(self, state: TaskState, now_text: str, *, force: bool = False) -> None:
        snapshot = {
            "timestamp": now_text,
            "status": state.status,
            "progress_percent": int(state.progress_percent or 0),
            "current_stage": state.current_stage,
            "message": state.message,
            "elapsed_seconds": state.elapsed_seconds,
        }

        if state.progress_history and not force:
            previous = state.progress_history[-1]
            if (
                previous.get("status") == snapshot["status"]
                and previous.get("progress_percent") == snapshot["progress_percent"]
                and previous.get("current_stage") == snapshot["current_stage"]
                and previous.get("message") == snapshot["message"]
            ):
                previous["timestamp"] = now_text
                previous["elapsed_seconds"] = state.elapsed_seconds
                return

        state.progress_history.append(snapshot)
        if len(state.progress_history) > self._history_limit:
            state.progress_history = state.progress_history[-self._history_limit :]


task_state_cache = TaskStateCache()
