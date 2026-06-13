from datetime import date, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest

from quant.engines.backtest.backtest_engine import PortfolioBacktestEngine
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


def alpha_config(symbols: list[str]) -> dict:
    return {
        "universe": symbols,
        "lookback_short": 5,
        "lookback_long": 10,
        "top_n": len(symbols),
        "weighting_mode": "equal_weight",
        "min_cash_weight": 0.1,
        "max_position_weight": 0.5,
    }


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


def test_alpha_backtest_signal_date_precedes_execution_date(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"], days=90)
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.run(
        start="2024-01-01",
        end="2024-03-30",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        alpha_config=alpha_config(["SPY", "QQQ"]),
    )

    assert result.strategy == "alpha"
    assert result.no_lookahead is True
    assert result.signal_execution_lag == "next_trading_day"
    assert result.trades
    assert all(trade.signal_date < trade.execution_date for trade in result.trades)
    assert all(trade.signal_price is not None for trade in result.trades)
    assert all(trade.execution_price is not None for trade in result.trades)
    assert any(point["last_signal_date"] for point in result.equity_curve)
    assert any(point["last_execution_date"] for point in result.equity_curve)


def test_alpha_backtest_future_prices_do_not_change_existing_signal_trades(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"], days=65)
    store = SQLitePriceStore(db_path)
    engine = PortfolioBacktestEngine(store, report_dir=tmp_path / "reports")
    config = alpha_config(["SPY", "QQQ"])

    first = engine.run(
        start="2024-01-01",
        end="2024-02-03",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        alpha_config=config,
    )
    store.upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "SPY",
                    "date": "2024-02-03",
                    "open": 10000,
                    "high": 10000,
                    "low": 10000,
                    "close": 10000,
                    "adj_close": 10000,
                    "volume": 1000,
                }
            ]
        )
    )
    second = engine.run(
        start="2024-01-01",
        end="2024-02-03",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        alpha_config=config,
    )

    first_execution_date = first.trades[0].execution_date
    first_trades = [trade for trade in first.trades if trade.execution_date == first_execution_date]
    second_trades = [trade for trade in second.trades if trade.execution_date == first_execution_date]

    assert [(t.symbol, t.side, t.shares, t.signal_price, t.execution_price) for t in first_trades] == [
        (t.symbol, t.side, t.shares, t.signal_price, t.execution_price) for t in second_trades
    ]


def test_alpha_backtest_costs_reduce_final_value(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"], days=90)
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    config = alpha_config(["SPY", "QQQ"])

    no_cost = engine.run(
        start="2024-01-01",
        end="2024-03-30",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        alpha_config=config,
        cost_config={"model": "fixed", "fixed_fee": 0, "slippage_bps": 0},
    )
    with_cost = engine.run(
        start="2024-01-01",
        end="2024-03-30",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        alpha_config=config,
        cost_config={"model": "combined", "fixed_fee": 1, "commission_rate": 0.001, "slippage_bps": 5},
    )

    assert with_cost.metrics.total_cost > no_cost.metrics.total_cost
    assert with_cost.metrics.final_value < no_cost.metrics.final_value


def test_alpha_backtest_report_contains_no_lookahead_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"], days=90)
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.run(
        start="2024-01-01",
        end="2024-03-30",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        execution_price="close",
        alpha_config=alpha_config(["SPY", "QQQ"]),
    )
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))

    assert report["strategy"] == "alpha"
    assert report["no_lookahead"] is True
    assert report["signal_execution_lag"] == "next_trading_day"
    assert report["alpha_config"]["lookback_long"] == 10
    assert "excluded_symbols_per_rebalance" in report
    assert report["trades"][0]["signal_date"] < report["trades"][0]["execution_date"]
