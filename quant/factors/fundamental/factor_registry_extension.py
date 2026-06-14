"""Compatibility helpers for accounting-based fundamental factors.

.. note::
    This is a lightweight compatibility shim for legacy consumers that
    expect a simplified factor view.  New code should use the canonical
    ``FactorDefinition`` from ``quant.factors.specs`` directly, which
    preserves ``higher_is_better``, ``direction``, and other metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from quant.factors.registry import discover_factor_specs

FundamentalMetricFunction = Callable[[dict], float | None]


@dataclass(frozen=True)
class FundamentalFactorSpec:
    """Lightweight factor view for backward compatibility.

    Attributes are derived from the canonical ``FactorDefinition``.
    For full metadata (direction, normalization, family, source,
    lookahead), use ``discover_factor_specs()`` directly.
    """

    name: str
    category: str
    description: str
    metrics_used: tuple[str, ...]
    compute: FundamentalMetricFunction
    higher_is_better: bool = True


def fundamental_factor_definitions() -> list[FundamentalFactorSpec]:
    return [
        FundamentalFactorSpec(
            name=definition.name,
            category=definition.category,
            description=definition.description,
            metrics_used=tuple(definition.fundamental_metrics_used or []),
            compute=definition.compute,
            higher_is_better=definition.higher_is_better,
        )
        for definition in discover_factor_specs().values()
        if definition.data_source == "fundamental"
    ]