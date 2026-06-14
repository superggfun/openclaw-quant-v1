"""Optional semantic-preserving factor acceleration helpers."""

from quant.factor_acceleration.acceleration_stats import AccelerationStats
from quant.factor_acceleration.bulk_price_loader import BulkPriceLoader, BulkPriceLoadResult
from quant.factor_acceleration.factor_matrix_builder import FactorMatrixBuilder, preload_price_cache, release_price_cache
from quant.factor_acceleration.in_memory_provider import InMemoryPriceMatrixProvider
from quant.factor_acceleration.observation_matrix import ObservationMatrixResult, ObservationMatrixRow
from quant.factor_acceleration.parallel_runner import FactorBatchResult, FactorBatchTask, run_factor_batch_tasks

__all__ = [
    "AccelerationStats",
    "BulkPriceLoadResult",
    "BulkPriceLoader",
    "FactorBatchResult",
    "FactorBatchTask",
    "FactorMatrixBuilder",
    "InMemoryPriceMatrixProvider",
    "ObservationMatrixResult",
    "ObservationMatrixRow",
    "preload_price_cache",
    "release_price_cache",
    "run_factor_batch_tasks",
]
