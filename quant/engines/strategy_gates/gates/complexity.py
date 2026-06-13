"""Strategy complexity gate spec."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_specs import GateSpec


GATE_SPECS = (
    GateSpec("complexity", "ROBUSTNESS", "Check strategy complexity and parameter count.", "_complexity_gate", 70),
)
