"""Quality-style price-history factor proxies."""

from __future__ import annotations

import pandas as pd

from quant.factors.price._utils import clean_price_series
from quant.factors.specs import price_factor_spec


def quality_price_proxy(closes: pd.Series) -> float | None:
    """Reward return consistency, positive days, and drawdown resistance."""
    closes = clean_price_series(closes)
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


FACTOR_SPECS = (
    price_factor_spec("quality_price_proxy", "price_proxy_quality", "PRICE-ONLY PROXY — NOT a fundamental quality factor. Uses Sharpe-like return/vol ratio, positive-day rate, and drawdown resistance. This is a pure price-history computation; use fundamental_quality_score for accounting-based quality.", 60, "price_proxy", quality_price_proxy),
)
