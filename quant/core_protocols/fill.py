"""Fill protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from quant.core_protocols.order import ORDER_SIDES


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    cost: float
    fill_time: str
    signal_date: str
    execution_date: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fill":
        return cls(
            fill_id=str(data["fill_id"]),
            order_id=str(data["order_id"]),
            symbol=str(data["symbol"]).upper(),
            side=str(data["side"]).upper(),
            quantity=float(data["quantity"]),
            price=float(data["price"]),
            cost=float(data.get("cost", 0.0)),
            fill_time=str(data.get("fill_time", "")),
            signal_date=str(data.get("signal_date", "")),
            execution_date=str(data.get("execution_date", "")),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.fill_id:
            errors.append("fill_id is required")
        if not self.order_id:
            errors.append("fill order_id is required")
        if self.side not in ORDER_SIDES:
            errors.append("fill side must be BUY or SELL")
        if self.quantity <= 0:
            errors.append("fill quantity must be positive")
        if self.price <= 0:
            errors.append("fill price must be positive")
        if self.cost < 0:
            errors.append("fill cost must be non-negative")
        if self.signal_date and self.execution_date and self.signal_date > self.execution_date:
            errors.append("fill signal_date must be on or before execution_date")
        return errors
