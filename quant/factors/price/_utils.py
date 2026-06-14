"""Shared price-series cleaning for all price-factor modules.

Every price factor should use ``clean_price_series()`` instead of
inlining ``pd.to_numeric(...).dropna()`` so that inf filtering,
time-order enforcement, and positive-price validation happen in one
place.
"""

from __future__ import annotations

import pandas as pd


def clean_price_series(closes: pd.Series) -> pd.Series:
    """Normalize a raw close-price Series for factor computation.

    Returns a copy with:
    * non-numeric values coerced to NaN and dropped
    * infinite values dropped
    * zero / negative prices dropped (garbage data)
    * DatetimeIndex sorted ascending (required for ``.iloc[-N]`` lookbacks)
    """
    s = pd.to_numeric(closes, errors="coerce")
    s = s.replace([float("inf"), float("-inf")], pd.NA).dropna()
    s = s[s > 0]
    if isinstance(s.index, pd.DatetimeIndex):
        s = s.sort_index()
    return s
