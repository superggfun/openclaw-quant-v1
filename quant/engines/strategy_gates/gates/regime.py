"""Regime coverage gate spec."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_specs import GateSpec


GATE_SPECS = (
    GateSpec("regime_coverage", "REGIME", "Check regime sample support for regime-aware diagnostics.", "_regime_gate", 50),
)
