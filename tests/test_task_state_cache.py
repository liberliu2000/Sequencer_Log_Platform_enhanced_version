from __future__ import annotations

import app.services.task_state_cache as task_state_cache_module


def test_task_state_cache_tracks_history_and_eta(monkeypatch):
    timestamps = iter(
        [
            "2026-01-01T00:00:00",
            "2026-01-01T00:00:01",
            "2026-01-01T00:00:11",
            "2026-01-01T00:00:21",
            "2026-01-01T00:00:31",
            "2026-01-01T00:00:32",
            "2026-01-01T00:00:33",
            "2026-01-01T00:00:34",
        ]
    )
    monkeypatch.setattr(task_state_cache_module, "_now_iso", lambda: next(timestamps))

    cache = task_state_cache_module.TaskStateCache()
    cache.init_task("task-1", filename="sample.log", cpu_cores=2)
    cache.mark_started("task-1")
    cache.update("task-1", status="processing", progress_percent=10, current_stage="parsing", message="parsing file")
    cache.update("task-1", status="processing", progress_percent=50, current_stage="aggregating", message="streaming aggregate")
    snapshot = cache.get("task-1")

    assert snapshot is not None
    assert snapshot["filename"] == "sample.log"
    assert snapshot["status"] == "processing"
    assert snapshot["estimated_remaining_seconds"] is not None
    assert snapshot["estimated_remaining_seconds"] > 0
    assert snapshot["estimated_finish_at"] is not None
    assert len(snapshot["progress_history"]) >= 4

    cache.update("task-1", status="completed", progress_percent=100, current_stage="completed", message="done")
    cache.mark_finished("task-1", status="completed")
    completed = cache.get("task-1")

    assert completed is not None
    assert completed["estimated_remaining_seconds"] == 0.0
    assert completed["finished_at"] is not None
    assert completed["progress_history"][-1]["status"] == "completed"
