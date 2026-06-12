"""Recommendation protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


RECOMMENDATION_ACTIONS = {"BUY", "SELL", "HOLD", "REDUCE", "INCREASE"}


@dataclass(frozen=True)
class Recommendation:
    symbol: str
    action: str
    target_weight: float
    confidence: float
    reason: str
    generated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recommendation":
        return cls(
            symbol=str(data["symbol"]).upper(),
            action=str(data["action"]).upper(),
            target_weight=float(data.get("target_weight", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", "")),
            generated_at=str(data.get("generated_at", "")),
            metadata=dict(data.get("metadata") or {}),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.symbol:
            errors.append("recommendation symbol is required")
        if self.action not in RECOMMENDATION_ACTIONS:
            errors.append("recommendation action is invalid")
        if not 0.0 <= self.target_weight <= 1.0:
            errors.append("recommendation target_weight must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("recommendation confidence must be between 0 and 1")
        return errors
