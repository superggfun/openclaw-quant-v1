"""Helpers for compatibility aliases during package layout migrations."""

from __future__ import annotations

from importlib import import_module
import sys


def alias_modules(package_name: str, mapping: dict[str, str]) -> None:
    """Expose existing modules under a new package path.

    This keeps v0.34 structural refactors low-risk: new layered imports work,
    while old public imports remain untouched for at least one release.
    """
    for alias, target in mapping.items():
        sys.modules[f"{package_name}.{alias}"] = import_module(target)

