"""Walk-forward gate spec."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_specs import GateSpec


GATE_SPECS = (
    GateSpec(
        "walk_forward",
        "VALIDATION",
        "Check out-of-sample fold evidence and train/test gap diagnostics.",
        "_walk_forward_gate",
        40,
    ),
)
