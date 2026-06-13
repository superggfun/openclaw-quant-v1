"""Auto-discovery for Strategy Gate specs."""

from __future__ import annotations

import importlib
import pkgutil

from quant.engines.strategy_gates.gate_specs import GateSpec


def discover_gate_specs(package_name: str = "quant.engines.strategy_gates.gates") -> tuple[GateSpec, ...]:
    package = importlib.import_module(package_name)
    specs: list[GateSpec] = []
    seen: set[str] = set()

    for module_info in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
        module = importlib.import_module(module_info.name)
        module_specs = getattr(module, "GATE_SPECS", ())
        for spec in module_specs:
            if not isinstance(spec, GateSpec):
                raise TypeError(f"{module_info.name}.GATE_SPECS must contain GateSpec objects")
            if spec.name in seen:
                raise ValueError(f"duplicate Strategy Gate spec registered: {spec.name}")
            seen.add(spec.name)
            specs.append(spec)

    return tuple(sorted(specs, key=lambda spec: (spec.order, spec.name)))
