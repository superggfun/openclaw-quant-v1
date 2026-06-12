"""Account protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from quant.core_protocols.fill import Fill
from quant.core_protocols.order import Order
from quant.core_protocols.position import Position


@dataclass(frozen=True)
class AccountState:
    account_id: str
    cash: float
    equity: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float
    cost_paid: float
    timestamp: str
    positions: list[Position] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["positions"] = [position.to_dict() for position in self.positions]
        payload["orders"] = [order.to_dict() for order in self.orders]
        payload["fills"] = [fill.to_dict() for fill in self.fills]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountState":
        return cls(
            account_id=str(data["account_id"]),
            cash=float(data.get("cash", 0.0)),
            equity=float(data.get("equity", 0.0)),
            market_value=float(data.get("market_value", 0.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            cost_paid=float(data.get("cost_paid", 0.0)),
            timestamp=str(data.get("timestamp", "")),
            positions=[Position.from_dict(position) for position in data.get("positions", [])],
            orders=[Order.from_dict(order) for order in data.get("orders", [])],
            fills=[Fill.from_dict(fill) for fill in data.get("fills", [])],
            metadata=dict(data.get("metadata") or {}),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.account_id:
            errors.append("account_id is required")
        if self.cash < -1e-9:
            errors.append("account cash must be non-negative")
        if self.equity < -1e-9:
            errors.append("account equity must be non-negative")
        if self.market_value < -1e-9:
            errors.append("account market_value must be non-negative")
        if self.cost_paid < 0:
            errors.append("account cost_paid must be non-negative")
        position_value = sum(position.market_value for position in self.positions)
        if abs((self.cash + position_value) - self.equity) > 0.02:
            errors.append("account reconciliation failed: cash + positions != equity")
        errors.extend(error for position in self.positions for error in position.validate())
        errors.extend(error for order in self.orders for error in order.validate())
        errors.extend(error for fill in self.fills for error in fill.validate())
        order_ids = {order.order_id for order in self.orders}
        for fill in self.fills:
            if order_ids and fill.order_id not in order_ids:
                errors.append(f"fill {fill.fill_id} references unknown order {fill.order_id}")
        return errors
