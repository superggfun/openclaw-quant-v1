"""Fast vectorized price factor kernels (no registry / no SQLite / no I/O).

These functions are pure Pandas/NumPy computations that derive factor values
from a close-price history.  They are shared by both the SQLite-backed
``FactorMatrixBuilder`` and the in-memory ``InMemoryPriceMatrixProvider``,
breaking the reverse dependency where the in-memory path imported the builder.
"""

from __future__ import annotations

import pandas as pd


def price_factor_series(factor: str, history: pd.DataFrame) -> pd.Series | None:
    """Compute a price-derived factor as a full-length Series.

    ``history`` must contain a ``"close"`` column.
    Returns ``None`` for non-price factors (e.g. fundamental) so the caller
    can fall back to per-row computation.
    """
    closes = pd.to_numeric(history["close"], errors="coerce")
    returns = closes.pct_change()

    if factor == "momentum_20d":
        return (closes / closes.shift(20)) - 1.0
    if factor == "momentum_60d":
        return (closes / closes.shift(60)) - 1.0
    if factor == "volatility_20d":
        volatility = _rolling_std_exact(returns, 20)
        return volatility.where(volatility > 0)
    if factor == "risk_adjusted_momentum":
        momentum = (closes / closes.shift(60)) - 1.0
        volatility = _rolling_std_exact(returns, 20)
        return (momentum / volatility).where(volatility > 0)
    if factor == "reversal_5d":
        return -((closes / closes.shift(5)) - 1.0)
    if factor == "reversal_20d":
        return -((closes / closes.shift(20)) - 1.0)
    if factor == "low_volatility_score":
        volatility = _rolling_std_exact(returns, 20)
        return (-volatility).where(volatility > 0)
    return None


def _rolling_std_exact(values: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation (sample std, ddof=1 by default)."""
    return values.rolling(window).std()
