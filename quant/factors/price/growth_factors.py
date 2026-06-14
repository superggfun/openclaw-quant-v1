"""Growth-style price-history factor proxies."""

from __future__ import annotations

import pandas as pd

from quant.factors.price._utils import clean_price_series
from quant.factors.specs import price_factor_spec


def growth_price_proxy(closes: pd.Series) -> float | None:
    """Multi-horizon trend persistence score from stored close prices."""
    closes = clean_price_series(closes)
    if len(closes) <= 60:
        return None
    momentum_20d = float((closes.iloc[-1] / closes.iloc[-21]) - 1.0)
    momentum_60d = float((closes.iloc[-1] / closes.iloc[-61]) - 1.0)
    recent = closes.tail(21)
    consistency = float((recent.diff().dropna() > 0).mean())
    return 0.35 * momentum_20d + 0.45 * momentum_60d + 0.20 * consistency


FACTOR_SPECS = (
    price_factor_spec("growth_price_proxy", "price_proxy_growth", "PRICE-ONLY PROXY — NOT a fundamental growth factor. Uses 20d/60d momentum and positive-day consistency. This is a pure price-history computation; use fundamental_growth_score for accounting-based growth.", 60, "price_proxy", growth_price_proxy),
)
