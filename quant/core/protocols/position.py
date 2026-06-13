"""Position protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Position:
    symbol: str
    shares: float
    average_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    weight: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Position":
        return cls(
            symbol=str(data["symbol"]).upper(),
            shares=float(data["shares"]),
            average_cost=float(data.get("average_cost", 0.0)),
            market_price=float(data.get("market_price", 0.0)),
            market_value=float(data.get("market_value", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            weight=float(data.get("weight", 0.0)),
            timestamp=str(data.get("timestamp", "")),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.symbol:
            errors.append("position symbol is required")
        if self.shares < 0:
            errors.append("position shares must be non-negative")
        if self.average_cost < 0:
            errors.append("position average_cost must be non-negative")
        if self.market_price < 0:
            errors.append("position market_price must be non-negative")
        if self.market_value < -1e-9:
            errors.append("position market_value must be non-negative")
        if abs(self.weight) > 1.5:
            errors.append("position weight is outside expected account bounds")
        return errors
