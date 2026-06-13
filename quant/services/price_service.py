"""Price data orchestration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from quant.config import DEFAULT_START_DATE, DEFAULT_SYMBOLS
from quant.core.symbols import normalize_symbols
from quant.data.providers import DataProvider, YFinanceProvider
from quant.storage.sqlite_store import SQLitePriceStore


class PriceService:
    """Coordinate market data downloads and persistence."""

    def __init__(
        self,
        store: SQLitePriceStore,
        data_source: DataProvider | None = None,
        default_symbols: Iterable[str] = DEFAULT_SYMBOLS,
    ) -> None:
        self.store = store
        self.data_provider = data_source or YFinanceProvider()
        self.data_source = self.data_provider
        self.default_symbols = tuple(symbol.upper() for symbol in default_symbols)

    def update_prices(
        self,
        symbols: Iterable[str] | None = None,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> dict[str, int]:
        normalized_symbols = self._normalize_symbols(symbols or self.default_symbols)
        results: dict[str, int] = {}

        for symbol in normalized_symbols:
            fetch_start = self._resolve_start_date(symbol, start)
            prices = self._get_price_history(symbol, start=fetch_start, end=end)
            results[symbol] = self.store.upsert_prices(prices)

        return results

    def show_prices(self, symbol: str, limit: int = 10) -> list[dict]:
        return self.store.get_prices(symbol=symbol, limit=limit)

    def list_symbols(self, include_defaults: bool = True) -> list[str]:
        stored_symbols = set(self.store.list_symbols())
        if include_defaults:
            stored_symbols.update(self.default_symbols)
        return sorted(stored_symbols)

    def _resolve_start_date(self, symbol: str, requested_start: str | date | None) -> str | date:
        if requested_start:
            return requested_start

        latest = self.store.latest_date(symbol)
        if not latest:
            return DEFAULT_START_DATE

        next_day = datetime.strptime(latest, "%Y-%m-%d").date() + timedelta(days=1)
        return next_day.isoformat()

    @staticmethod
    def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
        return normalize_symbols(symbols)

    def _get_price_history(
        self,
        symbol: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ):
        if hasattr(self.data_provider, "get_price_history"):
            return self.data_provider.get_price_history(symbol, start=start, end=end)
        return self.data_provider.fetch_daily_prices(symbol, start=start, end=end)
