"""Regime data structures."""

from __future__ import annotations

from dataclasses import dataclass


REGIME_TYPES = {
    "BULL",
    "BEAR",
    "HIGH_VOL",
    "LOW_VOL",
    "TRENDING",
    "RANGE_BOUND",
    "CRISIS",
    "RECOVERY",
    "UNKNOWN",
}


class MarketRegime:
    BULL = "BULL"
    BEAR = "BEAR"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"
    TRENDING = "TRENDING"
    RANGE_BOUND = "RANGE_BOUND"
    CRISIS = "CRISIS"
    RECOVERY = "RECOVERY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeObservation:
    date: str
    regime: str
    volatility: float | None
    trend_strength: float | None
    drawdown: float | None
    market_return: float | None
    confidence: float

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "regime": self.regime,
            "volatility": self.volatility,
            "trend_strength": self.trend_strength,
            "drawdown": self.drawdown,
            "market_return": self.market_return,
            "confidence": self.confidence,
        }
