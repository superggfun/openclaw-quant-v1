"""Compatibility helpers for accounting-based fundamental factors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from quant.factors.registry import discover_factor_specs

FundamentalMetricFunction = Callable[[dict], float | None]


@dataclass(frozen=True)
class FundamentalFactorSpec:
    name: str
    category: str
    description: str
    metrics_used: list[str]
    compute: FundamentalMetricFunction


def fundamental_factor_definitions() -> list[FundamentalFactorSpec]:
    return [
        FundamentalFactorSpec(
            name=definition.name,
            category=definition.category,
            description=definition.description,
            metrics_used=definition.fundamental_metrics_used or [],
            compute=definition.compute,
        )
        for definition in discover_factor_specs().values()
        if definition.data_source == "fundamental"
    ]
