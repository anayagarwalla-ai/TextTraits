from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable


@dataclass(frozen=True)
class HubSpotSyncOperation:
    name: str
    execute: Callable[[], dict[str, Any]]


def _configured_worker_count() -> int:
    try:
        configured = int(os.getenv("TEXTTRAITS_HUBSPOT_SYNC_WORKERS", "4"))
    except ValueError:
        configured = 4
    return max(1, min(configured, 8))


@lru_cache(maxsize=1)
def _sync_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(
        max_workers=_configured_worker_count(),
        thread_name_prefix="hubspot-sync",
    )


def run_hubspot_sync_operations(
    operations: list[HubSpotSyncOperation],
    error_mapper: Callable[[str, Exception], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not operations:
        return [], []
    ordered_results: dict[int, dict[str, Any]] = {}
    ordered_errors: dict[int, dict[str, Any]] = {}
    executor = _sync_executor()
    futures = {executor.submit(operation.execute): (index, operation.name) for index, operation in enumerate(operations)}
    for future in as_completed(futures):
        index, name = futures[future]
        try:
            ordered_results[index] = future.result()
        except Exception as error:
            ordered_errors[index] = error_mapper(name, error)
    return (
        [ordered_results[index] for index in sorted(ordered_results)],
        [ordered_errors[index] for index in sorted(ordered_errors)],
    )
