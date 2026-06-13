"""Optional semantic-preserving factor acceleration helpers."""

from quant.factor_acceleration.acceleration_stats import AccelerationStats
from quant.factor_acceleration.bulk_price_loader import BulkPriceLoader, BulkPriceLoadResult
from quant.factor_acceleration.factor_matrix_builder import FactorMatrixBuilder
from quant.factor_acceleration.observation_matrix import ObservationMatrixResult, ObservationMatrixRow
from quant.factor_acceleration.parallel_runner import FactorBatchResult, FactorBatchTask, run_factor_batch_tasks

__all__ = [
    "AccelerationStats",
    "BulkPriceLoadResult",
    "BulkPriceLoader",
    "FactorBatchResult",
    "FactorBatchTask",
    "FactorMatrixBuilder",
    "ObservationMatrixResult",
    "ObservationMatrixRow",
    "run_factor_batch_tasks",
]
