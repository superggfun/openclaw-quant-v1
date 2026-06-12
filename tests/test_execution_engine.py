from pathlib import Path

import pandas as pd

from quant.execution.execution_engine import ExecutionEngine
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path) -> None:
    rows = []
    for row in [
        ("SPY", "2024-01-01", 99, 100),
        ("SPY", "2024-01-02", 120, 121),
        ("QQQ", "2024-01-01", 49, 50),
        ("QQQ", "2024-01-02", 55, 56),
    ]:
        symbol, date_text, open_price, close_price = row
        rows.append(
            {
                "symbol": symbol,
                "date": date_text,
                "open": open_price,
                "high": max(open_price, close_price),
                "low": min(open_price, close_price),
                "close": close_price,
                "adj_close": close_price,
                "volume": 1000,
            }
        )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def make_engine(db_path: Path, report_dir: Path, cash: float = 100000) -> ExecutionEngine:
    seed_prices(db_path)
    SQLitePortfolioStore(db_path).init_account(cash)
    return ExecutionEngine(
        SQLitePriceStore(db_path),
        SQLitePortfolioStore(db_path),
        report_dir=report_dir,
    )


def test_immediate_execution_runs_to_completion(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.run({"SPY": 0.5, "cash": 0.5}, mode="immediate")

    assert result.intended_trades
    assert result.executed_trades
    assert not result.unfilled_trades
    assert result.final_positions["SPY"] > 0
    assert Path(result.report_path).exists()


def test_next_day_open_uses_following_open_price(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.run(
        {"SPY": 0.5, "cash": 0.5},
        mode="next_day_open",
        execution_date="2024-01-01",
    )

    assert result.executed_trades[0].price == 120
    assert result.executed_trades[0].executed_at == "2024-01-02"


def test_twap_splits_trades_into_batches(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.run(
        {"SPY": 0.5, "cash": 0.5},
        mode="twap",
        twap_slices=4,
    )

    intended_shares = result.intended_trades[0].shares
    executed_shares = sum(trade.shares for trade in result.executed_trades)

    assert len(result.executed_trades) == 4
    assert executed_shares == intended_shares
    assert [trade.batch for trade in result.executed_trades] == [1, 2, 3, 4]


def test_partial_fill_creates_unfilled_trade(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.run(
        {"SPY": 0.5, "cash": 0.5},
        mode="partial_fill",
        fill_ratio=0.5,
    )

    intended_shares = result.intended_trades[0].shares
    executed_shares = sum(trade.shares for trade in result.executed_trades)
    unfilled_shares = sum(trade.shares for trade in result.unfilled_trades)

    assert executed_shares == intended_shares // 2
    assert unfilled_shares == intended_shares - executed_shares


def test_execution_costs_are_included(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.run(
        {"SPY": 0.5, "cash": 0.5},
        mode="immediate",
        cost_config={
            "model": "combined",
            "fixed_fee": 1,
            "commission_rate": 0.001,
            "min_commission": 1,
            "slippage_bps": 5,
        },
    )

    assert result.execution_costs["total_cost"] > 0
    assert result.slippage_estimate > 0
    assert all(trade.total_cost > 0 for trade in result.executed_trades)


def test_execution_report_schema_extends_with_market_realism(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.run({"SPY": 0.5, "cash": 0.5}, mode="immediate")
    report = Path(result.report_path).read_text(encoding="utf-8")

    payload = __import__("json").loads(report)
    assert {
        "mode",
        "target_allocation",
        "intended_trades",
        "executed_trades",
        "unfilled_trades",
        "execution_costs",
        "slippage_estimate",
        "final_cash",
        "final_positions",
        "warnings",
    } <= set(payload)
    assert "market_realism" in payload
    assert "protocol_orders" not in payload
    assert "protocol_fills" not in payload
