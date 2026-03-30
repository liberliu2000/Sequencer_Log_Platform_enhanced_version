from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Lock, Thread
from typing import Callable

from app.core.settings import get_settings


class TaskQueue:
    def __init__(self, max_workers: int | None = None):
        settings = get_settings()
        worker_count = max_workers or settings.queue_dispatch_workers or settings.task_queue_workers or 2
        self.executor = ThreadPoolExecutor(max_workers=max(1, worker_count), thread_name_prefix="sequencer-worker")
        self.queue: Queue[tuple[str, Callable[[], None]]] = Queue()
        self.pending: list[str] = []
        self.lock = Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        t = Thread(target=self._consume, daemon=True, name="sequencer-queue-dispatcher")
        t.start()

    def _consume(self) -> None:
        while True:
            task_uuid, func = self.queue.get()
            with self.lock:
                if task_uuid in self.pending:
                    self.pending.remove(task_uuid)
            self.executor.submit(func)
            self.queue.task_done()

    def submit(self, task_uuid: str, func: Callable[[], None]) -> int:
        self.start()
        with self.lock:
            self.pending.append(task_uuid)
            position = len(self.pending)
        self.queue.put((task_uuid, func))
        return position

    def queue_position(self, task_uuid: str) -> int | None:
        with self.lock:
            try:
                return self.pending.index(task_uuid) + 1
            except ValueError:
                return None


queue = TaskQueue()
