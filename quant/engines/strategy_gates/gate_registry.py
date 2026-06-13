"""Registry metadata for Strategy Evaluation Gates."""

from __future__ import annotations

from quant.engines.strategy_gates.gate_discovery import discover_gate_specs
from quant.engines.strategy_gates.gate_specs import GateDefinition, GateSpec


DEFAULT_GATES = tuple(spec.to_definition() for spec in discover_gate_specs())


class GateRegistry:
    """Return deterministic gate metadata for reports and docs."""

    def __init__(self, specs: tuple[GateSpec, ...] | None = None) -> None:
        self._specs = tuple(specs or discover_gate_specs())

    def specs(self) -> list[GateSpec]:
        return list(self._specs)

    def list_gates(self) -> list[dict[str, str]]:
        return [spec.to_definition().to_dict() for spec in self._specs]

    def names(self) -> list[str]:
        return [spec.name for spec in self._specs]
