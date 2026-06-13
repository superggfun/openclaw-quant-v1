"""Build strategy evaluation report payloads."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from quant.engines.strategy_eval.metrics import (
    annual_return,
    annual_volatility,
    benchmark_metrics as build_benchmark_metrics,
    best_period,
    calmar,
    compound_return,
    concentration,
    cost_drag as calculate_cost_drag,
    cost_to_return_ratio,
    diagnostic_warnings,
    drawdown,
    drawdown_stats,
    evaluation_window,
    hit_rate,
    interpretation_notes,
    methodology_notes,
    normalize_drawdown,
    average_loss,
    average_win,
    period_aggregate_returns,
    period_attribution,
    return_concentration,
    rolling_metrics,
    sharpe,
    sortino,
    top_contributors,
    top_detractors,
    value_or,
    win_loss_ratio,
    worst_period,
)
from quant.engines.strategy_eval.models import StrategyEvaluationResult


def build_strategy_evaluation_result(
    data: dict[str, Any],
    source_path: Path,
    strategy_type: str,
    prepared: dict[str, Any],
    benchmark_returns: dict[str, float] | None,
    benchmark_name: str | None,
) -> StrategyEvaluationResult:
    returns: pd.Series = prepared["returns"]
    overrides = prepared["summary_overrides"]
    values = returns.tolist()
    total_return = value_or(overrides.get("total_return"), compound_return(values))
    annual_return_value = value_or(overrides.get("annual_return"), annual_return(values))
    annual_volatility_value = value_or(overrides.get("annual_volatility"), annual_volatility(values))
    sharpe_ratio = value_or(overrides.get("sharpe_ratio"), sharpe(values))
    max_drawdown = normalize_drawdown(
        value_or(overrides.get("max_drawdown"), drawdown_stats(returns)["max_drawdown"])
    )
    total_cost = float(prepared.get("total_cost") or 0.0)
    cost_drag = calculate_cost_drag(total_cost, prepared.get("capital_base"))
    summary_metrics = {
        "total_return": total_return,
        "annual_return": annual_return_value,
        "annual_volatility": annual_volatility_value,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino(values),
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar(annual_return_value, max_drawdown),
        "hit_rate": value_or(overrides.get("hit_rate"), hit_rate(values)),
        "win_loss_ratio": win_loss_ratio(values),
        "average_win": average_win(values),
        "average_loss": average_loss(values),
        "best_period": best_period(returns),
        "worst_period": worst_period(returns),
        "turnover": prepared.get("turnover"),
        "total_cost": total_cost,
        "cost_to_return_ratio": cost_to_return_ratio(total_cost, total_return, prepared.get("capital_base")),
        "gross_exposure": prepared.get("gross_exposure"),
        "net_exposure": prepared.get("net_exposure"),
        "cash_drag": prepared.get("cash_drag"),
    }
    benchmark_metrics = build_benchmark_metrics(returns, benchmark_returns, benchmark_name, total_return)
    if benchmark_metrics:
        summary_metrics["benchmark_return"] = benchmark_metrics.get("benchmark_return")
        summary_metrics["excess_return"] = benchmark_metrics.get("excess_return")
        summary_metrics["information_ratio"] = benchmark_metrics.get("information_ratio")

    return_attribution = {
        "by_symbol": prepared["symbol_contributions"],
        "by_side": prepared["long_short_attribution"],
        "long_leg_return": prepared["long_short_attribution"].get("long_side"),
        "short_leg_return": prepared["long_short_attribution"].get("short_side"),
        "long_short_return": prepared["long_short_attribution"].get("long_short"),
        "long_side_contribution": prepared["long_short_attribution"].get("long_side_contribution"),
        "short_side_contribution": prepared["long_short_attribution"].get("short_side_contribution"),
        "cash_drag": prepared.get("cash_drag"),
        "cost_drag": cost_drag,
        "period_attribution": period_attribution(returns),
    }
    top_positive = top_contributors(prepared["symbol_contributions"])
    top_negative = top_detractors(prepared["symbol_contributions"])
    attribution = {
        "return_attribution": return_attribution,
        "cost_attribution_by_symbol": prepared["cost_by_symbol"],
        "turnover_attribution_by_symbol": prepared["turnover_by_symbol"],
        "top_positive_contributors": top_positive,
        "top_negative_contributors": top_negative,
        "position_attribution": {
            "top_contributors": top_positive,
            "top_detractors": top_negative,
        },
        "return_concentration": return_concentration(prepared["symbol_contributions"], total_return),
        "methodology": methodology_notes(strategy_type),
        "risk_attribution": {
            "gross_exposure": prepared.get("gross_exposure"),
            "net_exposure": prepared.get("net_exposure"),
            "average_cash": prepared.get("cash_drag"),
            "average_turnover": prepared.get("turnover"),
            "concentration": concentration(data, strategy_type),
        },
        "drawdown_attribution": drawdown(returns, prepared["symbol_contributions"], max_drawdown=max_drawdown),
    }
    warnings = diagnostic_warnings(
        returns=returns,
        total_return=total_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        turnover=prepared.get("turnover"),
        cost_drag=cost_drag,
        benchmark_metrics=benchmark_metrics,
        symbol_contributions=prepared["symbol_contributions"],
        long_short_attribution=prepared["long_short_attribution"],
        source_warnings=prepared["source_warnings"],
    )
    if prepared.get("no_lookahead") is not True:
        warnings.append({"code": "NO_LOOKAHEAD_NOT_MARKED", "reason": "input report is not marked no_lookahead"})
    robustness_diagnostics = {
        "rolling_metrics": rolling_metrics(returns),
        "monthly_returns": period_aggregate_returns(returns, "ME"),
        "yearly_returns": period_aggregate_returns(returns, "YE"),
        "diagnostics": {warning["code"]: warning["reason"] for warning in warnings},
    }
    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "engine": "StrategyEvaluation",
        "no_new_strategy_generated": True,
        "no_live_trading": True,
        "source_no_lookahead": prepared.get("no_lookahead"),
    }
    return StrategyEvaluationResult(
        metadata=metadata,
        input_report_paths={"primary_report": str(source_path)},
        strategy_type=strategy_type,
        evaluation_window=evaluation_window(returns),
        summary_metrics=summary_metrics,
        benchmark_metrics=benchmark_metrics,
        attribution=attribution,
        robustness_diagnostics=robustness_diagnostics,
        warnings=warnings,
        interpretation_notes=interpretation_notes(strategy_type),
        report_path="",
    )
