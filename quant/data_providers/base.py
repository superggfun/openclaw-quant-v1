"""Base interfaces for market data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd

from quant.storage.sqlite_store import SQLitePriceStore


PRICE_COLUMNS = [
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
]


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    healthy: bool
    status: str
    warning: str | None = None
    error: str | None = None
    messages: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "healthy": self.healthy,
            "status": self.status,
            "warning": self.warning,
            "error": self.error,
            "messages": list(self.messages),
        }


class DataProvider(ABC):
    """Interface implemented by all price and metadata providers."""

    name = "base"
    description = "Abstract data provider"
    status = "abstract"

    @abstractmethod
    def get_price_history(
        self,
        symbol: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        """Return normalized daily OHLCV rows for one symbol."""

    def get_symbol_metadata(self, symbol: str) -> dict | None:
        """Return provider metadata when available."""
        return None

    def get_latest_price(self, symbol: str) -> float | None:
        history = self.get_price_history(symbol)
        if history.empty:
            return None
        closes = pd.to_numeric(history.sort_values("date")["close"], errors="coerce").dropna()
        return None if closes.empty else float(closes.iloc[-1])

    def refresh_symbol(
        self,
        symbol: str,
        price_store: SQLitePriceStore,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> int:
        prices = self.get_price_history(symbol, start=start, end=end)
        return price_store.upsert_prices(prices)

    def refresh_universe(
        self,
        symbols: Iterable[str],
        price_store: SQLitePriceStore,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> dict[str, int]:
        return {
            symbol.upper().strip(): self.refresh_symbol(symbol, price_store, start=start, end=end)
            for symbol in symbols
            if symbol and symbol.strip()
        }

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=True,
            status="PASS",
            messages=(self.description,),
        )


class PlaceholderProvider(DataProvider):
    """Registered marker for future providers that are not implemented yet."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self.status = "not installed"

    def get_price_history(
        self,
        symbol: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} provider is not installed")

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=False,
            status="NOT_INSTALLED",
            warning="provider placeholder only",
            messages=(self.description,),
        )


def empty_price_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=PRICE_COLUMNS)


def normalize_price_frame(frame: pd.DataFrame, symbol: str | None = None) -> pd.DataFrame:
    """Normalize a provider frame to the repository OHLCV schema."""
    if frame.empty:
        return empty_price_frame()
    output = frame.copy()
    output.columns = [str(column).strip() for column in output.columns]
    rename = {
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Adj_Close": "adj_close",
        "Volume": "volume",
        "Symbol": "symbol",
    }
    output = output.rename(columns=rename)
    if symbol and "symbol" not in output.columns:
        output["symbol"] = symbol.upper().strip()
    if "adj_close" not in output.columns and "close" in output.columns:
        output["adj_close"] = output["close"]
    if "volume" not in output.columns:
        output["volume"] = 0
    missing = [column for column in PRICE_COLUMNS if column not in output.columns]
    if missing:
        raise ValueError(f"price frame missing required columns: {', '.join(missing)}")
    output["symbol"] = output["symbol"].astype(str).str.upper().str.strip()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    for column in ("open", "high", "low", "close", "adj_close"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    output["volume"] = pd.to_numeric(output["volume"], errors="coerce").fillna(0).astype("int64")
    return output[PRICE_COLUMNS].dropna(subset=["open", "high", "low", "close"])
