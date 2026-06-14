"""Strategy evaluation and performance attribution from generated reports."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from quant.engines.strategy_eval.adapters import prepare_backtest, prepare_factor_backtest
from quant.engines.strategy_eval.builder import build_strategy_evaluation_result
from quant.engines.strategy_eval.models import StrategyEvaluationResult
from quant.engines.strategy_eval.reporting import load_report, report_type, write_report


class StrategyEvaluation:
    """Explain return and risk characteristics from offline strategy reports."""

    def __init__(self, report_dir: str | Path = "reports") -> None:
        self.report_dir = Path(report_dir)

    def evaluate(
        self,
        report_path: str | Path,
        benchmark_returns: dict[str, float] | None = None,
        benchmark_name: str | None = None,
        output_path: str | Path | None = None,
    ) -> StrategyEvaluationResult:
        source_path = Path(report_path)
        data = self._load_report(source_path)
        strategy_type = self._report_type(data)
        if strategy_type == "factor_backtest":
            prepared = self._prepare_factor_backtest(data)
        elif strategy_type == "backtest":
            prepared = self._prepare_backtest(data)
        else:
            raise ValueError("unsupported report type for strategy evaluation")

        result = self._build_result(
            data=data,
            source_path=source_path,
            strategy_type=strategy_type,
            prepared=prepared,
            benchmark_returns=benchmark_returns,
            benchmark_name=benchmark_name,
        )
        report_file = self._write_report(result, output_path)
        return replace(result, report_path=str(report_file))

    @staticmethod
    def _prepare_factor_backtest(data: dict[str, Any]) -> dict[str, Any]:
        return prepare_factor_backtest(data)

    @staticmethod
    def _prepare_backtest(data: dict[str, Any]) -> dict[str, Any]:
        return prepare_backtest(data)

    @staticmethod
    def _build_result(
        data: dict[str, Any],
        source_path: Path,
        strategy_type: str,
        prepared: dict[str, Any],
        benchmark_returns: dict[str, float] | None,
        benchmark_name: str | None,
    ) -> StrategyEvaluationResult:
        return build_strategy_evaluation_result(data, source_path, strategy_type, prepared, benchmark_returns, benchmark_name)

    @staticmethod
    def _load_report(path: Path) -> dict[str, Any]:
        return load_report(path)

    @staticmethod
    def _report_type(data: dict[str, Any]) -> str:
        return report_type(data)

    def _write_report(self, result: StrategyEvaluationResult, output_path: str | Path | None = None) -> Path:
        return write_report(result, self.report_dir, output_path)


__all__ = ["StrategyEvaluation", "StrategyEvaluationResult"]
