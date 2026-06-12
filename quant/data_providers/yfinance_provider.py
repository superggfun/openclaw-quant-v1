"""Yahoo Finance data provider."""

from __future__ import annotations

from datetime import date
import importlib
from typing import Iterable

import pandas as pd

from quant.data_providers.base import DataProvider, PRICE_COLUMNS, ProviderHealth

yf = None


class YFinanceProvider(DataProvider):
    name = "yfinance"
    description = "Yahoo Finance daily OHLCV via yfinance"
    status = "default"

    def get_price_history(
        self,
        symbol: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        ticker = symbol.upper().strip()
        if not ticker:
            raise ValueError("symbol must not be empty")

        yfinance = self._load_yfinance()
        raw = yfinance.download(
            ticker,
            start=start,
            end=end,
            interval="1d",
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False,
        )

        if raw.empty:
            return pd.DataFrame(columns=PRICE_COLUMNS)

        raw = self._flatten_single_ticker_columns(raw, ticker)
        frame = raw.reset_index()
        date_column = "Date" if "Date" in frame.columns else frame.columns[0]

        frame = frame.rename(
            columns={
                date_column: "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )

        if "adj_close" not in frame.columns:
            frame["adj_close"] = frame["close"]

        frame["symbol"] = ticker
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
        frame["volume"] = frame["volume"].fillna(0).astype("int64")

        for column in ("open", "high", "low", "close", "adj_close"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        return frame[PRICE_COLUMNS].dropna(subset=["open", "high", "low", "close"])

    def fetch_daily_prices(
        self,
        symbol: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        """Backward-compatible alias for older service tests and adapters."""
        return self.get_price_history(symbol, start=start, end=end)

    def health_check(self) -> ProviderHealth:
        try:
            self._load_yfinance(force_reload=True)
        except Exception as exc:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                status="NOT_INSTALLED",
                error=str(exc),
                messages=("yfinance import failed",),
            )
        return ProviderHealth(
            provider=self.name,
            healthy=True,
            status="PASS",
            messages=("yfinance package import succeeded", "network not probed during health check"),
        )

    @staticmethod
    def _load_yfinance(force_reload: bool = False):
        global yf
        if yf is not None and not force_reload:
            return yf
        try:
            yf = importlib.import_module("yfinance")
        except Exception as exc:
            raise RuntimeError("yfinance is not installed; install openclaw-quant[core] or add yfinance") from exc
        return yf

    @staticmethod
    def _flatten_single_ticker_columns(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if not isinstance(frame.columns, pd.MultiIndex):
            return frame

        for level in range(frame.columns.nlevels):
            if ticker in set(frame.columns.get_level_values(level)):
                return frame.xs(ticker, axis=1, level=level, drop_level=True)

        return frame.droplevel(list(range(1, frame.columns.nlevels)), axis=1)

    def fetch_many_daily_prices(
        self,
        symbols: Iterable[str],
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        frames = [self.get_price_history(symbol, start=start, end=end) for symbol in symbols]
        frames = [frame for frame in frames if not frame.empty]
        if not frames:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        return pd.concat(frames, ignore_index=True)
