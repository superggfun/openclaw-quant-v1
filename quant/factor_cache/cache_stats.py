"""Runtime counters for the factor evaluation cache."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CacheStats:
    """Lightweight cache counters; all values are JSON-safe."""

    factor_value_hits: int = 0
    factor_value_misses: int = 0
    future_return_hits: int = 0
    future_return_misses: int = 0
    matrix_hits: int = 0
    matrix_misses: int = 0
    invalidations: int = 0
    cache_memory_estimate: int = 0

    def merge(self, other: "CacheStats") -> None:
        self.factor_value_hits += other.factor_value_hits
        self.factor_value_misses += other.factor_value_misses
        self.future_return_hits += other.future_return_hits
        self.future_return_misses += other.future_return_misses
        self.matrix_hits += other.matrix_hits
        self.matrix_misses += other.matrix_misses
        self.invalidations += other.invalidations
        self.cache_memory_estimate = max(self.cache_memory_estimate, other.cache_memory_estimate)

    def to_dict(self) -> dict[str, int]:
        return {
            "factor_value_hits": self.factor_value_hits,
            "factor_value_misses": self.factor_value_misses,
            "future_return_hits": self.future_return_hits,
            "future_return_misses": self.future_return_misses,
            "matrix_hits": self.matrix_hits,
            "matrix_misses": self.matrix_misses,
            "cache_memory_estimate": self.cache_memory_estimate,
            "invalidations": self.invalidations,
        }
