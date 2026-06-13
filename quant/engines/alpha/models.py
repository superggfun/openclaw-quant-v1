"""Dataclass models for alpha engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AlphaFactorRow:
    symbol: str
    as_of_date: str | None
    data_start_date: str | None
    data_end_date: str | None
    lookback_used: dict[str, int]
    momentum_20d: float | None
    momentum_60d: float | None
    volatility_20d: float | None
    risk_adjusted_momentum: float | None
    rank: int | None
    selected: bool
    excluded: bool
    exclusion_reason: str | None
    factor_values: dict[str, float | None] | None = None
    factor_contributions: dict[str, float] | None = None
    family_contributions: dict[str, float] | None = None
    factor_confidence: dict[str, float] | None = None
    overall_confidence: float | None = None
    composite_alpha_score: float | None = None


@dataclass(frozen=True)
class AlphaResult:
    config: dict
    as_of_date: str | None
    data_start_date: str | None
    data_end_date: str | None
    lookback_used: dict[str, int]
    factors: list[AlphaFactorRow]
    selected_symbols: list[str]
    target_weights: dict[str, float]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    suggested_execution_date: str | None
    pipeline_config: dict | None
    pipeline_report_path: str | None
    multi_factor_report_path: str | None
    multi_factor_summary: dict | None
    warnings: list[str]
    report_path: str
    targets_path: str | None

    def to_report(self) -> dict:
        return {
            "config": self.config,
            "as_of_date": self.as_of_date,
            "data_start_date": self.data_start_date,
            "data_end_date": self.data_end_date,
            "lookback_used": self.lookback_used,
            "factors": [asdict(row) for row in self.factors],
            "selected_symbols": self.selected_symbols,
            "target_weights": self.target_weights,
            "excluded_symbols": self.excluded_symbols,
            "exclusion_reasons": self.exclusion_reasons,
            "suggested_execution_date": self.suggested_execution_date,
            "pipeline_config": self.pipeline_config,
            "pipeline_report_path": self.pipeline_report_path,
            "multi_factor_report_path": self.multi_factor_report_path,
            "multi_factor_summary": self.multi_factor_summary,
            "warnings": self.warnings,
            "targets_path": self.targets_path,
        }
