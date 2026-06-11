"""Low-volatility factor proxies."""

from __future__ import annotations

import pandas as pd


def low_volatility_score(closes: pd.Series) -> float | None:
    """Higher scores indicate lower recent realized volatility."""
    closes = pd.to_numeric(closes, errors="coerce").dropna()
    returns = closes.pct_change().dropna().tail(20)
    if len(returns) < 20:
        return None
    volatility = float(returns.std())
    if volatility <= 0:
        return None
    return -volatility
