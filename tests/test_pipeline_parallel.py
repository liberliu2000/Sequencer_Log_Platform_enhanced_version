from __future__ import annotations

from app.services.pipeline_parallel import (
    build_parse_dispatch_items,
    compute_optimal_parse_chunks,
    compute_weighted_progress,
    parse_item_weight,
    prioritize_parse_dispatch,
)


def test_parse_item_weight_never_returns_zero() -> None:
    assert parse_item_weight({}) == 1
    assert parse_item_weight({"size_bytes": 0}) == 1
    assert parse_item_weight({"size_bytes": 128}) == 128


def test_prioritize_parse_dispatch_schedules_larger_files_first() -> None:
    items = [
        {"path": "/tmp/b.log", "size_bytes": 10},
        {"path": "/tmp/a.log", "size_bytes": 100},
        {"path": "/tmp/c.log", "size_bytes": 100},
    ]

    ordered = prioritize_parse_dispatch(items)

    assert [item["path"] for item in ordered] == [
        "/tmp/a.log",
        "/tmp/c.log",
        "/tmp/b.log",
    ]


def test_compute_weighted_progress_tracks_completed_work() -> None:
    total_weight = 1_000

    assert compute_weighted_progress(0, total_weight, 26, 34) == 26
    assert compute_weighted_progress(500, total_weight, 26, 34) == 43
    assert compute_weighted_progress(1_000, total_weight, 26, 34) == 60


def test_compute_optimal_parse_chunks_caps_prefetch_depth() -> None:
    assert compute_optimal_parse_chunks(total_files=3, workers=4, configured_batch_size=64) == 3
    assert compute_optimal_parse_chunks(total_files=120, workers=4, configured_batch_size=64) == 16
    assert compute_optimal_parse_chunks(total_files=120, workers=8, configured_batch_size=1) == 16


def test_build_parse_dispatch_items_splits_large_chunk_capable_file() -> None:
    items = build_parse_dispatch_items(
        [
            {
                "path": "/tmp/big.log",
                "size_bytes": 350,
                "parser_name": "service_log",
                "chunk_capable": True,
            }
        ],
        streaming_enabled=True,
        chunk_bytes=100,
        max_chunks_per_file=8,
    )

    assert len(items) == 4
    assert [item["dispatch_kind"] for item in items] == ["chunk", "chunk", "chunk", "chunk"]
    assert [item["chunk_index"] for item in items] == [0, 1, 2, 3]
    assert items[0]["chunk_start"] == 0
    assert items[-1]["chunk_end"] == 350


def test_build_parse_dispatch_items_keeps_non_chunk_dispatch_for_small_or_unsupported_files() -> None:
    items = build_parse_dispatch_items(
        [
            {
                "path": "/tmp/a.log",
                "size_bytes": 64,
                "parser_name": "service_log",
                "chunk_capable": True,
            },
            {
                "path": "/tmp/b.csv",
                "size_bytes": 10_000,
                "parser_name": "metrics_csv",
                "chunk_capable": False,
            },
        ],
        streaming_enabled=True,
        chunk_bytes=1024,
        max_chunks_per_file=8,
    )

    assert len(items) == 2
    assert [item["dispatch_kind"] for item in items] == ["file", "file"]
    assert all(item["chunk_start"] is None and item["chunk_end"] is None for item in items)
