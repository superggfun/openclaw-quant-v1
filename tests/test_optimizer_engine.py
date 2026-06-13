from pathlib import Path

import pandas as pd
import pytest

from quant.engines.portfolio.optimizer_engine import OptimizerEngine
from quant.engines.portfolio.rebalance_engine import RebalanceEngine
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, symbols: list[str]) -> None:
    rows = []
    for symbol_index, symbol in enumerate(symbols):
        for day in range(5):
            close = 100 + symbol_index + day
            rows.append(
                {
                    "symbol": symbol,
                    "date": f"2024-01-0{day + 1}",
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def make_optimizer(db_path: Path, report_dir: Path) -> OptimizerEngine:
    price_store = SQLitePriceStore(db_path)
    portfolio_store = SQLitePortfolioStore(db_path)
    portfolio_store.init_account(100000)
    return OptimizerEngine(price_store, portfolio_store, report_dir=report_dir)


def test_equal_weight_generates_targets(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["SPY", "QQQ", "TLT"])
    optimizer = make_optimizer(db_path, tmp_path / "reports")

    result = optimizer.optimize(
        mode="equal_weight",
        symbols=["SPY", "QQQ", "TLT"],
        constraints={
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
            "max_sector_weight": 1.0,
        },
    )

    assert result.optimized_allocation["cash"] == 0.1
    assert result.optimized_allocation["SPY"] == 0.3
    assert result.optimized_allocation["QQQ"] == 0.3
    assert result.optimized_allocation["TLT"] == 0.3
    assert Path(result.report_path).exists()


def test_min_cash_constraint_is_applied(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["SPY", "QQQ"])
    optimizer = make_optimizer(db_path, tmp_path / "reports")

    result = optimizer.optimize(
        mode="equal_weight",
        symbols=["SPY", "QQQ"],
        constraints={"min_cash_weight": 0.25, "max_position_weight": 0.5},
    )

    assert result.optimized_allocation["cash"] >= 0.25
    assert round(sum(result.optimized_allocation.values()), 6) == 1.0


def test_max_position_constraint_is_applied(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["SPY", "QQQ"])
    optimizer = make_optimizer(db_path, tmp_path / "reports")

    result = optimizer.optimize(
        mode="equal_weight",
        symbols=["SPY", "QQQ"],
        constraints={"min_cash_weight": 0.1, "max_position_weight": 0.2},
    )

    assert result.optimized_allocation["SPY"] <= 0.2
    assert result.optimized_allocation["QQQ"] <= 0.2
    assert result.optimized_allocation["cash"] == 0.6


def test_max_sector_constraint_is_applied(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["AAPL", "MSFT", "NVDA", "SPY"])
    optimizer = make_optimizer(db_path, tmp_path / "reports")

    result = optimizer.optimize(
        mode="equal_weight",
        symbols=["AAPL", "MSFT", "NVDA", "SPY"],
        constraints={
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
            "max_sector_weight": 0.3,
        },
    )

    technology_weight = (
        result.optimized_allocation["AAPL"]
        + result.optimized_allocation["MSFT"]
        + result.optimized_allocation["NVDA"]
    )
    assert technology_weight <= 0.300001
    assert "scaled Technology sector to max_sector_weight" in result.warnings


def test_optimized_targets_can_be_used_by_rebalance(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    target_path = tmp_path / "optimized_targets.json"
    seed_prices(db_path, ["SPY", "QQQ", "TLT"])
    optimizer = make_optimizer(db_path, tmp_path / "reports")

    optimizer.optimize(
        mode="equal_weight",
        symbols=["SPY", "QQQ", "TLT"],
        targets_path=target_path,
    )
    targets = pd.read_json(target_path, typ="series").to_dict()
    plan = RebalanceEngine(SQLitePortfolioStore(db_path), report_dir=tmp_path / "reports").plan(targets)

    assert plan.items
    assert plan.cash_after_rebalance >= 0


def test_no_price_data_has_clear_error(tmp_path: Path) -> None:
    optimizer = make_optimizer(tmp_path / "quant.db", tmp_path / "reports")

    with pytest.raises(ValueError, match="no price data found for optimizer universe"):
        optimizer.optimize(mode="equal_weight", symbols=["SPY"])
