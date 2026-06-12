"""Dataclasses for versioned strategy DSL objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class StrategyDefinition:
    """Normalized strategy definition loaded from YAML or JSON."""

    name: str
    description: str
    version: str
    author: str
    created_at: str
    tags: list[str] = field(default_factory=list)
    universe: dict[str, Any] = field(default_factory=dict)
    factors: list[dict[str, Any]] = field(default_factory=list)
    regime: dict[str, Any] = field(default_factory=dict)
    portfolio: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "StrategyDefinition":
        data = dict(payload)
        return cls(
            name=str(data.get("name") or "").strip(),
            description=str(data.get("description") or "").strip(),
            version=str(data.get("version") or "").strip(),
            author=str(data.get("author") or "").strip(),
            created_at=str(data.get("created_at") or "").strip(),
            tags=_list(data.get("tags")),
            universe=_dict(data.get("universe")),
            factors=[_dict(item) for item in _list(data.get("factors"))],
            regime=_dict(data.get("regime")),
            portfolio=_dict(data.get("portfolio")),
            risk=_dict(data.get("risk")),
            execution=_dict(data.get("execution")),
            validation=_dict(data.get("validation")),
            metadata=_dict(data.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "created_at": self.created_at,
            "tags": list(self.tags),
            "universe": dict(self.universe),
            "factors": [dict(item) for item in self.factors],
            "regime": dict(self.regime),
            "portfolio": dict(self.portfolio),
            "risk": dict(self.risk),
            "execution": dict(self.execution),
            "validation": dict(self.validation),
            "metadata": dict(self.metadata),
        }

    @property
    def factor_weights(self) -> dict[str, float]:
        weights = {}
        for item in self.factors:
            name = str(item.get("name") or "").strip().lower()
            if not name:
                continue
            weights[name] = float(item.get("weight", 1.0))
        return weights

    @property
    def symbols(self) -> list[str]:
        return [str(symbol).upper().strip() for symbol in _list(self.universe.get("symbols")) if str(symbol).strip()]

    @property
    def portfolio_method(self) -> str:
        return str(self.portfolio.get("method") or "equal_weight").strip().lower()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]
