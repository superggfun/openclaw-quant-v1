"""Declarative Strategy Gate specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateDefinition:
    name: str
    category: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "category": self.category, "description": self.description}


@dataclass(frozen=True)
class GateSpec:
    name: str
    category: str
    description: str
    handler_name: str
    order: int

    def to_definition(self) -> GateDefinition:
        return GateDefinition(self.name, self.category, self.description)


@dataclass(frozen=True)
class GateRunInput:
    validation: dict[str, Any]
    symbols: list[str]
    definition: Any
    config: Any
    strategy_run_report: dict[str, Any] | None
    write_report: bool
