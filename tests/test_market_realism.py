from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.engines.execution.cost_engine import CostEngine, TradeInput
from quant.engines.execution.execution_constraints import ExecutionConstraints
from quant.engines.execution.liquidity_model import LiquidityModel
from quant.engines.execution.slippage_model import SlippageModel
from quant.storage.sqlite_store import SQLitePriceStore
from quant.engines.trading_simulation.portfolio_account import PortfolioAccount
from quant.engines.trading_simulation.trading_simulator import TradingSimulator


def seed_market_prices(db_path: Path, volume: int = 1000) -> None:
    rows = []
    for index, date in enumerate(pd.bdate_range("2023-10-02", "2024-03-29")):
        close = 100 + index * 0.1
        rows.append(
            {
                "symbol": "SPY",
                "date": date.strftime("%Y-%m-%d"),
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "adj_close": close,
                "volume": volume,
            }
        )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_adv_calculation(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_market_prices(db_path, volume=2000)

    snapshot = LiquidityModel(SQLitePriceStore(db_path), lookback_days=20).snapshot("SPY", "2024-01-31")

    assert snapshot.average_daily_volume == pytest.approx(2000)
    assert snapshot.average_daily_notional is not None
    assert snapshot.observations == 20


def test_slippage_models() -> None:
    assert SlippageModel({"model": "fixed", "fixed_amount": 3}).estimate(1000, 10, 100) == 3
    assert SlippageModel({"model": "bps", "bps": 10}).estimate(1000, 10, 100) == 1
    assert SlippageModel({"model": "volume_scaled", "volume_scaled_bps": 100}).estimate(1000, 10, 100, average_daily_volume=100) == 1
    assert SlippageModel({"model": "volatility_scaled", "volatility_multiplier": 0.5}).estimate(1000, 10, 100, volatility=0.02) == 10


def test_trade_cap_by_adv() -> None:
    result = ExecutionConstraints({"max_adv_participation": 0.05}).apply(
        "SPY",
        "BUY",
        requested_quantity=200,
        price=100,
        average_daily_volume=1000,
    )

    assert result.allowed is True
    assert result.adjusted_quantity == 50
    assert result.rejected_quantity == 150
    assert any("WARN_LIQUIDITY_CAP" in warning for warning in result.warnings)


def test_missing_price_handling() -> None:
    result = ExecutionConstraints({"max_adv_participation": 0.05}).apply(
        "SPY",
        "BUY",
        requested_quantity=10,
        price=None,
        average_daily_volume=1000,
    )

    assert result.allowed is False
    assert result.reason == "SKIPPED_NO_PRICE"
    assert result.adjusted_quantity == 0


def test_position_limit_caps_buy() -> None:
    result = ExecutionConstraints({"max_position_notional": 500}).apply(
        "SPY",
        "BUY",
        requested_quantity=10,
        price=100,
        average_daily_volume=10000,
        current_shares=3,
        current_equity=1000,
    )

    assert result.adjusted_quantity == 2
    assert result.rejected_quantity == 8
    assert any("WARN_POSITION_LIMIT" in warning for warning in result.warnings)


def test_cost_engine_market_realism_components(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "combined",
            "fixed_fee": 0,
            "commission_rate": 0,
            "min_commission": 0,
            "slippage_model": {"model": "bps", "bps": 10},
            "market_impact_bps": 5,
            "liquidity_impact_rate": 0.01,
        },
        report_dir=tmp_path / "reports",
    ).estimate([TradeInput("SPY", "BUY", 100, 10, average_daily_volume=1000)])

    trade = report.trades[0]
    assert trade.slippage_cost == pytest.approx(1.0)
    assert trade.market_impact_cost == pytest.approx(0.5)
    assert trade.liquidity_cost == pytest.approx(1.0)
    assert report.total_market_impact == pytest.approx(0.5)


def test_trade_sim_integration_caps_and_reports(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_market_prices(db_path, volume=1000)
    simulator = TradingSimulator(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    account = PortfolioAccount(100000)
    event = {
        "signal_date": "2024-01-02",
        "execution_date": "2024-01-03",
        "target_weights": {"SPY": 0.90, "cash": 0.10},
        "warnings": [],
    }

    result = simulator._execute_rebalance_event(
        account,
        event,
        {"SPY": 100},
        {
            "model": "combined",
            "fixed_fee": 0,
            "commission_rate": 0,
            "min_commission": 0,
            "slippage_model": {"model": "bps", "bps": 10},
            "market_realism": {"max_adv_participation": 0.05, "min_trade_notional": 50},
        },
    )

    assert result["executed_trades"][0]["executed_quantity"] == 50
    assert result["rejected_trades"][0]["rejected_quantity"] > 0
    assert "liquidity" in result
    assert any("WARN_LIQUIDITY_CAP" in warning for warning in result["warnings"])


def test_agent_export_includes_market_realism(tmp_path: Path) -> None:
    report_path = tmp_path / "trade_sim.json"
    report_path.write_text(
        json.dumps(
            {
                "metadata": {"report_type": "trade_sim"},
                "strategy": "alpha",
                "portfolio_method": "equal_weight",
                "initial_cash": 100000,
                "final_equity": 99000,
                "total_return": -0.01,
                "max_drawdown": -0.02,
                "total_cost": 50,
                "turnover": 0.5,
                "trade_count": 1,
                "rebalance_events": [],
                "rejected_trades": [{"symbol": "SPY", "rejected_quantity": 10}],
                "market_realism": {"total_slippage": 10, "total_market_impact": 5, "total_rejected_quantity": 10},
                "warnings": [],
                "no_lookahead": True,
                "equity_curve": [],
            }
        ),
        encoding="utf-8",
    )

    rendered = AgentExporter().export_file(report_path, output_format="json")
    payload = json.loads(rendered)

    assert payload["key_metrics"]["slippage"] == 10
    assert "WARN_LIQUIDITY_CAP" in payload["warnings"]
