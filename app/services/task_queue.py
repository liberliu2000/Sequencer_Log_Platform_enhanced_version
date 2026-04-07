from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Lock, Thread
from typing import Callable

from app.core.settings import get_settings
from app.services.system_runtime_service import SystemRuntimeService
from app.services.task_state_cache import task_state_cache


class TaskQueue:
    def __init__(self, max_workers: int | None = None):
        settings = get_settings()
        worker_count = max_workers or settings.queue_dispatch_workers or settings.task_queue_workers or 2
        self.executor = ThreadPoolExecutor(max_workers=max(1, worker_count), thread_name_prefix="sequencer-worker")
        self.queue: Queue[tuple[str, Callable[[], None]]] = Queue(maxsize=max(1, int(settings.queue_maxsize)))
        self.pending: list[str] = []
        self.cancelled: set[str] = set()
        self.lock = Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        dispatcher = Thread(target=self._consume, daemon=True, name="sequencer-queue-dispatcher")
        dispatcher.start()

    def _consume(self) -> None:
        while True:
            task_uuid, func = self.queue.get()
            try:
                while True:
                    with self.lock:
                        if task_uuid in self.cancelled:
                            self.cancelled.discard(task_uuid)
                            if task_uuid in self.pending:
                                self.pending.remove(task_uuid)
                            break

                    guard = SystemRuntimeService().dispatch_guard()
                    if guard.get("dispatch_allowed"):
                        with self.lock:
                            if task_uuid in self.pending:
                                self.pending.remove(task_uuid)
                            self.cancelled.discard(task_uuid)
                        self.executor.submit(func)
                        break

                    task_state_cache.update(
                        task_uuid,
                        status="queued",
                        current_stage="waiting_for_resource_window",
                        queue_position=self.queue_position(task_uuid),
                        message=f"{guard.get('summary')}; running tasks stay uninterrupted.",
                        runtime_snapshot={"guard": guard},
                    )
                    time.sleep(max(2, int(guard.get("guard_wait_seconds") or 5)))
            finally:
                self.queue.task_done()

    def submit(self, task_uuid: str, func: Callable[[], None]) -> int:
        self.start()
        with self.lock:
            self.cancelled.discard(task_uuid)
            self.pending.append(task_uuid)
            position = len(self.pending)
        self.queue.put((task_uuid, func))
        return position

    def cancel(self, task_uuid: str) -> None:
        with self.lock:
            self.cancelled.add(task_uuid)
            if task_uuid in self.pending:
                self.pending.remove(task_uuid)

    def queue_position(self, task_uuid: str) -> int | None:
        with self.lock:
            try:
                return self.pending.index(task_uuid) + 1
            except ValueError:
                return None


queue = TaskQueue()
