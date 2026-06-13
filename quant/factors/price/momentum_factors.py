"""Momentum and volatility price-history factors."""

from __future__ import annotations

import pandas as pd

from quant.factors.specs import price_factor_spec


def _clean_closes(closes: pd.Series) -> pd.Series:
    return pd.to_numeric(closes, errors="coerce").dropna()


def momentum_20d(closes: pd.Series) -> float | None:
    closes = _clean_closes(closes)
    if len(closes) <= 20:
        return None
    return float((closes.iloc[-1] / closes.iloc[-21]) - 1.0)


def momentum_60d(closes: pd.Series) -> float | None:
    closes = _clean_closes(closes)
    if len(closes) <= 60:
        return None
    return float((closes.iloc[-1] / closes.iloc[-61]) - 1.0)


def volatility_20d(closes: pd.Series) -> float | None:
    closes = _clean_closes(closes)
    returns = closes.pct_change().dropna().tail(20)
    if len(returns) < 20:
        return None
    volatility = float(returns.std())
    return volatility if volatility > 0 else None


def risk_adjusted_momentum(closes: pd.Series) -> float | None:
    momentum = momentum_60d(closes)
    volatility = volatility_20d(closes)
    if momentum is None or volatility is None or volatility <= 0:
        return None
    return momentum / volatility


FACTOR_SPECS = (
    price_factor_spec("momentum_20d", "momentum", "20-day close-to-close price momentum.", 20, "price_momentum", momentum_20d),
    price_factor_spec("momentum_60d", "momentum", "60-day close-to-close price momentum.", 60, "price_momentum", momentum_60d),
    price_factor_spec("volatility_20d", "risk", "20-day realized close-to-close volatility.", 20, "realized_volatility", volatility_20d, higher_is_better=False),
    price_factor_spec("risk_adjusted_momentum", "momentum", "60-day momentum divided by 20-day realized volatility.", 60, "risk_adjusted_price_momentum", risk_adjusted_momentum),
)
