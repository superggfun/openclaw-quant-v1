from pathlib import Path

import pandas as pd

from quant.services.price_service import PriceService
from quant.storage.sqlite_store import SQLitePriceStore


class FakeDataSource:
    def __init__(self) -> None:
        self.calls = []

    def fetch_daily_prices(self, symbol, start=None, end=None):
        self.calls.append((symbol, start, end))
        return pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "date": "2024-01-02",
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.0,
                    "adj_close": 101.0,
                    "volume": 123456,
                }
            ]
        )


def test_update_prices_uses_default_symbols_and_deduplicates(tmp_path: Path) -> None:
    source = FakeDataSource()
    service = PriceService(
        store=SQLitePriceStore(tmp_path / "quant.db"),
        data_source=source,
        default_symbols=("spy", "SPY", "qqq"),
    )

    result = service.update_prices()

    assert list(result) == ["SPY", "QQQ"]
    assert [call[0] for call in source.calls] == ["SPY", "QQQ"]


def test_incremental_update_starts_after_latest_stored_date(tmp_path: Path) -> None:
    source = FakeDataSource()
    store = SQLitePriceStore(tmp_path / "quant.db")
    service = PriceService(store=store, data_source=source, default_symbols=("SPY",))

    service.update_prices()
    service.update_prices()

    assert source.calls[1][1] == "2024-01-03"

