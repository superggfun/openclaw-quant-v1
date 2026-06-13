"""Auto-discovered agent export registry."""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from quant.reports.agent_export import exporters as exporter_package
from quant.reports.agent_export.specs import ExportSpec


def discover_export_modules(package: ModuleType = exporter_package) -> list[ModuleType]:
    modules = []
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return modules
    prefix = f"{package.__name__}."
    for module_info in pkgutil.iter_modules(package_path, prefix):
        module_name = module_info.name.rsplit(".", 1)[-1]
        if module_info.ispkg or module_name.startswith("_"):
            continue
        module = importlib.import_module(module_info.name)
        if getattr(module, "EXPORT_SPECS", None):
            modules.append(module)
    return sorted(modules, key=lambda module: module.__name__)


def discover_export_specs(modules: list[ModuleType] | None = None) -> tuple[ExportSpec, ...]:
    specs = []
    seen: set[tuple[str, int]] = set()
    for module in modules or discover_export_modules():
        for spec in getattr(module, "EXPORT_SPECS", ()):
            if not isinstance(spec, ExportSpec):
                raise TypeError(f"{module.__name__}.EXPORT_SPECS contains non-ExportSpec value: {spec!r}")
            key = (spec.report_type, spec.priority)
            if key in seen:
                raise ValueError(f"duplicate agent export spec priority: {spec.report_type} at {spec.priority}")
            seen.add(key)
            specs.append(spec)
    return tuple(sorted(specs, key=lambda spec: (spec.priority, spec.report_type)))


EXPORT_SPECS = discover_export_specs()
SUPPORTED_REPORT_TYPES = frozenset(spec.report_type for spec in EXPORT_SPECS)
