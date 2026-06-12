from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quant.agent_export.agent_exporter import AgentExporter
from quant.core_protocols import (
    AccountState,
    Fill,
    Order,
    PortfolioSnapshot,
    Position,
    Recommendation,
    Signal,
    TradeRecord,
)
from quant.core_protocols.protocol_validation import (
    reconcile_account,
    validate_fill_references_order,
    validate_signal_execution_dates,
    validate_weights,
)
from quant.storage.sqlite_store import SQLitePriceStore
from quant.trading_simulation.portfolio_account import PortfolioAccount
from quant.trading_simulation.trading_simulator import TradingSimulator


def test_account_validation_and_reconciliation() -> None:
    position = Position("SPY", 10, 100, 110, 1100, 100, 0.011, "2024-01-02")
    account = AccountState(
        account_id="acct-1",
        cash=98900,
        equity=100000,
        market_value=1100,
        realized_pnl=0,
        unrealized_pnl=100,
        cost_paid=1,
        timestamp="2024-01-02",
        positions=[position],
    )

    assert account.validate() == []
    assert reconcile_account(account) == []


def test_account_validation_rejects_bad_cash_and_reconciliation() -> None:
    account = AccountState(
        account_id="acct-1",
        cash=-1,
        equity=100,
        market_value=0,
        realized_pnl=0,
        unrealized_pnl=0,
        cost_paid=0,
        timestamp="2024-01-02",
    )

    errors = account.validate()
    assert "account cash must be non-negative" in errors
    assert any("reconciliation" in error for error in errors)


def test_position_validation() -> None:
    assert Position("SPY", 1, 100, 101, 101, 1, 0.5, "2024-01-02").validate() == []
    assert "position shares must be non-negative" in Position("SPY", -1, 100, 101, 101, 1, 0.5, "2024-01-02").validate()


def test_order_and_fill_lifecycle_validation() -> None:
    order = Order(
        order_id="order-1",
        symbol="SPY",
        side="BUY",
        quantity=5,
        target_weight=0.2,
        signal_date="2024-01-02",
        created_at="2024-01-02",
        status="PENDING",
        reason="rebalance",
    )
    submitted = Order.from_dict(order.to_dict() | {"status": "SUBMITTED"})
    filled = Order.from_dict(submitted.to_dict() | {"status": "FILLED"})
    fill = Fill("fill-1", filled.order_id, "SPY", "BUY", 5, 100, 1, "2024-01-03", "2024-01-02", "2024-01-03")

    assert submitted.validate() == []
    assert filled.validate() == []
    assert fill.validate() == []
    assert validate_fill_references_order(fill, [filled]) == []


def test_invalid_order_status_is_rejected() -> None:
    order = Order(
        order_id="order-1",
        symbol="SPY",
        side="BUY",
        quantity=5,
        target_weight=0.2,
        signal_date="2024-01-02",
        created_at="2024-01-02",
        status="UNKNOWN",
        reason="rebalance",
    )

    assert "order status is invalid" in order.validate()


def test_fill_references_missing_order_is_rejected() -> None:
    order = Order("order-1", "SPY", "BUY", 5, 0.2, "2024-01-02", "2024-01-02", "FILLED", "rebalance")
    fill = Fill("fill-1", "missing-order", "SPY", "BUY", 5, 100, 1, "2024-01-03", "2024-01-02", "2024-01-03")

    assert validate_fill_references_order(fill, [order]) == ["fill fill-1 references unknown order missing-order"]


def test_fill_rejects_bad_signal_execution_order() -> None:
    fill = Fill("fill-1", "order-1", "SPY", "BUY", 1, 100, 1, "2024-01-02", "2024-01-03", "2024-01-02")

    assert "fill signal_date must be on or before execution_date" in fill.validate()
    assert validate_signal_execution_dates("2024-01-03", "2024-01-02") == ["signal_date must be on or before execution_date"]


def test_signal_and_recommendation_serialization() -> None:
    signal = Signal("sig-1", "NVDA", 0.8, "2024-01-02", "alpha", 0.7, {"momentum": 0.8})
    recommendation = Recommendation("NVDA", "BUY", 0.2, 0.7, "high score", "2024-01-02")

    signal_roundtrip = Signal.from_dict(json.loads(json.dumps(signal.to_dict())))
    recommendation_roundtrip = Recommendation.from_dict(json.loads(json.dumps(recommendation.to_dict())))

    assert signal_roundtrip == signal
    assert recommendation_roundtrip == recommendation
    assert signal_roundtrip.validate() == []
    assert recommendation_roundtrip.validate() == []


def test_trade_record_json_roundtrip() -> None:
    trade = TradeRecord("SPY", "BUY", 10, 100, 1, "2024-01-02", "2024-01-03", "alpha", "equal_weight")

    restored = TradeRecord.from_dict(json.loads(json.dumps(trade.to_dict())))

    assert restored == trade
    assert restored.validate() == []


def test_portfolio_snapshot_weights_validation() -> None:
    snapshot = PortfolioSnapshot(
        date="2024-01-02",
        cash=100,
        equity=1000,
        positions=[Position("SPY", 9, 100, 100, 900, 0, 0.9, "2024-01-02")],
        weights={"cash": 0.1, "SPY": 0.9},
    )

    assert snapshot.validate() == []
    assert validate_weights(snapshot.weights) == []


def test_json_roundtrip_for_every_protocol_object() -> None:
    order = Order("order-1", "SPY", "BUY", 5, 0.2, "2024-01-02", "2024-01-02", "FILLED", "rebalance")
    fill = Fill("fill-1", "order-1", "SPY", "BUY", 5, 100, 1, "2024-01-03", "2024-01-02", "2024-01-03")
    position = Position("SPY", 5, 100, 101, 505, 5, 0.00505, "2024-01-03")
    account = AccountState("acct", 99495, 100000, 505, 0, 5, 1, "2024-01-03", [position], [order], [fill])
    signal = Signal("sig-1", "SPY", 0.7, "2024-01-02", "alpha", 0.8, {"momentum": 0.7})
    recommendation = Recommendation("SPY", "BUY", 0.2, 0.8, "alpha rank", "2024-01-02")
    trade = TradeRecord("SPY", "BUY", 5, 100, 1, "2024-01-02", "2024-01-03", "alpha", "equal_weight")
    snapshot = PortfolioSnapshot("2024-01-03", 99495, 100000, [position], {"cash": 0.99495, "SPY": 0.00505}, -0.01, 1, 1)

    objects = [order, fill, position, account, signal, recommendation, trade, snapshot]
    restored = [
        obj.__class__.from_dict(json.loads(json.dumps(obj.to_dict())))
        for obj in objects
    ]

    assert restored == objects
    assert all(obj.validate() == [] for obj in restored)


def test_portfolio_account_protocol_state_and_trade_conversion() -> None:
    account = PortfolioAccount(1000)
    trade = account.apply_trade("SPY", "BUY", 5, 100, 1, "2024-01-03", signal_date="2024-01-02", execution_date="2024-01-03")
    state = account.to_protocol_state("2024-01-03", {"SPY": 110}, account_id="acct")

    assert state.validate() == []
    assert state.cash == 499
    assert state.cost_paid == 1
    assert state.equity == pytest.approx(state.cash + state.market_value)
    assert state.positions[0].symbol == "SPY"
    assert state.positions[0].shares == 5
    assert state.positions[0].unrealized_pnl == 50
    trade_record = trade.to_protocol(strategy="alpha", portfolio_method="equal_weight")
    assert trade_record.signal_date == "2024-01-02"
    assert trade_record.execution_date == "2024-01-03"
    assert trade_record.validate() == []


def test_agent_export_accepts_protocol_object() -> None:
    position = Position("SPY", 1, 100, 100, 100, 0, 1, "2024-01-02")
    export = AgentExporter().export_protocol(position)

    assert export.report_type == "protocol_Position"
    assert export.key_metrics["symbol"] == "SPY"
    assert export.warnings == []


def seed_trade_sim_prices(db_path: Path) -> None:
    dates = pd.bdate_range("2023-10-02", "2024-03-29")
    rows = []
    for index, date in enumerate(dates):
        for symbol, base, drift in [("SPY", 100, 0.10), ("QQQ", 120, 0.14), ("NVDA", 80, 0.30), ("AAPL", 150, 0.05)]:
            close = base + drift * index + ((index % 5) * 0.1)
            rows.append(
                {
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1_000_000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_trade_simulation_integration_extends_report_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trade_sim_prices(db_path)
    result = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        start="2024-01-02",
        end="2024-03-29",
        initial_cash=100000,
        rebalance_frequency="monthly",
        portfolio_method="equal_weight",
        alpha_config={
            "universe": ["SPY", "QQQ", "NVDA", "AAPL"],
            "lookback_short": 20,
            "lookback_long": 40,
            "top_n": 3,
            "min_cash_weight": 0.10,
            "max_position_weight": 0.30,
        },
    )
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))

    assert result.trade_count > 0
    assert {
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
        "report_path",
    } <= set(report)
    assert "market_realism" in report
    assert "rejected_trades" in report
    assert report["metadata"]["report_type"] == "trade_sim"
    assert "protocol_orders" not in report
    assert "protocol_fills" not in report
    assert all("protocol validation" not in warning for warning in report["warnings"])
