import json
from pathlib import Path

import pandas as pd
import pytest

from quant.cli import main
from quant.engines.execution.cost_engine import CostEngine, TradeInput, apply_cost_profile
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


def test_fixed_cost_is_calculated(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "fixed",
            "fixed_fee": 2,
            "slippage_bps": 0,
        },
        report_dir=tmp_path / "reports",
    ).estimate([TradeInput("SPY", "BUY", 10, 100)])

    assert report.trades[0].fixed_fee == 2
    assert report.trades[0].commission == 0
    assert report.trades[0].total_cost == 2
    assert Path(report.report_path).exists()


def test_linear_cost_is_calculated(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "linear",
            "commission_rate": 0.002,
            "min_commission": 1,
            "slippage_bps": 0,
        },
        report_dir=tmp_path / "reports",
    ).estimate([TradeInput("SPY", "BUY", 10, 100)])

    assert report.trades[0].fixed_fee == 0
    assert report.trades[0].commission == 2
    assert report.trades[0].total_cost == 2


def test_combined_cost_is_calculated(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "combined",
            "fixed_fee": 1,
            "commission_rate": 0.002,
            "min_commission": 1,
            "slippage_bps": 0,
        },
        report_dir=tmp_path / "reports",
    ).estimate([TradeInput("SPY", "BUY", 10, 100)])

    assert report.trades[0].fixed_fee == 1
    assert report.trades[0].commission == 2
    assert report.trades[0].total_cost == 3


def test_slippage_bps_is_calculated(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "fixed",
            "fixed_fee": 0,
            "slippage_bps": 5,
        },
        report_dir=tmp_path / "reports",
    ).estimate([TradeInput("SPY", "BUY", 10, 100)])

    assert report.trades[0].slippage_cost == 0.5
    assert report.trades[0].total_cost == 0.5


def test_realistic_cost_profile_enables_market_impact() -> None:
    config = apply_cost_profile(
        {
            "model": "combined",
            "fixed_fee": 2.0,
            "commission_rate": 0.001,
            "market_impact_bps": 0.0,
        },
        "realistic",
    )

    assert config["cost_profile"] == "realistic"
    assert config["fixed_fee"] == 2.0
    assert config["commission_rate"] == 0.001
    assert config["market_impact_bps"] == 0.0
    assert config["market_impact_model"] == "sqrt_participation"
    assert config["market_impact_volatility_factor"] == 0.05


def test_min_commission_is_applied(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "linear",
            "commission_rate": 0.001,
            "min_commission": 5,
            "slippage_bps": 0,
        },
        report_dir=tmp_path / "reports",
    ).estimate([TradeInput("SPY", "BUY", 1, 100)])

    assert report.trades[0].commission == 5
    assert report.trades[0].total_cost == 5


def test_small_trade_generates_warning(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "fixed",
            "fixed_fee": 1,
            "slippage_bps": 0,
            "min_trade_notional": 50,
        },
        report_dir=tmp_path / "reports",
    ).estimate([TradeInput("SPY", "BUY", 1, 10)])

    assert "below min_trade_notional" in report.warnings[0]


def test_market_impact_scales_with_sqrt_adv_participation(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "combined",
            "fixed_fee": 0,
            "commission_rate": 0,
            "min_commission": 0,
            "slippage_bps": 0,
            "market_impact_bps": 5,
        },
        report_dir=tmp_path / "reports",
    ).estimate(
        [
            TradeInput("SPY", "BUY", 100, 100, average_daily_volume=10000),
            TradeInput("ILLQ", "BUY", 100, 100, average_daily_volume=200),
        ],
        write_report=False,
    )

    small_participation = report.trades[0]
    large_participation = report.trades[1]

    assert small_participation.adv_participation == pytest.approx(0.01)
    assert small_participation.market_impact_model == "sqrt_participation"
    assert small_participation.market_impact_bps_effective == pytest.approx(5.5)
    assert small_participation.market_impact_cost == pytest.approx(5.5)
    assert large_participation.adv_participation == pytest.approx(0.5)
    assert large_participation.market_impact_bps_effective == pytest.approx(8.5355339059)
    assert large_participation.market_impact_cost > small_participation.market_impact_cost


def test_market_impact_can_include_volatility_scaled_sqrt_participation(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "combined",
            "fixed_fee": 0,
            "commission_rate": 0,
            "min_commission": 0,
            "slippage_bps": 0,
            "market_impact_bps": 0,
            "market_impact_volatility_factor": 0.1,
        },
        report_dir=tmp_path / "reports",
    ).estimate(
        [TradeInput("VOL", "BUY", 100, 100, average_daily_volume=400, volatility=0.04)],
        write_report=False,
    )

    trade = report.trades[0]
    assert trade.adv_participation == pytest.approx(0.25)
    assert trade.market_impact_bps_effective == pytest.approx(20.0)
    assert trade.market_impact_cost == pytest.approx(20.0)


def test_flat_market_impact_model_preserves_legacy_formula(tmp_path: Path) -> None:
    report = CostEngine(
        {
            "model": "combined",
            "fixed_fee": 0,
            "commission_rate": 0,
            "min_commission": 0,
            "slippage_bps": 0,
            "market_impact_bps": 5,
            "market_impact_model": "flat",
        },
        report_dir=tmp_path / "reports",
    ).estimate(
        [
            TradeInput("LOW", "BUY", 100, 10, average_daily_volume=1000),
            TradeInput("HIGH", "BUY", 100, 10, average_daily_volume=50),
        ],
        write_report=False,
    )

    assert report.trades[0].market_impact_bps_effective == pytest.approx(5.0)
    assert report.trades[0].market_impact_cost == pytest.approx(0.5)
    assert report.trades[1].market_impact_bps_effective == pytest.approx(10.0)
    assert report.trades[1].market_impact_cost == pytest.approx(1.0)


def test_rebalance_with_costs_outputs_cost_estimate(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "quant.db"
    targets_path = tmp_path / "targets.json"
    cost_config_path = tmp_path / "cost_config.json"
    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "SPY",
                    "date": "2024-01-02",
                    "open": 100,
                    "high": 100,
                    "low": 100,
                    "close": 100,
                    "adj_close": 100,
                    "volume": 1000,
                }
            ]
        )
    )
    SQLitePortfolioStore(db_path).init_account(100000)
    targets_path.write_text(json.dumps({"SPY": 0.5, "cash": 0.5}), encoding="utf-8")
    cost_config_path.write_text(
        json.dumps({"model": "combined", "fixed_fee": 1, "commission_rate": 0.001}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "rebalance",
            "--targets",
            str(targets_path),
            "--with-costs",
            "--cost-config",
            str(cost_config_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "cost_estimate:" in output
    assert "total_cost:" in output

