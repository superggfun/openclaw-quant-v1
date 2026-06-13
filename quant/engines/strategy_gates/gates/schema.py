"""Strategy schema gate spec."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_specs import GateSpec


GATE_SPECS = (
    GateSpec(
        "schema_validation",
        "DSL",
        "Validate Strategy DSL schema, factors, and no-lookahead guardrails.",
        "_schema_gate",
        10,
    ),
)
