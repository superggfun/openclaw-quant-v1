"""Bulk price loading helpers for acceleration paths."""

from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

from quant.storage.sqlite_store import SQLitePriceStore


@dataclass(frozen=True)
class BulkPriceLoadResult:
    histories: dict[str, pd.DataFrame]
    read_seconds: float


class BulkPriceLoader:
    """Load many symbol histories through one store call where available."""

    def __init__(self, price_store: SQLitePriceStore) -> None:
        self.price_store = price_store

    def load(
        self,
        symbols: list[str],
        start: str | None = None,
        end: str | None = None,
    ) -> BulkPriceLoadResult:
        started = time.monotonic()
        if hasattr(self.price_store, "get_price_history_many"):
            histories = self.price_store.get_price_history_many(symbols, start=start, end=end)
        else:
            histories = {
                symbol: self.price_store.get_price_history(symbol, start=start, end=end)
                for symbol in symbols
            }
        return BulkPriceLoadResult(histories=histories, read_seconds=time.monotonic() - started)
