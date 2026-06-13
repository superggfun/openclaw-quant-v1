"""Order protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ORDER_STATUSES = {
    "PENDING",
    "SUBMITTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
}
ORDER_SIDES = {"BUY", "SELL"}


@dataclass(frozen=True)
class Order:
    order_id: str
    symbol: str
    side: str
    quantity: float
    target_weight: float | None
    signal_date: str
    created_at: str
    status: str = "PENDING"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Order":
        return cls(
            order_id=str(data["order_id"]),
            symbol=str(data["symbol"]).upper(),
            side=str(data["side"]).upper(),
            quantity=float(data["quantity"]),
            target_weight=None if data.get("target_weight") is None else float(data["target_weight"]),
            signal_date=str(data.get("signal_date", "")),
            created_at=str(data.get("created_at", "")),
            status=str(data.get("status", "PENDING")).upper(),
            reason=str(data.get("reason", "")),
            metadata=dict(data.get("metadata") or {}),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.order_id:
            errors.append("order_id is required")
        if not self.symbol:
            errors.append("order symbol is required")
        if self.side not in ORDER_SIDES:
            errors.append("order side must be BUY or SELL")
        if self.quantity <= 0:
            errors.append("order quantity must be positive")
        if self.target_weight is not None and not 0.0 <= self.target_weight <= 1.0:
            errors.append("order target_weight must be between 0 and 1")
        if self.status not in ORDER_STATUSES:
            errors.append("order status is invalid")
        return errors
