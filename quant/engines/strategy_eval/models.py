"""Models for strategy evaluation reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyEvaluationResult:
    metadata: dict[str, Any]
    input_report_paths: dict[str, str | None]
    strategy_type: str
    evaluation_window: dict[str, str | None]
    summary_metrics: dict[str, Any]
    benchmark_metrics: dict[str, Any]
    attribution: dict[str, Any]
    robustness_diagnostics: dict[str, Any]
    warnings: list[dict[str, str]]
    interpretation_notes: list[str]
    report_path: str

    @property
    def report_type(self) -> str:
        return self.strategy_type

    @property
    def source_report(self) -> str:
        return self.input_report_paths.get("primary_report") or ""

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_return": self.summary_metrics.get("total_return"),
            "annual_return": self.summary_metrics.get("annual_return"),
            "volatility": self.summary_metrics.get("annual_volatility"),
            "sharpe": self.summary_metrics.get("sharpe_ratio"),
            "max_drawdown": self.summary_metrics.get("max_drawdown"),
            "calmar_ratio": self.summary_metrics.get("calmar_ratio"),
            "hit_rate": self.summary_metrics.get("hit_rate"),
            "turnover": self.summary_metrics.get("turnover"),
        }

    @property
    def return_attribution(self) -> dict[str, Any]:
        return self.attribution.get("return_attribution", {})

    @property
    def position_attribution(self) -> dict[str, Any]:
        return self.attribution.get("position_attribution", {})

    @property
    def risk_attribution(self) -> dict[str, Any]:
        return self.attribution.get("risk_attribution", {})

    @property
    def drawdown(self) -> dict[str, Any]:
        return self.attribution.get("drawdown_attribution", {})

    @property
    def rolling_metrics(self) -> dict[str, Any]:
        return self.robustness_diagnostics.get("rolling_metrics", {})

    @property
    def monthly_returns(self) -> dict[str, float]:
        return self.robustness_diagnostics.get("monthly_returns", {})

    @property
    def yearly_returns(self) -> dict[str, float]:
        return self.robustness_diagnostics.get("yearly_returns", {})

    def to_report(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "input_report_paths": self.input_report_paths,
            "strategy_type": self.strategy_type,
            "evaluation_window": self.evaluation_window,
            "summary_metrics": self.summary_metrics,
            "benchmark_metrics": self.benchmark_metrics,
            "attribution": self.attribution,
            "robustness_diagnostics": self.robustness_diagnostics,
            "warnings": self.warnings,
            "interpretation_notes": self.interpretation_notes,
        }
