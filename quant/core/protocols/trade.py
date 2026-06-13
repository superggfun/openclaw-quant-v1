"""Executed trade protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from quant.core.protocols.order import ORDER_SIDES


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    side: str
    quantity: float
    price: float
    cost: float
    signal_date: str
    execution_date: str
    strategy: str
    portfolio_method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradeRecord":
        return cls(
            symbol=str(data["symbol"]).upper(),
            side=str(data["side"]).upper(),
            quantity=float(data.get("quantity", data.get("shares", 0.0))),
            price=float(data["price"]),
            cost=float(data.get("cost", data.get("total_cost", 0.0))),
            signal_date=str(data.get("signal_date", "")),
            execution_date=str(data.get("execution_date", "")),
            strategy=str(data.get("strategy", "")),
            portfolio_method=str(data.get("portfolio_method", "")),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.symbol:
            errors.append("trade symbol is required")
        if self.side not in ORDER_SIDES:
            errors.append("trade side must be BUY or SELL")
        if self.quantity <= 0:
            errors.append("trade quantity must be positive")
        if self.price <= 0:
            errors.append("trade price must be positive")
        if self.cost < 0:
            errors.append("trade cost must be non-negative")
        if self.signal_date and self.execution_date and self.signal_date > self.execution_date:
            errors.append("trade signal_date must be on or before execution_date")
        return errors
