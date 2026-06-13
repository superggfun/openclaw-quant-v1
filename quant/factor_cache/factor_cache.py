"""Generic in-memory cache storage for factor matrices."""

from __future__ import annotations

from collections.abc import Callable

from quant.factor_cache.cache_keys import FactorCacheKey
from quant.factor_cache.cache_stats import CacheStats
from quant.factor_cache.factor_matrix import FactorMatrixResult


class FactorCache:
    """Process-local matrix cache.

    The cache is intentionally in-memory for v0.41. Persistence can be added
    later only after invalidation and no-lookahead semantics are proven.
    """

    def __init__(self) -> None:
        self._matrices: dict[FactorCacheKey, FactorMatrixResult] = {}
        self.stats = CacheStats()

    def get_or_build(
        self,
        key: FactorCacheKey,
        builder: Callable[[], FactorMatrixResult],
    ) -> tuple[FactorMatrixResult, bool]:
        cached = self._matrices.get(key)
        if cached is not None:
            self.stats.matrix_hits += 1
            self.stats.factor_value_hits += cached.matrix_rows
            self.stats.future_return_hits += cached.matrix_rows
            self._refresh_memory_estimate()
            return cached, True

        result = builder()
        self._matrices[key] = result
        self.stats.matrix_misses += 1
        self.stats.factor_value_misses += result.matrix_rows
        self.stats.future_return_misses += result.matrix_rows
        self._refresh_memory_estimate()
        return result, False

    def clear(self) -> None:
        if self._matrices:
            self.stats.invalidations += len(self._matrices)
        self._matrices.clear()
        self._refresh_memory_estimate()

    def snapshot(self) -> dict:
        return self.stats.to_dict() | {"cached_matrices": len(self._matrices)}

    def _refresh_memory_estimate(self) -> None:
        # Conservative rough estimate used only for diagnostics.
        self.stats.cache_memory_estimate = sum(matrix.matrix_rows * 160 for matrix in self._matrices.values())
