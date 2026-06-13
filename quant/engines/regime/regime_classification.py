"""Deterministic regime classification rules."""

from __future__ import annotations

from quant.engines.regime.market_regime import MarketRegime


def classify_regime(
    *,
    close: float | None,
    moving_average: float | None,
    volatility: float | None,
    trend_strength: float | None,
    drawdown: float | None,
    market_return: float | None,
    high_vol_threshold: float = 0.25,
    low_vol_threshold: float = 0.12,
    crisis_drawdown: float = -0.20,
    recovery_drawdown: float = -0.10,
    trend_threshold: float = 0.05,
) -> tuple[str, float]:
    """Classify one date using only metrics available as of that date."""
    if close is None or moving_average is None or volatility is None or trend_strength is None or drawdown is None:
        return MarketRegime.UNKNOWN, 0.0

    confidence = min(
        1.0,
        0.35 + abs(trend_strength) * 2.0 + abs(drawdown) + min(max(volatility, 0.0), 1.0) * 0.35,
    )
    if drawdown <= crisis_drawdown and (volatility >= high_vol_threshold or (market_return or 0.0) <= -0.08):
        return MarketRegime.CRISIS, round(confidence, 6)
    if drawdown <= recovery_drawdown and trend_strength > trend_threshold and (market_return or 0.0) > 0:
        return MarketRegime.RECOVERY, round(confidence, 6)
    if volatility >= high_vol_threshold:
        return MarketRegime.HIGH_VOL, round(confidence, 6)
    if volatility <= low_vol_threshold and abs(trend_strength) < trend_threshold:
        return MarketRegime.LOW_VOL, round(confidence, 6)
    if close > moving_average and trend_strength > 0:
        return MarketRegime.BULL, round(confidence, 6)
    if close < moving_average and trend_strength < 0:
        return MarketRegime.BEAR, round(confidence, 6)
    if abs(trend_strength) >= trend_threshold:
        return MarketRegime.TRENDING, round(confidence, 6)
    return MarketRegime.RANGE_BOUND, round(max(confidence, 0.35), 6)
