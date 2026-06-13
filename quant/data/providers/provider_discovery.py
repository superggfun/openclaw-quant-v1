"""Auto-discovery for data provider specs."""

from __future__ import annotations

import pkgutil
from pathlib import Path

from quant.data.providers.provider_specs import ProviderSpec


_SKIP_MODULES = {"base", "provider_discovery", "provider_registry", "provider_specs"}


def discover_provider_specs(
    package_prefix: str = "quant.data.providers.",
    package_path: Path | None = None,
) -> tuple[ProviderSpec, ...]:
    root = package_path or Path(__file__).resolve().parent
    specs: list[ProviderSpec] = []
    seen: set[str] = set()

    for module_info in pkgutil.iter_modules([str(root)]):
        if module_info.name in _SKIP_MODULES:
            continue
        module = __import__(f"{package_prefix}{module_info.name}", fromlist=["*"])
        module_specs = getattr(module, "PROVIDER_SPECS", ())
        for spec in module_specs:
            if not isinstance(spec, ProviderSpec):
                raise TypeError(f"{module.__name__}.PROVIDER_SPECS must contain ProviderSpec objects")
            key = spec.name.lower().strip()
            if key in seen:
                raise ValueError(f"duplicate data provider spec registered: {spec.name}")
            seen.add(key)
            specs.append(spec)

    return tuple(sorted(specs, key=lambda spec: spec.name))
