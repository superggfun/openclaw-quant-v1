"""No-lookahead factor observation matrix containers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ObservationMatrixRow:
    factor_name: str
    symbol: str
    signal_date: str
    future_date: str | None
    factor_value: float | None
    future_return: float | None
    forward_days: int
    valid: bool
    exclusion_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationMatrixResult:
    factor_name: str
    universe: list[str]
    start: str | None
    end: str | None
    forward_days: int
    rows: list[ObservationMatrixRow]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    warnings: list[str]
    bulk_read_seconds: float
    matrix_build_seconds: float
    performance_metadata: dict[str, Any] | None = None

    @property
    def valid_rows(self) -> list[ObservationMatrixRow]:
        return [row for row in self.rows if row.valid]

    @property
    def matrix_rows(self) -> int:
        return len(self.valid_rows)

    def to_metadata(self) -> dict[str, Any]:
        metadata = {
            "factor_name": self.factor_name,
            "universe_size": len(self.universe),
            "start": self.start,
            "end": self.end,
            "forward_days": self.forward_days,
            "matrix_rows": self.matrix_rows,
            "bulk_read_seconds": round(self.bulk_read_seconds, 6),
            "matrix_build_seconds": round(self.matrix_build_seconds, 6),
            "excluded_symbol_count": len(self.excluded_symbols),
            "no_lookahead": True,
        }
        if self.performance_metadata:
            metadata.update(self.performance_metadata)
        return metadata
