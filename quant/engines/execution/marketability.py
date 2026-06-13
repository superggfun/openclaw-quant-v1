"""Marketability diagnostics for proposed simulated trades."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketabilityCheck:
    symbol: str
    side: str
    requested_quantity: int
    price: float | None
    notional: float
    average_daily_volume: float | None
    adv_participation: float | None
    marketable: bool
    reason: str
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "requested_quantity": self.requested_quantity,
            "price": self.price,
            "notional": self.notional,
            "average_daily_volume": self.average_daily_volume,
            "adv_participation": self.adv_participation,
            "marketable": self.marketable,
            "reason": self.reason,
            "warnings": self.warnings,
        }
