"""Deterministic in-memory provider for tests."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant.data.layer.symbol_metadata import DEFAULT_SYMBOL_METADATA
from quant.data.providers.base import DataProvider, ProviderHealth, empty_price_frame, normalize_price_frame
from quant.data.providers.provider_specs import ProviderSpec


class MockProvider(DataProvider):
    name = "mock"
    description = "Deterministic in-memory provider for tests"
    status = "available"

    def __init__(self, frames: dict[str, pd.DataFrame] | None = None) -> None:
        self.frames = {symbol.upper(): frame.copy() for symbol, frame in (frames or {}).items()}

    def get_price_history(
        self,
        symbol: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        ticker = symbol.upper().strip()
        frame = self.frames.get(ticker)
        if frame is None:
            frame = self._default_frame(ticker)
        frame = normalize_price_frame(frame, symbol=ticker)
        if start:
            frame = frame[frame["date"] >= str(start)]
        if end:
            frame = frame[frame["date"] <= str(end)]
        return frame.sort_values("date").reset_index(drop=True)

    def get_symbol_metadata(self, symbol: str) -> dict | None:
        ticker = symbol.upper().strip()
        for row in DEFAULT_SYMBOL_METADATA:
            if row.symbol == ticker:
                return row.__dict__.copy()
        return {
            "symbol": ticker,
            "name": f"Mock {ticker}",
            "asset_type": "Equity",
            "sector": "Mock",
            "industry": "Mock",
            "currency": "USD",
            "exchange": "MOCK",
        }

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=True,
            status="PASS",
            messages=("mock provider ready",),
        )

    @staticmethod
    def _default_frame(symbol: str) -> pd.DataFrame:
        rows = []
        for index, date_value in enumerate(pd.bdate_range("2024-01-01", periods=30)):
            close = 100.0 + index
            rows.append(
                {
                    "symbol": symbol,
                    "date": date_value.strftime("%Y-%m-%d"),
                    "open": close - 0.5,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000 + index,
                }
            )
        return pd.DataFrame(rows) if rows else empty_price_frame()


PROVIDER_SPECS = (ProviderSpec("mock", MockProvider),)
