"""Runtime measurement primitives.

This module deliberately measures only. It does not optimize, parallelize, cache,
or alter quantitative semantics.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class RuntimeEvent:
    category: str
    name: str
    runtime_seconds: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "runtime_seconds": round(self.runtime_seconds, 6),
            "metadata": self.metadata,
        }


class RuntimeTracker:
    """Collect nested runtime events in a deterministic structure."""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    @contextmanager
    def track(self, category: str, name: str, **metadata: Any) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(category, name, time.perf_counter() - started, metadata)

    def record(self, category: str, name: str, runtime_seconds: float, metadata: dict[str, Any] | None = None) -> None:
        self.events.append(RuntimeEvent(category, name, runtime_seconds, metadata or {}))

    def summary(self) -> dict[str, Any]:
        by_category: dict[str, dict[str, Any]] = {}
        for event in self.events:
            bucket = by_category.setdefault(event.category, {"count": 0, "runtime_seconds": 0.0})
            bucket["count"] += 1
            bucket["runtime_seconds"] += event.runtime_seconds
        return {
            "event_count": len(self.events),
            "total_runtime_seconds": round(sum(event.runtime_seconds for event in self.events), 6),
            "by_category": {
                category: {
                    "count": values["count"],
                    "runtime_seconds": round(values["runtime_seconds"], 6),
                }
                for category, values in sorted(by_category.items())
            },
            "slowest_events": [
                event.to_dict()
                for event in sorted(self.events, key=lambda item: item.runtime_seconds, reverse=True)[:20]
            ],
        }
