"""Signal protocol object."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Signal:
    signal_id: str
    symbol: str
    score: float
    signal_date: str
    source: str
    confidence: float
    factor_breakdown: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Signal":
        return cls(
            signal_id=str(data["signal_id"]),
            symbol=str(data["symbol"]).upper(),
            score=float(data["score"]),
            signal_date=str(data["signal_date"]),
            source=str(data.get("source", "")),
            confidence=float(data.get("confidence", 0.0)),
            factor_breakdown={str(key): float(value) for key, value in (data.get("factor_breakdown") or {}).items()},
            metadata=dict(data.get("metadata") or {}),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.signal_id:
            errors.append("signal_id is required")
        if not self.symbol:
            errors.append("signal symbol is required")
        if not self.signal_date:
            errors.append("signal_date is required")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("signal confidence must be between 0 and 1")
        return errors
