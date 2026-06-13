"""Liquidity estimates from stored daily OHLCV history."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant.storage.sqlite_store import SQLitePriceStore


@dataclass(frozen=True)
class LiquiditySnapshot:
    symbol: str
    as_of_date: str
    lookback_days: int
    average_daily_volume: float | None
    average_daily_notional: float | None
    volatility: float | None
    observations: int
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of_date": self.as_of_date,
            "lookback_days": self.lookback_days,
            "average_daily_volume": self.average_daily_volume,
            "average_daily_notional": self.average_daily_notional,
            "volatility": self.volatility,
            "observations": self.observations,
            "warnings": self.warnings,
        }


class LiquidityModel:
    """Estimate ADV, notional liquidity, and volatility using historical daily bars."""

    def __init__(self, price_store: SQLitePriceStore, lookback_days: int = 20) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        self.price_store = price_store
        self.lookback_days = int(lookback_days)

    def snapshot(
        self,
        symbol: str,
        as_of_date: str,
        lookback_days: int | None = None,
        include_as_of: bool = False,
    ) -> LiquiditySnapshot:
        ticker = symbol.upper().strip()
        lookback = int(lookback_days or self.lookback_days)
        history = self.price_store.get_price_history(ticker, end=as_of_date)
        warnings: list[str] = []
        if history.empty:
            return LiquiditySnapshot(ticker, as_of_date, lookback, None, None, None, 0, ["WARN_NO_PRICE_HISTORY"])

        history = history.sort_values("date")
        if not include_as_of:
            history = history[history["date"] < as_of_date]
        window = history.tail(lookback).copy()
        if window.empty:
            return LiquiditySnapshot(ticker, as_of_date, lookback, None, None, None, 0, ["WARN_NO_PRIOR_LIQUIDITY_DATA"])

        volume = pd.to_numeric(window["volume"], errors="coerce")
        close = pd.to_numeric(window["close"], errors="coerce")
        valid = window[(volume > 0) & (close > 0)].copy()
        observations = int(len(valid))
        if observations < max(3, min(lookback, 10)):
            warnings.append("WARN_SHORT_LIQUIDITY_HISTORY")
        if valid.empty:
            return LiquiditySnapshot(ticker, as_of_date, lookback, None, None, None, 0, warnings + ["WARN_INVALID_LIQUIDITY_DATA"])

        valid_volume = pd.to_numeric(valid["volume"], errors="coerce")
        valid_close = pd.to_numeric(valid["close"], errors="coerce")
        adv = float(valid_volume.mean())
        daily_notional = float((valid_volume * valid_close).mean())
        returns = valid_close.pct_change().dropna()
        volatility = float(returns.std()) if len(returns) > 1 else None
        return LiquiditySnapshot(
            symbol=ticker,
            as_of_date=as_of_date,
            lookback_days=lookback,
            average_daily_volume=adv,
            average_daily_notional=daily_notional,
            volatility=volatility,
            observations=observations,
            warnings=warnings,
        )
