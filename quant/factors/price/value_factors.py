"""Value-style price-history factor proxies."""

from __future__ import annotations

import pandas as pd

from quant.factors.price._utils import clean_price_series
from quant.factors.specs import price_factor_spec


def value_price_proxy(closes: pd.Series) -> float | None:
    """Price-only value proxy: lower long-term relative performance ranks higher."""
    closes = clean_price_series(closes)
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
    price_factor_spec("value_price_proxy", "price_proxy_value", "PRICE-ONLY PROXY — NOT a fundamental value factor. Favors stocks with poor long-term relative performance adjusted for volatility. This is a pure price-history computation; use fundamental_value_score for accounting-based value.", 120, "price_proxy", value_price_proxy),
)
