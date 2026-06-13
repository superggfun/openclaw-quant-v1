"""Models for deterministic Strategy Evaluation Gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"
REJECTED = "REJECTED"
SKIPPED = "SKIPPED"

FINAL_STATUS_ORDER = {PASS: 0, SKIPPED: 1, WARNING: 2, FAIL: 3, REJECTED: 4}
VALID_GATE_STATUSES = set(FINAL_STATUS_ORDER)


@dataclass(frozen=True)
class GateConfig:
    """Thresholds used by Strategy Evaluation Gates.

    These thresholds are diagnostics for offline research. They do not submit
    orders, disable strategies, or mutate account state.
    """

    minimum_price_coverage: float = 0.80
    minimum_fundamental_coverage: float = 0.30
    stale_data_days: int = 7
    minimum_ic: float = 0.02
    minimum_rank_ic: float = 0.02
    minimum_icir: float = 0.0
    minimum_factor_coverage: float = 0.30
    minimum_factor_history_count: int = 3
    minimum_walk_forward_folds: int = 3
    minimum_test_sharpe: float = 0.20
    maximum_train_test_gap: float = 0.50
    maximum_drawdown: float = 0.25
    maximum_turnover: float = 5.0
    maximum_cost_drag: float = 0.05
    minimum_regime_sample: int = 30
    maximum_factor_count: int = 8
    maximum_parameter_count: int = 20
    reject_on_schema_error: bool = True

    @classmethod
    def from_mapping(cls, values: dict[str, Any] | None) -> "GateConfig":
        data = dict(values or {})
        allowed = cls.__dataclass_fields__
        coerced = {}
        for key, value in data.items():
            if key not in allowed:
                continue
            default = allowed[key].default
            if isinstance(default, bool):
                coerced[key] = bool(value)
            elif isinstance(default, int):
                coerced[key] = int(value)
            elif isinstance(default, float):
                coerced[key] = float(value)
            else:
                coerced[key] = value
        return cls(**coerced)

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_price_coverage": self.minimum_price_coverage,
            "minimum_fundamental_coverage": self.minimum_fundamental_coverage,
            "stale_data_days": self.stale_data_days,
            "minimum_ic": self.minimum_ic,
            "minimum_rank_ic": self.minimum_rank_ic,
            "minimum_icir": self.minimum_icir,
            "minimum_factor_coverage": self.minimum_factor_coverage,
            "minimum_factor_history_count": self.minimum_factor_history_count,
            "minimum_walk_forward_folds": self.minimum_walk_forward_folds,
            "minimum_test_sharpe": self.minimum_test_sharpe,
            "maximum_train_test_gap": self.maximum_train_test_gap,
            "maximum_drawdown": self.maximum_drawdown,
            "maximum_turnover": self.maximum_turnover,
            "maximum_cost_drag": self.maximum_cost_drag,
            "minimum_regime_sample": self.minimum_regime_sample,
            "maximum_factor_count": self.maximum_factor_count,
            "maximum_parameter_count": self.maximum_parameter_count,
            "reject_on_schema_error": self.reject_on_schema_error,
        }


@dataclass(frozen=True)
class GateResult:
    gate_name: str
    category: str
    status: str
    reason_code: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "category": self.category,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "evidence": dict(self.evidence),
            "warnings": list(self.warnings),
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class StrategyGateReport:
    strategy_name: str
    strategy_version: str
    overall_status: str
    gate_results: list[GateResult]
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "overall_status": self.overall_status,
            "gate_results": [result.to_dict() for result in self.gate_results],
            "report_path": self.report_path,
        }


def final_status(statuses: list[str]) -> str:
    if not statuses:
        return WARNING
    return max(statuses, key=lambda status: FINAL_STATUS_ORDER.get(status, 0))
