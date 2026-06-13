"""Value-style price-history factor proxies."""

from __future__ import annotations

import pandas as pd

from quant.factors.specs import price_factor_spec


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


FACTOR_SPECS = (
    price_factor_spec("value_score", "value", "Price-only value proxy that favors long-term relative underperformance.", 120, "price_proxy", value_score),
)
