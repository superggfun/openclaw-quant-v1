"""Data quality gate spec."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_specs import GateSpec


GATE_SPECS = (
    GateSpec("data_quality", "DATA", "Check price and fundamental data coverage before research use.", "_data_quality_gate", 20),
)
