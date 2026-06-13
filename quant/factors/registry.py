"""Auto-discovered factor definition registry."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from quant.factors.specs import FactorDefinition


SKIPPED_FACTOR_MODULES = {"factor_registry", "factor_registry_extension"}
FACTOR_PACKAGES = (
    ("quant.factors.price.", Path(__file__).resolve().parent / "price"),
    ("quant.factors.fundamental.", Path(__file__).resolve().parent / "fundamental"),
)


def discover_factor_modules(packages: tuple[tuple[str, Path], ...] = FACTOR_PACKAGES) -> list:
    modules = []
    for prefix, package_path in packages:
        if not package_path.exists():
            continue
        for module_info in pkgutil.iter_modules([str(package_path)], prefix):
            module_name = module_info.name.rsplit(".", 1)[-1]
            if module_info.ispkg or module_name.startswith("_") or module_name in SKIPPED_FACTOR_MODULES:
                continue
            module = importlib.import_module(module_info.name)
            if getattr(module, "FACTOR_SPECS", None):
                modules.append(module)
    return sorted(modules, key=lambda module: module.__name__)


def discover_factor_specs(modules: list[ModuleType] | None = None) -> dict[str, FactorDefinition]:
    definitions: dict[str, FactorDefinition] = {}
    for module in modules or discover_factor_modules():
        for spec in getattr(module, "FACTOR_SPECS", ()):
            if not isinstance(spec, FactorDefinition):
                raise TypeError(f"{module.__name__}.FACTOR_SPECS contains non-FactorDefinition value: {spec!r}")
            if spec.name in definitions:
                raise ValueError(f"duplicate factor definition: {spec.name}")
            definitions[spec.name] = spec
    return dict(sorted(definitions.items()))


FACTOR_DEFINITIONS = discover_factor_specs()
