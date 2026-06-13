"""Performance counters for optional factor acceleration paths."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccelerationStats:
    bulk_matrix_enabled: bool = False
    parallel_enabled: bool = False
    workers: int = 1
    bulk_read_seconds: float | None = None
    matrix_build_seconds: float | None = None
    eval_seconds: float | None = None
    factor_batches: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    speedup_vs_baseline: float | None = None

    def to_dict(self) -> dict:
        return {
            "bulk_matrix_enabled": self.bulk_matrix_enabled,
            "parallel_enabled": self.parallel_enabled,
            "workers": self.workers,
            "bulk_read_seconds": None if self.bulk_read_seconds is None else round(self.bulk_read_seconds, 6),
            "matrix_build_seconds": None if self.matrix_build_seconds is None else round(self.matrix_build_seconds, 6),
            "eval_seconds": None if self.eval_seconds is None else round(self.eval_seconds, 6),
            "factor_batches": self.factor_batches,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "speedup_vs_baseline": self.speedup_vs_baseline,
        }
