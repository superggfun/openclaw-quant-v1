from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quant.agent_export.agent_exporter import AgentExporter
from quant.storage.sqlite_store import SQLitePriceStore
from quant.trading_simulation.portfolio_account import PortfolioAccount
from quant.trading_simulation.trading_simulator import TradingSimulator


def seed_trading_prices(db_path: Path) -> None:
    dates = pd.bdate_range("2023-08-01", "2024-06-28")
    symbols = {
        "SPY": (100.0, 0.10, 2.0),
        "QQQ": (120.0, 0.14, 3.0),
        "NVDA": (80.0, 0.26, 7.0),
        "AAPL": (150.0, 0.06, 4.0),
        "MSFT": (200.0, 0.08, 5.0),
        "TLT": (95.0, -0.01, 1.5),
    }
    rows = []
    for index, date in enumerate(dates):
        for symbol, (base, slope, wave) in symbols.items():
            close = base + slope * index + wave * ((index % 17) / 17)
            rows.append(
                {
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "open": close * 0.999,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1_000_000 + index,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def alpha_config() -> dict:
    return {
        "universe": ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "TLT"],
        "lookback_short": 20,
        "lookback_long": 60,
        "top_n": 4,
        "weighting_mode": "equal_weight",
        "min_cash_weight": 0.10,
        "max_position_weight": 0.30,
    }


def multiply_prices_after(db_path: Path, after_date: str, multiplier: float) -> None:
    store = SQLitePriceStore(db_path)
    rows = []
    for symbol in store.list_symbols():
        history = store.get_price_history(symbol, start=after_date)
        if history.empty:
            continue
        history = history[history["date"] > after_date].copy()
        for column in ("open", "high", "low", "close", "adj_close"):
            history[column] = history[column] * multiplier
        rows.append(history)
    if rows:
        store.upsert_prices(pd.concat(rows, ignore_index=True))


def test_account_initialization() -> None:
    account = PortfolioAccount(100000)

    assert account.cash == 100000
    assert account.positions == {}
    assert account.realized_pnl == 0


def test_mark_to_market() -> None:
    account = PortfolioAccount(100000)
    account.apply_trade("SPY", "BUY", 10, 100, 1, "2024-01-02")
    snapshot = account.mark_to_market("2024-01-03", {"SPY": 110})

    assert snapshot.market_value == 1100
    assert snapshot.total_equity == 100099
    assert snapshot.unrealized_pnl == 100


def test_buy_trade_updates_cash_and_position() -> None:
    account = PortfolioAccount(100000)
    trade = account.apply_trade("SPY", "BUY", 5, 100, 2, "2024-01-02")

    assert trade.cash_after == 99498
    assert account.positions["SPY"] == 5
    assert account.average_cost["SPY"] == 100


def test_sell_trade_updates_cash_and_position() -> None:
    account = PortfolioAccount(100000)
    account.apply_trade("SPY", "BUY", 10, 100, 1, "2024-01-02")
    trade = account.apply_trade("SPY", "SELL", 4, 110, 2, "2024-01-03")

    assert account.positions["SPY"] == 6
    assert trade.realized_pnl == 38
    assert trade.cash_after == 99437


def test_cost_reduces_cash() -> None:
    account = PortfolioAccount(1000)
    account.apply_trade("SPY", "BUY", 1, 100, 7, "2024-01-02")

    assert account.cash == 893
    assert account.cost_paid == 7


def test_account_rejects_invalid_trades_without_mutation() -> None:
    account = PortfolioAccount(1000)
    with pytest.raises(ValueError):
        account.apply_trade("SPY", "BUY", 20, 100, 1, "2024-01-02")
    with pytest.raises(ValueError):
        account.apply_trade("SPY", "SELL", 1, 100, 1, "2024-01-02")

    assert account.cash == 1000
    assert account.positions == {}
    assert account.trades == []


def test_monthly_rebalance_loop_generates_report(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    report_dir = tmp_path / "reports"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=report_dir).run(
        start="2024-01-02",
        end="2024-05-31",
        initial_cash=100000,
        rebalance_frequency="monthly",
        portfolio_method="equal_weight",
        alpha_config=alpha_config(),
    )

    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert report["metadata"]["report_type"] == "trade_sim"
    assert report["no_lookahead"] is True
    assert result.trade_count > 0
    assert len(result.rebalance_events) == 5
    assert Path(result.report_path).exists()


def test_weekly_rebalance_loop(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-03-29",
        initial_cash=100000,
        rebalance_frequency="weekly",
        portfolio_method="equal_weight",
        alpha_config=alpha_config(),
    )

    assert len(result.rebalance_events) == 13
    assert result.final_equity > 0


def test_final_equity_cost_and_turnover_reconcile(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-05-31",
        initial_cash=100000,
        rebalance_frequency="monthly",
        portfolio_method="equal_weight",
        alpha_config=alpha_config(),
    )
    last_positions = result.positions_by_date[-1]
    trade_cost_sum = round(sum(float(trade["cost"]) for trade in result.trades), 6)
    gross_trade_value = sum(float(trade["notional"]) for trade in result.trades)

    assert result.final_equity == last_positions["total_equity"]
    assert result.final_equity == pytest.approx(result.cash_curve[-1]["cash"] + last_positions["market_value"], abs=1e-6)
    assert result.total_cost == trade_cost_sum
    assert result.turnover == round(gross_trade_value / result.initial_cash, 6)


def test_risk_parity_portfolio_method_integration(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-04-30",
        rebalance_frequency="monthly",
        portfolio_method="risk_parity",
        alpha_config=alpha_config(),
    )

    assert result.portfolio_method == "risk_parity"
    assert result.rebalance_events[0]["target_weights"]["cash"] >= 0.10


def test_min_variance_portfolio_method_integration(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-04-30",
        rebalance_frequency="monthly",
        portfolio_method="min_variance",
        alpha_config=alpha_config(),
    )

    assert result.portfolio_method == "min_variance"
    assert result.final_equity > 0


def test_no_lookahead_signal_execution_date_separation(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-04-30",
        rebalance_frequency="monthly",
        portfolio_method="equal_weight",
        alpha_config=alpha_config(),
    )

    assert result.no_lookahead is True
    for event in result.rebalance_events:
        assert event["signal_date"] < event["execution_date"]
    for trade in result.trades:
        assert trade["signal_date"] < trade["execution_date"]


def test_future_price_changes_do_not_change_first_signal_or_trade(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    simulator = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    kwargs = {
        "start": "2024-01-02",
        "end": "2024-04-30",
        "rebalance_frequency": "monthly",
        "portfolio_method": "equal_weight",
        "alpha_config": alpha_config(),
    }
    first = simulator.run(**kwargs)
    first_event = first.rebalance_events[0]

    multiply_prices_after(db_path, first_event["execution_date"], 10.0)
    second = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(**kwargs)
    second_event = second.rebalance_events[0]

    assert second_event["signal_date"] == first_event["signal_date"]
    assert second_event["execution_date"] == first_event["execution_date"]
    assert second_event["selected_symbols"] == first_event["selected_symbols"]
    assert second_event["target_weights"] == first_event["target_weights"]
    assert second_event["executed_trades"] == first_event["executed_trades"]


def test_execution_price_matches_next_available_close(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    store = SQLitePriceStore(db_path)
    result = TradingSimulator(store, report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-03-29",
        rebalance_frequency="monthly",
        portfolio_method="equal_weight",
        alpha_config=alpha_config(),
    )
    first_trade = result.rebalance_events[0]["executed_trades"][0]
    history = store.get_price_history(first_trade["symbol"], start=first_trade["execution_date"], end=first_trade["execution_date"])

    assert first_trade["price"] == pytest.approx(float(history.iloc[0]["close"]))


def test_small_target_difference_does_not_churn_account(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    simulator = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    account = PortfolioAccount(2000)
    account.apply_trade("SPY", "BUY", 10, 100, 0, "2024-01-02")
    event = {
        "signal_date": "2024-01-02",
        "execution_date": "2024-01-03",
        "target_weights": {"SPY": 0.505, "cash": 0.495},
        "warnings": [],
    }

    result = simulator._execute_rebalance_event(account, event, {"SPY": 100}, {})

    assert result["executed_trades"] == []
    assert account.positions == {"SPY": 10}
    assert account.cash == 1000


def test_missing_execution_price_warns_without_corrupting_account(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    simulator = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    account = PortfolioAccount(2000)
    account.apply_trade("SPY", "BUY", 10, 100, 0, "2024-01-02")
    event = {
        "signal_date": "2024-01-02",
        "execution_date": "2024-01-03",
        "target_weights": {"cash": 1.0},
        "warnings": [],
    }

    result = simulator._execute_rebalance_event(account, event, {}, {})

    assert result["executed_trades"] == []
    assert result["warnings"] == ["WARN_NO_PRICE: missing execution price for SPY"]
    assert result["rejected_trades"][0]["execution_status"] == "SKIPPED_NO_PRICE"
    assert account.positions == {"SPY": 10}
    assert account.cash == 1000


def test_low_notional_cost_warning_is_reported(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    simulator = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    account = PortfolioAccount(1000)
    event = {
        "signal_date": "2024-01-02",
        "execution_date": "2024-01-03",
        "target_weights": {"SPY": 0.04, "cash": 0.96},
        "warnings": [],
    }

    result = simulator._execute_rebalance_event(
        account,
        event,
        {"SPY": 10},
        {"min_trade_notional": 50, "fixed_fee": 0, "commission_rate": 0, "min_commission": 0, "slippage_bps": 0},
    )

    assert len(result["executed_trades"]) == 1
    assert any("below min_trade_notional" in warning for warning in result["warnings"])


def test_trade_report_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-03-29",
        rebalance_frequency="monthly",
        portfolio_method="equal_weight",
        alpha_config=alpha_config(),
    )
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))

    for key in (
        "metadata",
        "parameters",
        "strategy",
        "portfolio_method",
        "initial_cash",
        "final_equity",
        "total_return",
        "annual_return",
        "volatility",
        "sharpe",
        "max_drawdown",
        "total_cost",
        "turnover",
        "trade_count",
        "equity_curve",
        "cash_curve",
        "positions_by_date",
        "trades",
        "rebalance_events",
        "warnings",
        "no_lookahead",
    ):
        assert key in report


def test_agent_export_support(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-03-29",
        rebalance_frequency="monthly",
        portfolio_method="equal_weight",
        alpha_config=alpha_config(),
    )
    exporter = AgentExporter()
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    export = exporter.export_report(report, generated_from=result.report_path)

    assert exporter.detect_report_type(report) == "trade_sim"
    assert export.report_type == "trade_sim"
    assert export.key_metrics["final_equity"] == result.final_equity


def test_deterministic_results(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trading_prices(db_path)
    simulator = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    kwargs = {
        "start": "2024-01-02",
        "end": "2024-04-30",
        "rebalance_frequency": "monthly",
        "portfolio_method": "equal_weight",
        "alpha_config": alpha_config(),
    }
    first = simulator.run(**kwargs)
    second = simulator.run(**kwargs)

    assert second.final_equity == first.final_equity
    assert second.trades == first.trades


def test_generated_reports_are_ignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "reports/*.json" in gitignore
