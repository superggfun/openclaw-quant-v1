"""Cache keys for no-lookahead factor evaluation matrices."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def make_universe_hash(symbols: list[str]) -> str:
    """Return a deterministic hash for a normalized symbol universe."""

    normalized = sorted({str(symbol).upper().strip() for symbol in symbols if str(symbol).strip()})
    payload = "|".join(normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class FactorCacheKey:
    """Uniquely identify one factor matrix build."""

    factor_name: str
    universe_hash: str
    start: str | None
    end: str | None
    forward_days: int
    factor_version: str
    data_newest_date: str | None
    no_lookahead: bool = True

    def to_dict(self) -> dict:
        return {
            "factor_name": self.factor_name,
            "universe_hash": self.universe_hash,
            "start": self.start,
            "end": self.end,
            "forward_days": self.forward_days,
            "factor_version": self.factor_version,
            "data_newest_date": self.data_newest_date,
            "no_lookahead": self.no_lookahead,
        }
