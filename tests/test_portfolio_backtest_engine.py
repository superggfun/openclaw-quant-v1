from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.backtest.backtest_engine import PortfolioBacktestEngine
from quant.storage.sqlite_store import SQLitePriceStore


def seed_price_series(db_path: Path, symbols: list[str], days: int = 45) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        for offset in range(days):
            close = 100 + symbol_index * 10 + offset * (1 + symbol_index * 0.2)
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_portfolio_backtest_runs_to_completion(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"])
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.run(
        start="2024-01-01",
        end="2024-02-15",
        initial_cash=100000,
        mode="equal_weight",
        rebalance_frequency="monthly",
        symbols=["SPY", "QQQ"],
    )

    assert result.metrics.final_value > 0
    assert result.metrics.trade_count > 0
    assert Path(result.report_path).exists()


def test_portfolio_backtest_metrics_are_complete(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"])
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.run(
        start="2024-01-01",
        end="2024-02-15",
        initial_cash=100000,
        mode="risk_adjusted",
        rebalance_frequency="weekly",
        symbols=["SPY", "QQQ"],
    )

    assert set(result.metrics.__dataclass_fields__) == {
        "final_value",
        "total_return",
        "annual_return",
        "max_drawdown",
        "volatility",
        "sharpe_ratio",
        "trade_count",
        "turnover",
        "total_cost",
        "cash_ratio",
    }


def test_portfolio_backtest_includes_costs(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"])
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.run(
        start="2024-01-01",
        end="2024-02-15",
        initial_cash=100000,
        mode="equal_weight",
        rebalance_frequency="monthly",
        symbols=["SPY", "QQQ"],
        cost_config={"model": "combined", "fixed_fee": 1, "commission_rate": 0.001},
    )

    assert result.metrics.total_cost > 0
    assert all(trade.total_cost > 0 for trade in result.trades)


def test_portfolio_backtest_is_reproducible(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"])
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    first = engine.run(
        start="2024-01-01",
        end="2024-02-15",
        initial_cash=100000,
        mode="constrained",
        rebalance_frequency="daily",
        symbols=["SPY", "QQQ"],
    )
    second = engine.run(
        start="2024-01-01",
        end="2024-02-15",
        initial_cash=100000,
        mode="constrained",
        rebalance_frequency="daily",
        symbols=["SPY", "QQQ"],
    )

    assert first.metrics == second.metrics
    assert first.trades == second.trades


def test_portfolio_backtest_no_data_has_clear_error(tmp_path: Path) -> None:
    engine = PortfolioBacktestEngine(SQLitePriceStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports")

    with pytest.raises(ValueError, match="no price data found for backtest universe"):
        engine.run(
            start="2024-01-01",
            end="2024-02-15",
            initial_cash=100000,
            symbols=["SPY"],
        )

