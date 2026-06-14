from datetime import date, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest

from quant.engines.backtest.backtest_engine import PortfolioBacktestEngine
from quant.engines.execution.cost_engine import CostEngine
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


class BulkOnlyPriceStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.bulk_calls = 0

    def get_price_history_many(self, symbols: list[str], start: str | None = None, end: str | None = None):
        self.bulk_calls += 1
        rows = {}
        for index, symbol in enumerate(symbols):
            rows[symbol.upper()] = pd.DataFrame(
                [
                    {
                        "symbol": symbol.upper(),
                        "date": "2024-01-01",
                        "open": 100.0 + index,
                        "high": 100.0 + index,
                        "low": 100.0 + index,
                        "close": 100.0 + index,
                        "adj_close": 100.0 + index,
                        "volume": 1000,
                    },
                    {
                        "symbol": symbol.upper(),
                        "date": "2024-01-02",
                        "open": 101.0 + index,
                        "high": 101.0 + index,
                        "low": 101.0 + index,
                        "close": 101.0 + index,
                        "adj_close": 101.0 + index,
                        "volume": 1000,
                    },
                ]
            )
        return rows

    def get_price_history(self, *args, **kwargs):
        raise AssertionError("expected bulk price history path")


def test_portfolio_backtest_loaders_use_bulk_price_history(tmp_path: Path) -> None:
    store = BulkOnlyPriceStore(tmp_path / "quant.db")
    engine = PortfolioBacktestEngine(store, report_dir=tmp_path / "reports")

    frame = engine._load_price_frame(["SPY", "QQQ"], "2024-01-01", "2024-01-02")

    assert list(frame.columns) == ["SPY", "QQQ"]
    assert frame.loc[pd.Timestamp("2024-01-02"), "QQQ"] == 102.0
    assert store.bulk_calls == 1


def test_portfolio_backtest_execution_prices_are_not_ffilled(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    rows = [
        {
            "symbol": "SPY",
            "date": "2024-01-01",
            "open": 100,
            "high": 100,
            "low": 100,
            "close": 100,
            "adj_close": 100,
            "volume": 1000,
        },
        {
            "symbol": "SPY",
            "date": "2024-01-02",
            "open": 101,
            "high": 101,
            "low": 101,
            "close": 101,
            "adj_close": 101,
            "volume": 1000,
        },
        {
            "symbol": "QQQ",
            "date": "2024-01-01",
            "open": 200,
            "high": 200,
            "low": 200,
            "close": 200,
            "adj_close": 200,
            "volume": 1000,
        },
    ]
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    mark = engine._load_price_frame(["SPY", "QQQ"], "2024-01-01", "2024-01-02")
    execution = engine._load_execution_price_frame(["SPY", "QQQ"], "2024-01-01", "2024-01-02", "close")

    assert mark.loc[pd.Timestamp("2024-01-02"), "QQQ"] == 200
    assert pd.isna(execution.loc[pd.Timestamp("2024-01-02"), "QQQ"])


def test_portfolio_backtest_rebalance_skips_non_tradable_execution_price(tmp_path: Path) -> None:
    engine = PortfolioBacktestEngine(SQLitePriceStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports")
    warnings: list[dict] = []

    trades, cash, positions = engine._rebalance_with_prices(
        trade_date="2024-01-02",
        cash=1000,
        positions={"SPY": 0},
        valuation_prices={"SPY": 100},
        execution_prices={},
        target_weights={"SPY": 1.0, "cash": 0.0},
        cost_engine=CostEngine({"fixed_fee": 0, "commission_rate": 0, "min_commission": 0, "slippage_bps": 0}),
        warnings=warnings,
    )

    assert trades == []
    assert cash == 1000
    assert positions == {"SPY": 0}
    assert warnings == [
        {
            "code": "NOT_TRADABLE_ON_EXECUTION_DATE",
            "symbol": "SPY",
            "execution_date": "2024-01-02",
            "reason": "SPY has no real execution price on 2024-01-02; ffilled mark price was not used for trading.",
        }
    ]


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
        allow_same_day_close_simple_mode=True,
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
        allow_same_day_close_simple_mode=True,
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
        allow_same_day_close_simple_mode=True,
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
        allow_same_day_close_simple_mode=True,
    )
    second = engine.run(
        start="2024-01-01",
        end="2024-02-15",
        initial_cash=100000,
        mode="constrained",
        rebalance_frequency="daily",
        symbols=["SPY", "QQQ"],
        allow_same_day_close_simple_mode=True,
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
            allow_same_day_close_simple_mode=True,
        )


def test_portfolio_simple_mode_is_disabled_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"])
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    with pytest.raises(ValueError, match="disabled by default"):
        engine.run(
            start="2024-01-01",
            end="2024-02-15",
            initial_cash=100000,
            mode="equal_weight",
            rebalance_frequency="monthly",
            symbols=["SPY", "QQQ"],
        )


def test_portfolio_simple_mode_report_is_marked_research_only(tmp_path: Path) -> None:
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
        allow_same_day_close_simple_mode=True,
    )
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))

    assert report["no_lookahead"] is False
    assert report["signal_execution_lag"] == "same_day_close_simple_mode"
    assert report["tradability_label"] == "Research-only, same-day-close, not tradable."
    assert report["warnings"] == [
        {
            "code": "RESEARCH_ONLY_SAME_DAY_CLOSE",
            "reason": "Research-only, same-day-close, not tradable.",
        }
    ]


def test_portfolio_simple_mode_rejects_non_close_execution_price(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"])
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    with pytest.raises(ValueError, match="portfolio simple mode only supports close execution"):
        engine.run(
            start="2024-01-01",
            end="2024-02-15",
            initial_cash=100000,
            mode="equal_weight",
            rebalance_frequency="monthly",
            symbols=["SPY", "QQQ"],
            execution_price="open",
            allow_same_day_close_simple_mode=True,
        )


def test_portfolio_constraints_validate_ranges(tmp_path: Path) -> None:
    engine = PortfolioBacktestEngine(SQLitePriceStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports")

    with pytest.raises(ValueError, match="max_position_weight must be between 0 and 1"):
        engine._normalize_constraints({"max_position_weight": -0.1})
    with pytest.raises(ValueError, match="min_cash_weight must be between 0 and 1"):
        engine._normalize_constraints({"min_cash_weight": 1.2})
    with pytest.raises(ValueError, match="max_sector_weight must be between 0 and 1"):
        engine._normalize_constraints({"max_sector_weight": 2.0})
    with pytest.raises(ValueError, match="max_position_weight must be positive"):
        engine._normalize_constraints({"max_position_weight": 0.0})


def test_unknown_industry_symbols_are_not_sector_capped(tmp_path: Path) -> None:
    engine = PortfolioBacktestEngine(SQLitePriceStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports", industry_map={})
    warnings: list[dict] = []

    targets = engine._apply_constraints(
        {"AAA": 0.6, "BBB": 0.4},
        {"max_position_weight": 1.0, "min_cash_weight": 0.0, "max_sector_weight": 0.1},
        warnings=warnings,
    )

    assert targets["AAA"] == pytest.approx(0.6)
    assert targets["BBB"] == pytest.approx(0.4)
    assert targets["cash"] == pytest.approx(0.0)
    assert warnings == [
        {
            "code": "UNKNOWN_INDUSTRY_SYMBOLS",
            "symbols": ["AAA", "BBB"],
            "reason": "Symbols with unknown industry were excluded from sector cap grouping.",
        }
    ]


def test_risk_adjusted_first_rebalance_warns_when_history_is_insufficient(tmp_path: Path) -> None:
    engine = PortfolioBacktestEngine(SQLitePriceStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports")
    warnings: list[dict] = []
    price_frame = pd.DataFrame(
        {"SPY": [100.0], "QQQ": [200.0]},
        index=pd.to_datetime(["2024-01-01"]),
    )

    targets = engine._target_weights(
        mode="risk_adjusted",
        symbols=["SPY", "QQQ"],
        price_frame=price_frame,
        constraints={"max_position_weight": 1.0, "min_cash_weight": 0.0, "max_sector_weight": 1.0},
        warnings=warnings,
        date_text="2024-01-01",
    )

    assert targets["SPY"] == pytest.approx(0.5)
    assert targets["QQQ"] == pytest.approx(0.5)
    assert any(warning["code"] == "RISK_ADJUSTED_INSUFFICIENT_HISTORY" for warning in warnings)


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


def test_alpha_backtest_symbols_parameter_sets_universe_when_config_has_none(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["AAPL", "MSFT", "SPY"], days=90)
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    config = alpha_config(["SPY"])
    config.pop("universe")

    result = engine.run(
        start="2024-01-01",
        end="2024-03-30",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        symbols=["AAPL", "MSFT"],
        alpha_config=config,
    )

    assert result.alpha_config["universe"] == ["AAPL", "MSFT"]
    assert result.effective_universe == ["AAPL", "MSFT"]
    assert {trade.symbol for trade in result.trades} <= {"AAPL", "MSFT"}


def test_alpha_backtest_rejects_symbols_and_alpha_config_universe_conflict(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["AAPL", "MSFT"], days=90)
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    with pytest.raises(ValueError, match="Pass universe either via symbols"):
        engine.run(
            start="2024-01-01",
            end="2024-03-30",
            initial_cash=100000,
            rebalance_frequency="monthly",
            strategy="alpha",
            symbols=["AAPL"],
            alpha_config=alpha_config(["MSFT"]),
        )


def test_alpha_generation_failure_raises_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"], days=90)
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    config = alpha_config(["SPY", "QQQ"])
    config["factor_weights"] = {"not_a_factor": 1.0}

    with pytest.raises(ValueError, match="alpha generation failed"):
        engine.run(
            start="2024-01-01",
            end="2024-03-30",
            initial_cash=100000,
            rebalance_frequency="monthly",
            strategy="alpha",
            alpha_config=config,
        )


def test_alpha_generation_failure_can_be_allowed_with_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"], days=90)
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    config = alpha_config(["SPY", "QQQ"])
    config["factor_weights"] = {"not_a_factor": 1.0}

    result = engine.run(
        start="2024-01-01",
        end="2024-03-30",
        initial_cash=100000,
        rebalance_frequency="monthly",
        strategy="alpha",
        alpha_config=config,
        allow_alpha_failures=True,
    )

    assert result.trades == []
    assert any(warning["code"] == "ALPHA_GENERATION_FAILED" for warning in result.warnings)


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
    assert report["execution_price"] == "close"
    assert report["price_column"] == "close"
    assert report["effective_universe"] == ["SPY", "QQQ"]
    assert report["alpha_pipeline_config"] is None
    assert "excluded_symbols_per_rebalance" in report
    assert report["trades"][0]["signal_date"] < report["trades"][0]["execution_date"]


def test_stale_mark_price_warning_when_close_is_ffilled_too_long(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    rows = []
    for offset in range(8):
        rows.append(
            {
                "symbol": "SPY",
                "date": (date(2024, 1, 1) + timedelta(days=offset)).isoformat(),
                "open": 100 + offset,
                "high": 100 + offset,
                "low": 100 + offset,
                "close": 100 + offset,
                "adj_close": 100 + offset,
                "volume": 1000,
            }
        )
    rows.append(
        {
            "symbol": "QQQ",
            "date": "2024-01-01",
            "open": 200,
            "high": 200,
            "low": 200,
            "close": 200,
            "adj_close": 200,
            "volume": 1000,
        }
    )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))
    engine = PortfolioBacktestEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.run(
        start="2024-01-01",
        end="2024-01-08",
        initial_cash=100000,
        mode="equal_weight",
        rebalance_frequency="daily",
        symbols=["SPY", "QQQ"],
        allow_same_day_close_simple_mode=True,
    )

    stale = [warning for warning in result.warnings if warning["code"] == "STALE_MARK_PRICE"]
    assert stale
    assert stale[0]["symbol"] == "QQQ"
    assert stale[0]["days_stale"] == 6
