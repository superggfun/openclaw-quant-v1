"""Shared factor pipeline application helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

import pandas as pd

from quant.engines.factor_pipeline.factor_pipeline import FactorPipeline


ObservationT = TypeVar("ObservationT")


def apply_factor_pipeline(
    observations: list[ObservationT],
    factor: str,
    pipeline_config: dict | None,
    report_dir: str | Path,
    rebuild_observation: Callable[[Any, float], ObservationT],
    sort_key: Callable[[ObservationT], tuple],
) -> tuple[list[ObservationT], list[str]]:
    if pipeline_config is None or not observations:
        return observations, []

    frame = pd.DataFrame([_observation_row(observation) for observation in observations])
    pipeline = FactorPipeline(pipeline_config, report_dir=report_dir)
    processed: list[ObservationT] = []
    warnings = []

    for signal_date, group in frame.groupby("signal_date"):
        raw_values = {
            str(row.symbol): float(row.factor_value)
            for row in group.itertuples(index=False)
        }
        pipeline_result = pipeline.run(
            raw_values,
            factor=factor,
            as_of_date=str(signal_date),
            write_report=False,
        )
        warnings.extend(pipeline_result.warnings)
        for row in group.itertuples(index=False):
            cleaned_value = pipeline_result.cleaned_factor_values.get(str(row.symbol))
            if cleaned_value is None:
                continue
            processed.append(rebuild_observation(row, float(cleaned_value)))

    processed.sort(key=sort_key)
    return processed, sorted(set(warnings))


def _observation_row(observation: Any) -> dict[str, Any]:
    return {
        name: getattr(observation, name)
        for name in getattr(observation, "__dataclass_fields__", ())
    }
