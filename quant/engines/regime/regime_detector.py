"""No-lookahead market regime detector."""

from __future__ import annotations

import math

import pandas as pd

from quant.engines.regime.market_regime import RegimeObservation
from quant.engines.regime.regime_classification import classify_regime
from quant.storage.sqlite_store import SQLitePriceStore


class RegimeDetector:
    """Classify market regimes from stored daily prices using deterministic rules."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        benchmark: str = "SPY",
        long_window: int = 200,
        volatility_window: int = 20,
        trend_window: int = 60,
    ) -> None:
        if long_window < 20:
            raise ValueError("long_window must be >= 20")
        if volatility_window < 5:
            raise ValueError("volatility_window must be >= 5")
        if trend_window < 1:
            raise ValueError("trend_window must be >= 1")
        self.price_store = price_store
        self.benchmark = benchmark.upper()
        self.long_window = long_window
        self.volatility_window = volatility_window
        self.trend_window = trend_window

    def detect(self, start: str | None = None, end: str | None = None) -> list[RegimeObservation]:
        history = self.price_store.get_price_history(self.benchmark, start=None, end=end)
        if history.empty:
            raise ValueError(f"no price history found for benchmark {self.benchmark}")
        history = history.sort_values("date").reset_index(drop=True)
        closes = history["close"].astype(float)
        returns = closes.pct_change()
        rolling_vol = returns.rolling(self.volatility_window, min_periods=max(5, self.volatility_window // 2)).std() * math.sqrt(252)
        moving_average = closes.rolling(self.long_window, min_periods=max(20, min(self.long_window, len(closes)) // 2)).mean()
        trend = closes.pct_change(self.trend_window)
        market_return = returns
        rolling_peak = closes.cummax()
        drawdown = closes / rolling_peak - 1.0

        observations = []
        for index, row in history.iterrows():
            date = str(row["date"])
            if start and date < start:
                continue
            close = self._num(closes.iloc[index])
            ma = self._num(moving_average.iloc[index])
            vol = self._num(rolling_vol.iloc[index])
            trend_strength = self._num(trend.iloc[index])
            dd = self._num(drawdown.iloc[index])
            ret = self._num(market_return.iloc[index])
            regime, confidence = classify_regime(
                close=close,
                moving_average=ma,
                volatility=vol,
                trend_strength=trend_strength,
                drawdown=dd,
                market_return=ret,
            )
            observations.append(
                RegimeObservation(
                    date=date,
                    regime=regime,
                    volatility=vol,
                    trend_strength=trend_strength,
                    drawdown=dd,
                    market_return=ret,
                    confidence=confidence,
                )
            )
        return observations

    @staticmethod
    def _num(value) -> float | None:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None
