"""Strategy evaluation and performance attribution from generated reports."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from quant.engines.strategy_eval.adapters import prepare_backtest, prepare_factor_backtest
from quant.engines.strategy_eval.builder import build_strategy_evaluation_result
from quant.engines.strategy_eval.metrics import (
    DEFAULT_ROLLING_WINDOWS,
    annual_return,
    annual_volatility,
    average_loss,
    average_win,
    backtest_average_gross_exposure,
    backtest_cost_by_symbol,
    backtest_symbol_contributions,
    backtest_turnover_by_symbol,
    benchmark_metrics,
    best_period,
    calmar,
    compatible_period_frequency,
    compound_return,
    concentration,
    concentration_from_weights,
    cost_drag,
    cost_to_return_ratio,
    diagnostic_warnings,
    drawdown,
    drawdown_stats,
    equity_returns,
    evaluation_window,
    factor_side_attribution,
    factor_symbol_contributions,
    factor_turnover_by_symbol,
    hit_rate,
    interpretation_notes,
    mean,
    methodology_notes,
    normalize_drawdown,
    period_aggregate_returns,
    period_attribution,
    return_concentration,
    returns_series,
    rolling_metrics,
    series_to_dict,
    sharpe,
    sortino,
    top_contributors,
    top_detractors,
    value_or,
    win_loss_ratio,
    worst_period,
)
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

    @staticmethod
    def _returns_series(returns_by_date: dict[str, float | None]) -> pd.Series:
        return returns_series(returns_by_date)

    @staticmethod
    def _equity_returns(equity_curve: list[dict[str, Any]]) -> pd.Series:
        return equity_returns(equity_curve)

    @staticmethod
    def _factor_symbol_contributions(periods: list[dict[str, Any]]) -> dict[str, float]:
        return factor_symbol_contributions(periods)

    @staticmethod
    def _factor_turnover_by_symbol(periods: list[dict[str, Any]]) -> dict[str, float]:
        return factor_turnover_by_symbol(periods)

    @staticmethod
    def _backtest_symbol_contributions(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
        return backtest_symbol_contributions(trades, denominator)

    @staticmethod
    def _backtest_cost_by_symbol(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
        return backtest_cost_by_symbol(trades, denominator)

    @staticmethod
    def _backtest_turnover_by_symbol(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
        return backtest_turnover_by_symbol(trades, denominator)

    @staticmethod
    def _concentration(data: dict[str, Any], strategy_type: str) -> dict[str, float | str | None]:
        return concentration(data, strategy_type)

    @staticmethod
    def _concentration_from_weights(weights: dict[str, float]) -> dict[str, float | str | None]:
        return concentration_from_weights(weights)

    @staticmethod
    def _backtest_average_gross_exposure(equity_curve: list[dict[str, Any]]) -> float | None:
        return backtest_average_gross_exposure(equity_curve)

    @staticmethod
    def _factor_side_attribution(periods: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
        return factor_side_attribution(periods, data)

    @staticmethod
    def _drawdown(returns: pd.Series, contributions: dict[str, float], max_drawdown: float | None = None) -> dict[str, Any]:
        return drawdown(returns, contributions, max_drawdown=max_drawdown)

    @staticmethod
    def _drawdown_stats(returns: pd.Series) -> dict[str, Any]:
        return drawdown_stats(returns)

    @staticmethod
    def _rolling_metrics(returns: pd.Series, windows: list[int] | None = None) -> dict[str, Any]:
        return rolling_metrics(returns, windows)

    @staticmethod
    def _period_aggregate_returns(returns: pd.Series, frequency: str) -> dict[str, float]:
        return period_aggregate_returns(returns, frequency)

    @staticmethod
    def _period_attribution(returns: pd.Series) -> dict[str, float]:
        return period_attribution(returns)

    @staticmethod
    def _compatible_period_frequency(frequency: str) -> str:
        return compatible_period_frequency(frequency)

    @staticmethod
    def _benchmark_metrics(
        returns: pd.Series,
        benchmark_returns: dict[str, float] | None,
        benchmark_name: str | None,
        total_return: float | None,
    ) -> dict[str, Any]:
        return benchmark_metrics(returns, benchmark_returns, benchmark_name, total_return)

    @staticmethod
    def _diagnostic_warnings(
        returns: pd.Series,
        total_return: float | None,
        sharpe_ratio: float | None,
        max_drawdown: float | None,
        turnover: float | None,
        cost_drag_value: float | None,
        benchmark_metrics_value: dict[str, Any],
        symbol_contributions: dict[str, float],
        long_short_attribution: dict[str, Any],
        source_warnings: list[str],
    ) -> list[dict[str, str]]:
        return diagnostic_warnings(
            returns,
            total_return,
            sharpe_ratio,
            max_drawdown,
            turnover,
            cost_drag_value,
            benchmark_metrics_value,
            symbol_contributions,
            long_short_attribution,
            source_warnings,
        )

    @staticmethod
    def _top_contributors(contributions: dict[str, float]) -> list[dict[str, float | str]]:
        return top_contributors(contributions)

    @staticmethod
    def _top_detractors(contributions: dict[str, float]) -> list[dict[str, float | str]]:
        return top_detractors(contributions)

    @staticmethod
    def _return_concentration(contributions: dict[str, float], total_return: float | None) -> dict[str, float | None]:
        return return_concentration(contributions, total_return)

    @staticmethod
    def _interpretation_notes(strategy_type: str) -> list[str]:
        return interpretation_notes(strategy_type)

    @staticmethod
    def _methodology_notes(strategy_type: str) -> dict[str, str]:
        return methodology_notes(strategy_type)

    @staticmethod
    def _evaluation_window(returns: pd.Series) -> dict[str, str | None]:
        return evaluation_window(returns)

    @staticmethod
    def _series_to_dict(series: pd.Series) -> dict[str, float]:
        return series_to_dict(series)

    @staticmethod
    def _value_or(value: Any, fallback: Any) -> Any:
        return value_or(value, fallback)

    @staticmethod
    def _compound_return(values: list[float]) -> float | None:
        return compound_return(values)

    @staticmethod
    def _annual_return(values: list[float]) -> float | None:
        return annual_return(values)

    @staticmethod
    def _annual_volatility(values: list[float]) -> float | None:
        return annual_volatility(values)

    @staticmethod
    def _sharpe(values: list[float]) -> float | None:
        return sharpe(values)

    @staticmethod
    def _sortino(values: list[float]) -> float | None:
        return sortino(values)

    @staticmethod
    def _calmar(annual_return_value: float | None, max_drawdown: float | None) -> float | None:
        return calmar(annual_return_value, max_drawdown)

    @staticmethod
    def _hit_rate(values: list[float]) -> float | None:
        return hit_rate(values)

    @staticmethod
    def _average_win(values: list[float]) -> float | None:
        return average_win(values)

    @staticmethod
    def _average_loss(values: list[float]) -> float | None:
        return average_loss(values)

    @staticmethod
    def _win_loss_ratio(values: list[float]) -> float | None:
        return win_loss_ratio(values)

    @staticmethod
    def _best_period(returns: pd.Series) -> dict[str, Any] | None:
        return best_period(returns)

    @staticmethod
    def _worst_period(returns: pd.Series) -> dict[str, Any] | None:
        return worst_period(returns)

    @staticmethod
    def _cost_drag(total_cost: float, capital_base: float | None) -> float | None:
        return cost_drag(total_cost, capital_base)

    @staticmethod
    def _cost_to_return_ratio(total_cost: float, total_return: float | None, capital_base: float | None = None) -> float | None:
        return cost_to_return_ratio(total_cost, total_return, capital_base)

    @staticmethod
    def _normalize_drawdown(value: float | None) -> float | None:
        return normalize_drawdown(value)

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return mean(values)

    def _write_report(self, result: StrategyEvaluationResult, output_path: str | Path | None = None) -> Path:
        return write_report(result, self.report_dir, output_path)


__all__ = ["DEFAULT_ROLLING_WINDOWS", "StrategyEvaluation", "StrategyEvaluationResult"]
