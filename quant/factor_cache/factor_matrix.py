"""Bulk factor matrix result container."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FactorMatrixResult:
    """A no-lookahead factor/future-return matrix for one evaluation key."""

    factor_name: str
    universe: list[str]
    start: str | None
    end: str | None
    forward_days: int
    observations: list[Any]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    warnings: list[str]
    matrix_build_seconds: float
    bulk_read_seconds: float | None = None

    @property
    def matrix_rows(self) -> int:
        return len(self.observations)

    def rows(self) -> list[dict[str, Any]]:
        output = []
        for observation in self.observations:
            if hasattr(observation, "__dataclass_fields__"):
                row = asdict(observation)
            elif isinstance(observation, dict):
                row = dict(observation)
            else:
                row = dict(observation)
            row["valid"] = True
            row["factor_name"] = self.factor_name
            output.append(row)
        return output

    def to_metadata(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name,
            "universe_size": len(self.universe),
            "start": self.start,
            "end": self.end,
            "forward_days": self.forward_days,
            "matrix_rows": self.matrix_rows,
            "matrix_build_seconds": round(self.matrix_build_seconds, 6),
            "bulk_read_seconds": None if self.bulk_read_seconds is None else round(self.bulk_read_seconds, 6),
            "excluded_symbol_count": len(self.excluded_symbols),
        }
