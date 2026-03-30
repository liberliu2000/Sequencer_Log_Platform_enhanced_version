from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import datetime


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


@dataclass
class TaskState:
    task_uuid: str
    status: str = "uploaded"
    progress_percent: int = 0
    current_stage: str | None = None
    file_count: int = 0
    queue_position: int | None = None
    message: str | None = None
    cpu_cores: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class TaskStateCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, TaskState] = {}

    def init_task(self, task_uuid: str, filename: str | None = None, cpu_cores: int | None = None) -> None:
        now = _now_iso()
        with self._lock:
            self._data[task_uuid] = TaskState(
                task_uuid=task_uuid,
                status="uploaded",
                progress_percent=0,
                current_stage="已上传",
                message=f"文件: {filename}" if filename else None,
                cpu_cores=cpu_cores,
                created_at=now,
                updated_at=now,
            )

    def mark_started(self, task_uuid: str) -> None:
        now = _now_iso()
        with self._lock:
            state = self._data.setdefault(task_uuid, TaskState(task_uuid=task_uuid, created_at=now, updated_at=now))
            state.started_at = now
            state.updated_at = now

    def mark_finished(self, task_uuid: str, status: str = "completed") -> None:
        now = _now_iso()
        with self._lock:
            state = self._data.get(task_uuid)
            if not state:
                return
            state.status = status
            state.finished_at = now
            state.updated_at = now
            if state.started_at:
                try:
                    started = datetime.fromisoformat(state.started_at)
                    finished = datetime.fromisoformat(now)
                    state.elapsed_seconds = round((finished - started).total_seconds(), 3)
                except Exception:
                    pass

    def update(
        self,
        task_uuid: str,
        *,
        status: str | None = None,
        progress_percent: int | None = None,
        current_stage: str | None = None,
        file_count: int | None = None,
        queue_position: int | None = None,
        message: str | None = None,
        cpu_cores: int | None = None,
    ) -> None:
        now = _now_iso()
        with self._lock:
            state = self._data.get(task_uuid)
            if not state:
                state = TaskState(task_uuid=task_uuid, created_at=now, updated_at=now)
                self._data[task_uuid] = state

            if status is not None:
                state.status = status
            if progress_percent is not None:
                state.progress_percent = max(0, min(int(progress_percent), 100))
            if current_stage is not None:
                state.current_stage = current_stage
            if file_count is not None:
                state.file_count = int(file_count)
            if queue_position is not None:
                state.queue_position = queue_position
            if message is not None:
                state.message = message
            if cpu_cores is not None:
                state.cpu_cores = cpu_cores
            state.updated_at = now
            if state.started_at:
                try:
                    started = datetime.fromisoformat(state.started_at)
                    updated = datetime.fromisoformat(now)
                    state.elapsed_seconds = round((updated - started).total_seconds(), 3)
                except Exception:
                    pass

    def get(self, task_uuid: str) -> dict | None:
        with self._lock:
            state = self._data.get(task_uuid)
            return state.to_dict() if state else None

    def remove(self, task_uuid: str) -> None:
        with self._lock:
            self._data.pop(task_uuid, None)


task_state_cache = TaskStateCache()
