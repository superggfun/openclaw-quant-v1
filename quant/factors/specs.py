"""Factor definition types and spec helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


FactorFunction = Callable[[Any], float | None]


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    category: str
    description: str
    required_inputs: list[str]
    lookback_days: int
    forward_return_horizon: int
    factor_type: str
    higher_is_better: bool
    no_lookahead: bool
    compute: FactorFunction
    data_source: str = "price"
    fundamental_data_required: bool = False
    fundamental_statement: str | None = None
    fundamental_metrics_used: list[str] | None = None


def price_factor_spec(
    name: str,
    category: str,
    description: str,
    lookback_days: int,
    factor_type: str,
    compute: FactorFunction,
    *,
    higher_is_better: bool = True,
    required_inputs: list[str] | None = None,
    forward_return_horizon: int | None = None,
) -> FactorDefinition:
    return FactorDefinition(
        name=name,
        category=category,
        description=description,
        required_inputs=required_inputs or ["close"],
        lookback_days=lookback_days,
        forward_return_horizon=forward_return_horizon if forward_return_horizon is not None else lookback_days,
        factor_type=factor_type,
        higher_is_better=higher_is_better,
        no_lookahead=True,
        compute=compute,
    )


def fundamental_factor_spec(
    name: str,
    category: str,
    description: str,
    metrics_used: list[str],
    compute: FactorFunction,
    *,
    higher_is_better: bool = True,
    statement: str = "fundamental_metrics",
) -> FactorDefinition:
    return FactorDefinition(
        name=name,
        category=category,
        description=description,
        required_inputs=[f"{statement}.report_date"] + [f"{statement}.{field}" for field in metrics_used],
        lookback_days=0,
        forward_return_horizon=0,
        factor_type="fundamental_accounting",
        higher_is_better=higher_is_better,
        no_lookahead=True,
        compute=compute,
        data_source="fundamental",
        fundamental_data_required=True,
        fundamental_statement=statement,
        fundamental_metrics_used=metrics_used,
    )
