"""Input report adapters for strategy evaluation."""

from __future__ import annotations

from typing import Any

from quant.engines.strategy_eval.metrics import (
    backtest_average_gross_exposure,
    backtest_cost_by_symbol,
    backtest_symbol_contributions,
    backtest_turnover_by_symbol,
    equity_returns,
    factor_side_attribution,
    factor_symbol_contributions,
    factor_turnover_by_symbol,
    mean,
    returns_series,
)


def prepare_factor_backtest(data: dict[str, Any]) -> dict[str, Any]:
    periods = data.get("periods")
    if not isinstance(periods, list) or not periods:
        raise ValueError("factor_backtest report must contain non-empty periods")
    returns = returns_series(
        {
            str(period["signal_date"]): period.get("long_short_return")
            for period in periods
            if period.get("long_short_return") is not None
        }
    )
    symbol_contributions = factor_symbol_contributions(periods)
    side_attribution = factor_side_attribution(periods, data)
    return {
        "returns": returns,
        "periods": periods,
        "symbol_contributions": symbol_contributions,
        "cost_by_symbol": {},
        "turnover_by_symbol": factor_turnover_by_symbol(periods),
        "long_short_attribution": side_attribution,
        "total_cost": 0.0,
        "turnover": data.get("turnover"),
        "gross_exposure": data.get("gross_exposure"),
        "net_exposure": data.get("net_exposure"),
        "cash_drag": 0.0,
        "capital_base": 1.0,
        "source_warnings": data.get("warnings", []),
        "no_lookahead": data.get("no_lookahead"),
        "summary_overrides": {
            "total_return": data.get("long_short_return"),
            "annual_return": data.get("annual_return") or data.get("long_short_annual_return"),
            "annual_volatility": data.get("volatility") or data.get("long_short_volatility"),
            "sharpe_ratio": data.get("sharpe") or data.get("long_short_sharpe"),
            "max_drawdown": None,
            "hit_rate": data.get("hit_rate"),
        },
    }


def prepare_backtest(data: dict[str, Any]) -> dict[str, Any]:
    metrics = data.get("metrics")
    equity_curve = data.get("equity_curve")
    if not isinstance(metrics, dict):
        raise ValueError("backtest report must contain metrics")
    if not isinstance(equity_curve, list) or len(equity_curve) < 2:
        raise ValueError("backtest report must contain at least two equity_curve rows")
    returns = equity_returns(equity_curve)
    total_cost = float(metrics.get("total_cost") or 0.0)
    initial_cash = float(data.get("initial_cash") or 0.0)
    cash_ratios = [
        (float(row.get("cash") or 0.0) / float(row.get("equity") or 1.0))
        for row in equity_curve
        if float(row.get("equity") or 0.0) > 0
    ]
    reported_cash_ratio = metrics.get("cash_ratio")
    reported_exposure = (
        max(0.0, 1.0 - float(reported_cash_ratio))
        if reported_cash_ratio is not None
        else backtest_average_gross_exposure(equity_curve)
    )
    return {
        "returns": returns,
        "periods": [],
        "symbol_contributions": backtest_symbol_contributions(data.get("trades", []), initial_cash),
        "cost_by_symbol": backtest_cost_by_symbol(data.get("trades", []), initial_cash),
        "turnover_by_symbol": backtest_turnover_by_symbol(data.get("trades", []), initial_cash),
        "long_short_attribution": {
            "long_side": metrics.get("total_return"),
            "short_side": 0.0,
            "long_short": metrics.get("total_return"),
        },
        "total_cost": total_cost,
        "turnover": metrics.get("turnover"),
        "gross_exposure": reported_exposure,
        "net_exposure": reported_exposure,
        "cash_drag": mean(cash_ratios),
        "capital_base": initial_cash if initial_cash > 0 else 1.0,
        "source_warnings": [],
        "no_lookahead": data.get("no_lookahead"),
        "summary_overrides": {
            "total_return": metrics.get("total_return"),
            "annual_return": metrics.get("annual_return"),
            "annual_volatility": metrics.get("volatility"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
        },
    }
