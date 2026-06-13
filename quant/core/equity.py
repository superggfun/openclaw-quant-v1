"""Shared equity-curve metric calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class EquityCurveStats:
    series: pd.Series
    returns: pd.Series
    drawdowns: pd.Series
    final_value: float
    total_return: float
    annual_return: float
    volatility: float | None
    sharpe: float | None
    max_drawdown: float | None


def equity_curve_stats(
    equity_curve: list[dict[str, Any]],
    initial_cash: float,
    *,
    min_return_count_for_volatility: int = 1,
    empty_volatility: float | None = 0.0,
    empty_sharpe: float | None = 0.0,
    nonpositive_annual_return: float | None = None,
) -> EquityCurveStats:
    series = pd.Series(
        [row["equity"] for row in equity_curve],
        index=pd.to_datetime([row["date"] for row in equity_curve]),
        dtype="float64",
    )
    returns = series.pct_change().dropna()
    final_value = float(series.iloc[-1])
    total_return = (final_value / initial_cash) - 1.0
    years = max((series.index[-1] - series.index[0]).days / 365.25, 1 / 365.25)
    if final_value <= 0 and nonpositive_annual_return is not None:
        annual_return = nonpositive_annual_return
    else:
        annual_return = (final_value / initial_cash) ** (1 / years) - 1.0
    drawdowns = (series / series.cummax()) - 1.0
    enough_returns = len(returns) >= min_return_count_for_volatility
    std = returns.std() if enough_returns else None
    volatility = float(std * math.sqrt(252)) if std is not None else empty_volatility
    if std is not None and std != 0 and not pd.isna(std):
        sharpe = float((returns.mean() / std) * math.sqrt(252))
    else:
        sharpe = empty_sharpe
    max_drawdown = float(drawdowns.min()) if not drawdowns.empty else None
    return EquityCurveStats(
        series=series,
        returns=returns,
        drawdowns=drawdowns,
        final_value=final_value,
        total_return=float(total_return),
        annual_return=float(annual_return),
        volatility=volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
    )
