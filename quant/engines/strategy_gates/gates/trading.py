"""Trading simulation gate spec."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_specs import GateSpec


GATE_SPECS = (
    GateSpec(
        "trading_simulation",
        "SIMULATION",
        "Check offline trade simulation drawdown, turnover, and cost drag.",
        "_trading_simulation_gate",
        60,
    ),
)
