"""Value-style price-history factor proxies."""

from __future__ import annotations

import pandas as pd


def value_score(closes: pd.Series) -> float | None:
    """Price-only value proxy: lower long-term relative performance ranks higher."""
    closes = pd.to_numeric(closes, errors="coerce").dropna()
    if len(closes) <= 120:
        return None
    long_return = float((closes.iloc[-1] / closes.iloc[-121]) - 1.0)
    returns = closes.pct_change().dropna().tail(60)
    if len(returns) < 20:
        return None
    volatility = float(returns.std())
    if volatility <= 0:
        return None
    return -long_return / volatility
