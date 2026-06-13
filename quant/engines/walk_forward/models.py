"""Walk-forward dataclass models (shared between engine and fold runner)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class WalkForwardFoldTask:
    """Serializable task for parallel fold execution."""
    index: int
    strategy: str
    factor: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    symbols: list[str]
    initial_cash: float
    rebalance_frequency: str
    alpha_config: dict | None
    pipeline_config: dict | None
    db_path: str
    report_dir: str


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    fold_id: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_return: float | None
    test_return: float | None
    train_sharpe: float | None
    test_sharpe: float | None
    train_max_drawdown: float | None
    test_max_drawdown: float | None
    ic: float | None
    rank_ic: float | None
    icir: float | None
    turnover: float | None
    cost: float | None
    train_report: str | None
    test_report: str | None
    no_lookahead: bool
    fold_warnings: list[dict[str, str]]


@dataclass(frozen=True)
class WalkForwardResult:
    metadata: dict[str, Any]
    strategy: str
    parameters: dict[str, Any]
    folds: list[WalkForwardFold]
    summary: dict[str, Any]
    rolling_validation: dict[str, Any]
    stability_analysis: dict[str, Any]
    warnings: list[dict[str, str]]
    recommendations: list[str]
    report_path: str

    def to_report(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "strategy": self.strategy,
            "parameters": self.parameters,
            "folds": [asdict(fold) for fold in self.folds],
            "summary": self.summary,
            "rolling_validation": self.rolling_validation,
            "stability_analysis": self.stability_analysis,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }
