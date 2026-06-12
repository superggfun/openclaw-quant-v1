"""Registry metadata for Strategy Evaluation Gates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateDefinition:
    name: str
    category: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "category": self.category, "description": self.description}


DEFAULT_GATES = [
    GateDefinition("schema_validation", "DSL", "Validate Strategy DSL schema, factors, and no-lookahead guardrails."),
    GateDefinition("data_quality", "DATA", "Check price and fundamental data coverage before research use."),
    GateDefinition("factor_history", "FACTORS", "Check persisted factor IC, RankIC, ICIR, coverage, and history depth."),
    GateDefinition("walk_forward", "VALIDATION", "Check out-of-sample fold evidence and train/test gap diagnostics."),
    GateDefinition("regime_coverage", "REGIME", "Check regime sample support for regime-aware diagnostics."),
    GateDefinition("trading_simulation", "SIMULATION", "Check offline trade simulation drawdown, turnover, and cost drag."),
    GateDefinition("complexity", "ROBUSTNESS", "Check strategy complexity and parameter count."),
]


class GateRegistry:
    """Return deterministic gate metadata for reports and docs."""

    def list_gates(self) -> list[dict[str, str]]:
        return [gate.to_dict() for gate in DEFAULT_GATES]

    def names(self) -> list[str]:
        return [gate.name for gate in DEFAULT_GATES]
