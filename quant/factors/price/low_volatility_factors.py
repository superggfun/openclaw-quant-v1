"""Low-volatility factor proxies."""

from __future__ import annotations

import pandas as pd

from quant.factors.specs import price_factor_spec


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


FACTOR_SPECS = (
    price_factor_spec("low_volatility_score", "low_volatility", "Low-volatility score based on negative 20-day realized volatility.", 20, "risk_proxy", low_volatility_score),
)
