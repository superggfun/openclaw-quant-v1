"""Mean-reversion factor proxies."""

from __future__ import annotations

import pandas as pd


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
