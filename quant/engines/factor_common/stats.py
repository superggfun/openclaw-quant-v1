"""Shared factor research statistics."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd


def mean(values: Iterable[float | None]) -> float | None:
    clean = _clean(values)
    if not clean:
        return None
    return float(pd.Series(clean, dtype="float64").mean())


def std(values: Iterable[float | None]) -> float | None:
    clean = _clean(values)
    if len(clean) < 2:
        return None
    return float(pd.Series(clean, dtype="float64").std())


def positive_rate(values: Iterable[float | None]) -> float | None:
    clean = _clean(values)
    if not clean:
        return None
    return sum(1 for value in clean if value > 0) / len(clean)


def compound_return(values: Iterable[float | None]) -> float | None:
    clean = _clean(values)
    if not clean:
        return None
    total = 1.0
    for value in clean:
        total *= 1.0 + value
    return total - 1.0


def annual_return(values: Iterable[float | None], periods_per_year: float = 252.0) -> float | None:
    clean = _clean(values)
    compounded = compound_return(clean)
    if compounded is None:
        return None
    if 1.0 + compounded <= 0:
        return -1.0
    return (1.0 + compounded) ** (periods_per_year / len(clean)) - 1.0


def annual_volatility(values: Iterable[float | None], periods_per_year: float = 252.0) -> float | None:
    clean = _clean(values)
    if len(clean) < 2:
        return None
    return float(pd.Series(clean, dtype="float64").std() * (periods_per_year**0.5))


def sharpe(values: Iterable[float | None], periods_per_year: float = 252.0) -> float | None:
    clean = _clean(values)
    if len(clean) < 2:
        return None
    series = pd.Series(clean, dtype="float64")
    series_std = float(series.std())
    if series_std <= 0 or pd.isna(series_std):
        return None
    return float((series.mean() / series_std) * (periods_per_year**0.5))


def max_drawdown(values: Iterable[float | None]) -> float | None:
    clean = _clean(values)
    if not clean:
        return None
    arr = np.asarray(clean, dtype="float64")
    equity = np.cumprod(1.0 + arr)
    peak = np.maximum.accumulate(equity)
    drawdown = equity / peak - 1.0
    return float(np.min(drawdown))


def hit_rate(values: Iterable[float | None]) -> float | None:
    return positive_rate(values)


def cumulative_spread_return(values: Iterable[float | None]) -> float | None:
    """Additive cumulative return for spread / forward-spread sequences.

    Multiply-compounding (compound_return) is not appropriate for dollar-neutral
    long-short spread returns where each period represents an independent trade
    rather than reinvested capital.  This function computes a simple additive sum.
    """
    clean = _clean(values)
    if not clean:
        return None
    return float(np.sum(clean))


def spread_max_drawdown(values: Iterable[float | None]) -> float | None:
    """Maximum drawdown on the cumulative-sum curve of spread returns.

    Uses np.cumsum (additive) instead of np.cumprod (multiplicative) because
    overlapping forward-spread returns are diagnostic, not an investable equity
    curve that can be compounded period-over-period.
    """
    clean = _clean(values)
    if not clean:
        return None
    arr = np.asarray(clean, dtype="float64")
    cumulative = np.cumsum(arr)
    peak = np.maximum.accumulate(cumulative)
    drawdown = cumulative - peak
    return float(np.min(drawdown))


def cross_section_correlations(observations: Iterable[Any]) -> tuple[list[float], list[float]]:
    rows = [
        {
            "signal_date": getattr(observation, "signal_date"),
            "factor_value": getattr(observation, "factor_value"),
            "future_return": getattr(observation, "future_return"),
        }
        for observation in observations
    ]
    if not rows:
        return [], []
    frame = pd.DataFrame(rows)
    ic_values = []
    rank_ic_values = []
    for _, group in frame.groupby("signal_date"):
        if len(group) < 2:
            continue
        if group["factor_value"].nunique() < 2 or group["future_return"].nunique() < 2:
            continue
        ic = group["factor_value"].corr(group["future_return"])
        rank_ic = group["factor_value"].rank().corr(group["future_return"].rank())
        if pd.notna(ic):
            ic_values.append(float(ic))
        if pd.notna(rank_ic):
            rank_ic_values.append(float(rank_ic))
    return ic_values, rank_ic_values


def _clean(values: Iterable[float | None]) -> list[float]:
    return [float(value) for value in values if value is not None and pd.notna(value)]
