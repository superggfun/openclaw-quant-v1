from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.services.backtest_service import BacktestService
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, closes: list[float], symbol: str = "SPY") -> None:
    start = date(2024, 1, 1)
    rows = []
    for offset, close in enumerate(closes):
        day = start + timedelta(days=offset)
        rows.append(
            {
                "symbol": symbol,
                "date": day.isoformat(),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "adj_close": close,
                "volume": 1000,
            }
        )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def make_service(db_path: Path, report_dir: Path) -> BacktestService:
    return BacktestService(SQLitePriceStore(db_path), report_dir=report_dir)


def test_backtest_runs_to_completion(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, [10, 9, 8, 7, 6, 7, 8, 9, 10, 11, 12, 11, 10, 9, 8, 7, 6])
    service = make_service(db_path, tmp_path / "reports")

    result = service.run_sma_crossover(
        "SPY",
        start="2024-01-01",
        end="2024-01-31",
        short_window=3,
        long_window=5,
    )

    assert result.metrics.symbol == "SPY"
    assert result.metrics.initial_cash == 100000
    assert result.metrics.final_value > 0
    assert Path(result.report_path).exists()


def test_sma_crossovers_generate_trades(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, [10, 9, 8, 7, 6, 7, 8, 9, 10, 11, 12, 11, 10, 9, 8, 7, 6])
    service = make_service(db_path, tmp_path / "reports")

    result = service.run_sma_crossover(
        "SPY",
        start="2024-01-01",
        end="2024-01-31",
        short_window=3,
        long_window=5,
    )

    assert [trade.side for trade in result.trades] == ["BUY", "SELL"]
    assert result.metrics.number_of_trades == 2


def test_backtest_metrics_fields_are_complete(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, [10, 9, 8, 7, 6, 7, 8, 9, 10, 11, 12, 11, 10, 9, 8, 7, 6])
    service = make_service(db_path, tmp_path / "reports")

    result = service.run_sma_crossover(
        "SPY",
        start="2024-01-01",
        end="2024-01-31",
        short_window=3,
        long_window=5,
    )

    assert set(asdict(result.metrics)) == {
        "symbol",
        "start",
        "end",
        "initial_cash",
        "final_value",
        "total_return_pct",
        "max_drawdown_pct",
        "sharpe_ratio",
        "number_of_trades",
        "win_rate_pct",
    }


def test_backtest_no_data_has_clear_error(tmp_path: Path) -> None:
    service = make_service(tmp_path / "quant.db", tmp_path / "reports")

    with pytest.raises(ValueError, match="no price data found for SPY"):
        service.run_sma_crossover("SPY", start="2024-01-01", end="2024-01-31")


def test_backtest_rejects_invalid_windows(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, [10, 11, 12, 13, 14])
    service = make_service(db_path, tmp_path / "reports")

    with pytest.raises(ValueError, match="short_window must be less than long_window"):
        service.run_sma_crossover(
            "SPY",
            start="2024-01-01",
            end="2024-01-31",
            short_window=5,
            long_window=5,
        )

