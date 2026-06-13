"""Metrics, attribution, and diagnostics for strategy evaluation."""

from __future__ import annotations

from typing import Any

import pandas as pd


DEFAULT_ROLLING_WINDOWS = [20, 60]


def returns_series(returns_by_date: dict[str, float | None]) -> pd.Series:
    values = {
        pd.to_datetime(date): float(value)
        for date, value in returns_by_date.items()
        if value is not None and pd.notna(value)
    }
    return pd.Series(values, dtype="float64").sort_index()


def equity_returns(equity_curve: list[dict[str, Any]]) -> pd.Series:
    frame = pd.DataFrame(equity_curve)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["equity"] = pd.to_numeric(frame["equity"], errors="coerce")
    returns = frame.sort_values("date").set_index("date")["equity"].pct_change().dropna()
    return returns.astype("float64")


def factor_symbol_contributions(periods: list[dict[str, Any]]) -> dict[str, float]:
    contributions: dict[str, float] = {}
    for period in periods:
        long_symbols = period.get("long_symbols") or []
        short_symbols = period.get("short_symbols") or []
        long_return = period.get("long_return")
        short_return = period.get("short_return")
        if long_return is not None and long_symbols:
            per_symbol = float(long_return) / len(long_symbols)
            for symbol in long_symbols:
                contributions[symbol] = contributions.get(symbol, 0.0) + per_symbol
        if short_return is not None and short_symbols:
            per_symbol = -float(short_return) / len(short_symbols)
            for symbol in short_symbols:
                contributions[symbol] = contributions.get(symbol, 0.0) + per_symbol
    return {symbol: float(value) for symbol, value in sorted(contributions.items())}


def factor_turnover_by_symbol(periods: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    previous: dict[str, float] | None = None
    for period in periods:
        weights = dict(period.get("long_weights") or {})
        weights.update(period.get("short_weights") or {})
        weights = {symbol: float(weight) for symbol, weight in weights.items()}
        if previous is not None:
            for symbol in set(previous) | set(weights):
                totals[symbol] = totals.get(symbol, 0.0) + abs(weights.get(symbol, 0.0) - previous.get(symbol, 0.0))
        previous = weights
    return {symbol: float(value) for symbol, value in sorted(totals.items())}


def backtest_symbol_contributions(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
    contributions: dict[str, float] = {}
    scale = denominator if denominator > 0 else 1.0
    for trade in trades or []:
        symbol = str(trade.get("symbol"))
        side = str(trade.get("side", "")).upper()
        notional = float(trade.get("notional") or 0.0)
        cost = float(trade.get("total_cost") or 0.0)
        signed = notional if side == "SELL" else -notional
        contributions[symbol] = contributions.get(symbol, 0.0) + (signed - cost) / scale
    return {symbol: float(value) for symbol, value in sorted(contributions.items())}


def backtest_cost_by_symbol(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
    scale = denominator if denominator > 0 else 1.0
    costs: dict[str, float] = {}
    for trade in trades or []:
        symbol = str(trade.get("symbol"))
        costs[symbol] = costs.get(symbol, 0.0) - float(trade.get("total_cost") or 0.0) / scale
    return {symbol: float(value) for symbol, value in sorted(costs.items())}


def backtest_turnover_by_symbol(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
    scale = denominator if denominator > 0 else 1.0
    turnover: dict[str, float] = {}
    for trade in trades or []:
        symbol = str(trade.get("symbol"))
        turnover[symbol] = turnover.get(symbol, 0.0) + abs(float(trade.get("notional") or 0.0)) / scale
    return {symbol: float(value) for symbol, value in sorted(turnover.items())}


def concentration(data: dict[str, Any], strategy_type: str) -> dict[str, float | str | None]:
    if strategy_type == "factor_backtest":
        weights_by_symbol: dict[str, list[float]] = {}
        for period in data.get("periods", []):
            weights = dict(period.get("long_weights") or {})
            weights.update(period.get("short_weights") or {})
            for symbol, weight in weights.items():
                weights_by_symbol.setdefault(symbol, []).append(abs(float(weight)))
        average_weights = {symbol: sum(values) / len(values) for symbol, values in weights_by_symbol.items() if values}
        return concentration_from_weights(average_weights)
    weights_by_symbol: dict[str, list[float]] = {}
    for row in data.get("equity_curve", []):
        equity = float(row.get("equity") or 0.0)
        positions = row.get("positions") or {}
        if equity <= 0 or not isinstance(positions, dict):
            continue
        for symbol, value in positions.items():
            weights_by_symbol.setdefault(symbol, []).append(abs(float(value) / equity))
    average_weights = {symbol: sum(values) / len(values) for symbol, values in weights_by_symbol.items() if values}
    return concentration_from_weights(average_weights)


def concentration_from_weights(weights: dict[str, float]) -> dict[str, float | str | None]:
    if not weights:
        return {"largest_position": None, "largest_position_weight": None, "top_3_weight": 0.0, "top_5_weight": 0.0}
    ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    return {
        "largest_position": ranked[0][0],
        "largest_position_weight": float(ranked[0][1]),
        "top_3_weight": float(sum(value for _, value in ranked[:3])),
        "top_5_weight": float(sum(value for _, value in ranked[:5])),
    }


def backtest_average_gross_exposure(equity_curve: list[dict[str, Any]]) -> float | None:
    exposures = []
    for row in equity_curve:
        equity = float(row.get("equity") or 0.0)
        positions = row.get("positions") or {}
        if equity <= 0 or not isinstance(positions, dict):
            continue
        exposures.append(sum(abs(float(value)) for value in positions.values()) / equity)
    return mean(exposures)


def factor_side_attribution(periods: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    long_period_returns = [
        float(period["long_return"])
        for period in periods
        if period.get("long_return") is not None and period.get("long_short_return") is not None
    ]
    short_period_returns = [
        float(period["short_return"])
        for period in periods
        if period.get("short_return") is not None and period.get("long_short_return") is not None
    ]
    long_side_contribution = sum(long_period_returns) if long_period_returns else None
    short_side_contribution = -sum(short_period_returns) if short_period_returns else None
    return {
        "long_side": data.get("long_leg_return"),
        "short_side": data.get("short_leg_return"),
        "long_short": data.get("long_short_return"),
        "long_side_contribution": long_side_contribution,
        "short_side_contribution": short_side_contribution,
        "period_contribution_sum": (
            long_side_contribution + short_side_contribution
            if long_side_contribution is not None and short_side_contribution is not None
            else None
        ),
        "raw_long_leg_return": data.get("long_leg_return"),
        "raw_short_leg_underlying_return": data.get("short_leg_return"),
        "source_long_short_return": data.get("long_short_return"),
    }


def drawdown(returns: pd.Series, contributions: dict[str, float], max_drawdown: float | None = None) -> dict[str, Any]:
    stats = drawdown_stats(returns)
    detractors = top_detractors(contributions)
    return {
        "max_drawdown": max_drawdown if max_drawdown is not None else stats["max_drawdown"],
        "drawdown_start": stats["drawdown_start"],
        "drawdown_end": stats["drawdown_end"],
        "drawdown_duration": stats["drawdown_duration"],
        "largest_contributors_to_drawdown": detractors[:5],
    }


def drawdown_stats(returns: pd.Series) -> dict[str, Any]:
    if returns.empty:
        return {"max_drawdown": None, "drawdown_start": None, "drawdown_end": None, "drawdown_duration": 0}
    equity = (1.0 + returns).cumprod()
    running_max = equity.cummax().clip(lower=1.0)
    drawdowns = equity / running_max - 1.0
    end = drawdowns.idxmin()
    start = equity.loc[:end].idxmax() if equity.loc[:end].max() >= 1.0 else returns.index.min()
    return {
        "max_drawdown": float(drawdowns.loc[end]),
        "drawdown_start": start.strftime("%Y-%m-%d"),
        "drawdown_end": end.strftime("%Y-%m-%d"),
        "drawdown_duration": int((end - start).days),
    }


def rolling_metrics(returns: pd.Series, windows: list[int] | None = None) -> dict[str, Any]:
    windows = windows or DEFAULT_ROLLING_WINDOWS
    output: dict[str, Any] = {}
    if returns.empty:
        return {str(window): {"rolling_return": {}, "rolling_sharpe": {}, "rolling_drawdown": {}} for window in windows}
    for window in windows:
        rolling_return = (1.0 + returns).rolling(window).apply(lambda values: float(values.prod() - 1.0), raw=False)
        rolling_std = returns.rolling(window).std()
        rolling_mean = returns.rolling(window).mean()
        rolling_sharpe = (rolling_mean / rolling_std) * (252.0 ** 0.5)
        equity = (1.0 + returns).cumprod()
        rolling_peak = equity.rolling(window).max()
        rolling_drawdown = equity / rolling_peak - 1.0
        output[str(window)] = {
            "rolling_return": series_to_dict(rolling_return.dropna()),
            "rolling_sharpe": series_to_dict(rolling_sharpe.dropna()),
            "rolling_drawdown": series_to_dict(rolling_drawdown.dropna()),
        }
    return output


def period_aggregate_returns(returns: pd.Series, frequency: str) -> dict[str, float]:
    if returns.empty:
        return {}
    aggregated = (1.0 + returns).resample(compatible_period_frequency(frequency)).prod() - 1.0
    if frequency == "ME":
        return {index.strftime("%Y-%m"): float(value) for index, value in aggregated.items()}
    return {index.strftime("%Y"): float(value) for index, value in aggregated.items()}


def period_attribution(returns: pd.Series) -> dict[str, float]:
    return period_aggregate_returns(returns, "ME")


def compatible_period_frequency(frequency: str) -> str:
    try:
        pd.tseries.frequencies.to_offset(frequency)
        return frequency
    except ValueError:
        aliases = {"ME": "M", "YE": "Y"}
        return aliases.get(frequency, frequency)


def benchmark_metrics(
    returns: pd.Series,
    benchmark_returns: dict[str, float] | None,
    benchmark_name: str | None,
    total_return: float | None,
) -> dict[str, Any]:
    if not benchmark_returns:
        return {}
    benchmark = returns_series(benchmark_returns)
    benchmark_return = compound_return(benchmark.tolist())
    excess_return = (total_return - benchmark_return) if total_return is not None and benchmark_return is not None else None
    active = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    information_ratio = None
    if len(active) > 1:
        diff = active.iloc[:, 0] - active.iloc[:, 1]
        std = float(diff.std())
        if std > 0 and pd.notna(std):
            information_ratio = float((diff.mean() / std) * (252.0 ** 0.5))
    return {
        "benchmark": benchmark_name,
        "benchmark_return": benchmark_return,
        "excess_return": excess_return,
        "information_ratio": information_ratio,
    }


def diagnostic_warnings(
    returns: pd.Series,
    total_return: float | None,
    sharpe_ratio: float | None,
    max_drawdown: float | None,
    turnover: float | None,
    cost_drag: float | None,
    benchmark_metrics: dict[str, Any],
    symbol_contributions: dict[str, float],
    long_short_attribution: dict[str, Any],
    source_warnings: list[str],
) -> list[dict[str, str]]:
    warnings = [{"code": "SOURCE_WARNING", "reason": str(warning)} for warning in source_warnings]
    if len(returns) < 30:
        warnings.append({"code": "LOW_OBSERVATION_COUNT", "reason": "fewer than 30 return observations; Sharpe may be unstable"})
    if turnover is not None and turnover > 1.0:
        warnings.append({"code": "HIGH_TURNOVER", "reason": "turnover is above 1.0"})
    if cost_drag is not None and abs(cost_drag) > 0.02:
        warnings.append({"code": "HIGH_COST_DRAG", "reason": "cost drag exceeds 2% of reported return denominator"})
    if total_return is not None and sharpe_ratio is not None and total_return < 0 < sharpe_ratio:
        warnings.append({"code": "NEGATIVE_COMPOUND_POSITIVE_SHARPE", "reason": "compounded return is negative while arithmetic Sharpe is positive"})
    if max_drawdown is not None and max_drawdown < -0.2:
        warnings.append({"code": "LARGE_DRAWDOWN", "reason": "max drawdown is worse than -20%"})
    if max_drawdown is not None and max_drawdown <= -1.0:
        warnings.append({"code": "CAPITAL_WIPEOUT_OR_MARGIN_LOSS", "reason": "drawdown reaches or exceeds -100%; long-short spread returns may imply margin-style losses"})
    if benchmark_metrics.get("excess_return") is not None and benchmark_metrics["excess_return"] < 0:
        warnings.append({"code": "BENCHMARK_UNDERPERFORMANCE", "reason": "strategy total return is below benchmark return"})
    return_conc = return_concentration(symbol_contributions, total_return)
    if return_conc.get("top_1_pct") is not None and return_conc["top_1_pct"] > 0.5:
        warnings.append({"code": "SYMBOL_CONCENTRATION", "reason": "top contributor explains more than 50% of total return"})
    long_side = long_short_attribution.get("long_side")
    short_side = long_short_attribution.get("short_side")
    if long_side is not None and short_side is not None and abs(float(short_side)) > 0:
        ratio = abs(float(long_side) / float(short_side))
        if ratio > 5 or ratio < 0.2:
            warnings.append({"code": "LONG_SHORT_IMBALANCE", "reason": "long and short leg contributions are highly imbalanced"})
    return warnings


def top_contributors(contributions: dict[str, float]) -> list[dict[str, float | str]]:
    return [
        {"symbol": symbol, "contribution": float(value)}
        for symbol, value in sorted(contributions.items(), key=lambda item: item[1], reverse=True)
        if value > 0
    ][:5]


def top_detractors(contributions: dict[str, float]) -> list[dict[str, float | str]]:
    return [
        {"symbol": symbol, "contribution": float(value)}
        for symbol, value in sorted(contributions.items(), key=lambda item: item[1])
        if value < 0
    ][:5]


def return_concentration(contributions: dict[str, float], total_return: float | None) -> dict[str, float | None]:
    positives = sorted([value for value in contributions.values() if value > 0], reverse=True)
    denominator = abs(float(total_return)) if total_return not in {None, 0.0} else sum(abs(value) for value in positives)
    if denominator <= 0:
        return {"top_1_pct": None, "top_3_pct": None}
    return {
        "top_1_pct": float(positives[0] / denominator) if positives else 0.0,
        "top_3_pct": float(sum(positives[:3]) / denominator) if positives else 0.0,
    }


def interpretation_notes(strategy_type: str) -> list[str]:
    notes = ["offline evaluation only; no live trades or broker APIs are used"]
    if strategy_type == "factor_backtest":
        notes.append("factor long-short reports may use overlapping forward-return observations")
        notes.append("short_side is the raw underlying short basket return; short_side_contribution is sign-adjusted for long-short attribution")
    return notes


def methodology_notes(strategy_type: str) -> dict[str, str]:
    if strategy_type == "factor_backtest":
        return {
            "return_stream": "period long_short_return values from the factor backtest report",
            "max_drawdown": "computed from the period return stream with initial capital treated as the starting high-water mark",
            "by_symbol": "arithmetic period contribution using long weights and negative short weights; not compounded",
            "by_side": "raw leg returns are kept separately from sign-adjusted long-short contributions",
        }
    return {
        "return_stream": "equity_curve percentage changes from the portfolio backtest report",
        "by_symbol": "trade-notional approximation normalized by initial cash",
        "cost": "trade costs normalized by initial cash when available",
    }


def evaluation_window(returns: pd.Series) -> dict[str, str | None]:
    if returns.empty:
        return {"start": None, "end": None}
    return {"start": returns.index.min().strftime("%Y-%m-%d"), "end": returns.index.max().strftime("%Y-%m-%d")}


def series_to_dict(series: pd.Series) -> dict[str, float]:
    return {index.strftime("%Y-%m-%d"): float(value) for index, value in series.items() if pd.notna(value)}


def value_or(value: Any, fallback: Any) -> Any:
    return fallback if value is None else value


def compound_return(values: list[float]) -> float | None:
    if not values:
        return None
    total = 1.0
    for value in values:
        total *= 1.0 + value
    return total - 1.0


def annual_return(values: list[float]) -> float | None:
    compounded = compound_return(values)
    if compounded is None or not values:
        return None
    return (1.0 + compounded) ** (252.0 / len(values)) - 1.0


def annual_volatility(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return float(pd.Series(values, dtype="float64").std() * (252.0 ** 0.5))


def sharpe(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    series = pd.Series(values, dtype="float64")
    std = float(series.std())
    if std <= 0 or pd.isna(std):
        return None
    return float((series.mean() / std) * (252.0 ** 0.5))


def sortino(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    series = pd.Series(values, dtype="float64")
    downside = series[series < 0]
    if len(downside) < 2:
        return None
    downside_std = float(downside.std())
    if downside_std <= 0 or pd.isna(downside_std):
        return None
    return float((series.mean() / downside_std) * (252.0 ** 0.5))


def calmar(annual_return_value: float | None, max_drawdown: float | None) -> float | None:
    if annual_return_value is None or max_drawdown in {None, 0.0}:
        return None
    drawdown_value = abs(float(max_drawdown))
    return None if drawdown_value <= 0 else float(annual_return_value) / drawdown_value


def hit_rate(values: list[float]) -> float | None:
    return None if not values else sum(1 for value in values if value > 0) / len(values)


def average_win(values: list[float]) -> float | None:
    wins = [value for value in values if value > 0]
    return mean(wins)


def average_loss(values: list[float]) -> float | None:
    losses = [value for value in values if value < 0]
    return mean(losses)


def win_loss_ratio(values: list[float]) -> float | None:
    avg_win = average_win(values)
    avg_loss = average_loss(values)
    if avg_win is None or avg_loss in {None, 0.0}:
        return None
    return float(avg_win / abs(avg_loss))


def best_period(returns: pd.Series) -> dict[str, Any] | None:
    if returns.empty:
        return None
    date = returns.idxmax()
    return {"date": date.strftime("%Y-%m-%d"), "return": float(returns.loc[date])}


def worst_period(returns: pd.Series) -> dict[str, Any] | None:
    if returns.empty:
        return None
    date = returns.idxmin()
    return {"date": date.strftime("%Y-%m-%d"), "return": float(returns.loc[date])}


def cost_drag(total_cost: float, capital_base: float | None) -> float | None:
    if total_cost == 0:
        return 0.0
    denominator = abs(float(capital_base)) if capital_base not in {None, 0.0} else 1.0
    return -abs(total_cost) / denominator


def cost_to_return_ratio(total_cost: float, total_return: float | None, capital_base: float | None = None) -> float | None:
    if total_return in {None, 0.0}:
        return None
    denominator = abs(float(total_return))
    if capital_base not in {None, 0.0}:
        denominator *= abs(float(capital_base))
    return abs(float(total_cost)) / denominator


def normalize_drawdown(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    return -abs(value)


def mean(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and pd.notna(value)]
    if not clean:
        return None
    return float(sum(clean) / len(clean))
