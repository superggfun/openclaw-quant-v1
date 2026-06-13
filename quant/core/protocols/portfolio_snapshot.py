"""Portfolio snapshot protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from quant.core.protocols.position import Position


@dataclass(frozen=True)
class PortfolioSnapshot:
    date: str
    cash: float
    equity: float
    positions: list[Position] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    drawdown: float | None = None
    cost_paid: float = 0.0
    trade_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["positions"] = [position.to_dict() for position in self.positions]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortfolioSnapshot":
        return cls(
            date=str(data["date"]),
            cash=float(data.get("cash", 0.0)),
            equity=float(data.get("equity", 0.0)),
            positions=[Position.from_dict(position) for position in data.get("positions", [])],
            weights={str(key): float(value) for key, value in (data.get("weights") or {}).items()},
            drawdown=None if data.get("drawdown") is None else float(data["drawdown"]),
            cost_paid=float(data.get("cost_paid", 0.0)),
            trade_count=int(data.get("trade_count", 0)),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.cash < -1e-9:
            errors.append("snapshot cash must be non-negative")
        if self.equity < -1e-9:
            errors.append("snapshot equity must be non-negative")
        if self.cost_paid < 0:
            errors.append("snapshot cost_paid must be non-negative")
        errors.extend(error for position in self.positions for error in position.validate())
        weight_sum = sum(self.weights.values())
        if self.weights and not 0.0 <= weight_sum <= 1.5:
            errors.append("snapshot weights sum is outside expected bounds")
        return errors
