"""Quality-style price-history factor proxies."""

from __future__ import annotations

import pandas as pd


def quality_score(closes: pd.Series) -> float | None:
    """Reward return consistency, positive days, and drawdown resistance."""
    closes = pd.to_numeric(closes, errors="coerce").dropna()
    if len(closes) <= 60:
        return None
    window = closes.tail(61)
    returns = window.pct_change().dropna()
    if len(returns) < 60:
        return None
    volatility = float(returns.std())
    if volatility <= 0:
        return None
    positive_rate = float((returns > 0).mean())
    cumulative = (1.0 + returns).cumprod()
    max_drawdown = float((cumulative / cumulative.cummax() - 1.0).min())
    mean_return = float(returns.mean())
    return (mean_return / volatility) + positive_rate + max_drawdown
