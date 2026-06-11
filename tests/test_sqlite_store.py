from pathlib import Path

import pandas as pd

from quant.storage.sqlite_store import SQLitePriceStore


def sample_prices(close: float = 101.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "date": "2024-01-02",
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": close,
                "adj_close": close,
                "volume": 123456,
            }
        ]
    )


def test_upsert_is_idempotent_by_symbol_and_date(tmp_path: Path) -> None:
    store = SQLitePriceStore(tmp_path / "quant.db")

    first_changes = store.upsert_prices(sample_prices())
    second_changes = store.upsert_prices(sample_prices())

    rows = store.get_prices("SPY")
    assert first_changes == 1
    assert second_changes == 1
    assert len(rows) == 1
    assert rows[0]["close"] == 101.0


def test_upsert_updates_existing_row(tmp_path: Path) -> None:
    store = SQLitePriceStore(tmp_path / "quant.db")

    store.upsert_prices(sample_prices(close=101.0))
    store.upsert_prices(sample_prices(close=105.0))

    rows = store.get_prices("SPY")
    assert len(rows) == 1
    assert rows[0]["close"] == 105.0

