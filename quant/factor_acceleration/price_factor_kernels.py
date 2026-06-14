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
    if factor == "growth_score":
        momentum_20d = (closes / closes.shift(20)) - 1.0
        momentum_60d = (closes / closes.shift(60)) - 1.0
        consistency = (closes.diff() > 0).rolling(20).mean()
        return 0.35 * momentum_20d + 0.45 * momentum_60d + 0.20 * consistency
    if factor == "value_score":
        long_return = (closes / closes.shift(120)) - 1.0
        volatility = _rolling_std_exact(returns, 60)
        return (-long_return / volatility).where(volatility > 0)
    if factor == "quality_score":
        return closes.rolling(61).apply(_quality_window_score, raw=True)
    return None


def _rolling_std_exact(values: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation (sample std, ddof=1 by default)."""
    return values.rolling(window).std()


def _quality_window_score(values) -> float:
    """Quality score for a single rolling window (raw numpy array).

    Equivalent to the original pandas Series version but avoids
    per-window Series object construction.
    """
    import numpy as _np

    arr = _np.asarray(values, dtype=_np.float64)
    returns = _np.diff(arr) / arr[:-1]
    returns = returns[_np.isfinite(returns)]
    if len(returns) < 60:
        return float("nan")
    vol = float(_np.std(returns, ddof=1))
    if vol <= 0 or _np.isnan(vol):
        return float("nan")
    pos_rate = float(_np.mean(returns > 0))
    cum = _np.cumprod(1.0 + returns)
    max_dd = float(_np.min(cum / _np.maximum.accumulate(cum) - 1.0))
    mean_ret = float(_np.mean(returns))
    return (mean_ret / vol) + pos_rate + max_dd
