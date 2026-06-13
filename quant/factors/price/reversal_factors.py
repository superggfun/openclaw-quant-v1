"""Mean-reversion factor proxies."""

from __future__ import annotations

import pandas as pd

from quant.factors.specs import price_factor_spec


def reversal_5d(closes: pd.Series) -> float | None:
    closes = pd.to_numeric(closes, errors="coerce").dropna()
    if len(closes) <= 5:
        return None
    return -float((closes.iloc[-1] / closes.iloc[-6]) - 1.0)


def reversal_20d(closes: pd.Series) -> float | None:
    closes = pd.to_numeric(closes, errors="coerce").dropna()
    if len(closes) <= 20:
        return None
    return -float((closes.iloc[-1] / closes.iloc[-21]) - 1.0)


FACTOR_SPECS = (
    price_factor_spec("reversal_5d", "reversal", "5-day mean-reversion score; recent underperformance ranks higher.", 5, "mean_reversion", reversal_5d),
    price_factor_spec("reversal_20d", "reversal", "20-day mean-reversion score; recent underperformance ranks higher.", 20, "mean_reversion", reversal_20d),
)
