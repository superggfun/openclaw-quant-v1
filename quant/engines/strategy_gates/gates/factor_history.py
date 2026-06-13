"""Factor history gate spec."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_specs import GateSpec


GATE_SPECS = (
    GateSpec(
        "factor_history",
        "FACTORS",
        "Check persisted factor IC, RankIC, ICIR, coverage, and history depth.",
        "_factor_history_gate",
        30,
    ),
)
