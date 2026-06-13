"""Auto-discovered visualization report registry."""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from quant.reports.visualization import extractors as extractor_package
from quant.reports.visualization.specs import ReportSpec


SKIPPED_SPEC_MODULES = {"common"}


def discover_spec_modules(package: ModuleType = extractor_package) -> list[ModuleType]:
    modules = []
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return modules
    prefix = f"{package.__name__}."
    for module_info in pkgutil.iter_modules(package_path, prefix):
        module_name = module_info.name.rsplit(".", 1)[-1]
        if module_info.ispkg or module_name.startswith("_") or module_name in SKIPPED_SPEC_MODULES:
            continue
        module = importlib.import_module(module_info.name)
        if getattr(module, "REPORT_SPECS", None):
            modules.append(module)
    return sorted(modules, key=lambda module: module.__name__)


def discover_report_specs(modules: list[ModuleType] | None = None) -> dict[str, ReportSpec]:
    specs: dict[str, ReportSpec] = {}
    for module in modules or discover_spec_modules():
        for spec in getattr(module, "REPORT_SPECS", ()):
            if not isinstance(spec, ReportSpec):
                raise TypeError(f"{module.__name__}.REPORT_SPECS contains non-ReportSpec value: {spec!r}")
            if spec.report_type in specs:
                raise ValueError(f"duplicate visualization report spec: {spec.report_type}")
            specs[spec.report_type] = spec
    return dict(sorted(specs.items()))


REPORT_SPECS = discover_report_specs()
SUPPORTED_REPORT_TYPES = frozenset(REPORT_SPECS)
EXPECTED_CHARTS_BY_REPORT_TYPE = {
    report_type: spec.expected_charts
    for report_type, spec in REPORT_SPECS.items()
}
