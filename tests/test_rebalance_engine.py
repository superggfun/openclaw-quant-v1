from pathlib import Path

import pandas as pd

from quant.engines.portfolio.rebalance_engine import RebalanceEngine
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, prices: dict[str, float]) -> None:
    rows = []
    for symbol, close in prices.items():
        rows.append(
            {
                "symbol": symbol,
                "date": "2024-01-02",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "adj_close": close,
                "volume": 1000,
            }
        )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def make_store(db_path: Path, cash: float = 100000) -> SQLitePortfolioStore:
    store = SQLitePortfolioStore(db_path)
    store.init_account(cash)
    return store


def make_engine(db_path: Path, report_dir: Path) -> RebalanceEngine:
    return RebalanceEngine(SQLitePortfolioStore(db_path), report_dir=report_dir)


def test_target_allocation_values_are_calculated_correctly(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, {"SPY": 100, "QQQ": 100, "NVDA": 100})
    store = make_store(db_path, cash=100000)
    account = store.get_account()
    assert account is not None
    store.buy(account["id"], "SPY", qty=300, price=100)
    store.buy(account["id"], "QQQ", qty=250, price=100)
    store.buy(account["id"], "NVDA", qty=250, price=100)

    plan = make_engine(db_path, tmp_path / "reports").plan(
        {"SPY": 0.4, "QQQ": 0.3, "NVDA": 0.2, "cash": 0.1},
        commission_rate=0.001,
    )
    by_symbol = {item.symbol: item for item in plan.items}

    assert plan.total_assets == 100000
    assert by_symbol["SPY"].current_value == 30000
    assert by_symbol["SPY"].target_value == 40000
    assert by_symbol["SPY"].difference == 10000
    assert by_symbol["cash"].target_value == 10000


def test_cash_shortfall_is_reported(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, {"SPY": 100})
    make_store(db_path, cash=1000)

    plan = make_engine(db_path, tmp_path / "reports").plan(
        {"SPY": 1.0, "cash": 0.0},
        commission_rate=0.1,
    )

    assert "insufficient cash to fully reach target allocation for SPY" in plan.warnings


def test_empty_account_can_rebalance(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, {"SPY": 100, "QQQ": 50})
    make_store(db_path, cash=100000)

    plan = make_engine(db_path, tmp_path / "reports").plan(
        {"SPY": 0.5, "QQQ": 0.4, "cash": 0.1},
        commission_rate=0.001,
    )

    actions = {item.symbol: item.action for item in plan.items}
    assert actions["SPY"] == "BUY"
    assert actions["QQQ"] == "BUY"
    assert plan.cash_after_rebalance > 0


def test_single_symbol_100_percent_target(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, {"SPY": 100})
    make_store(db_path, cash=100000)

    plan = make_engine(db_path, tmp_path / "reports").plan(
        {"SPY": 1.0, "cash": 0.0},
        commission_rate=0.0,
    )
    spy = next(item for item in plan.items if item.symbol == "SPY")

    assert spy.action == "BUY"
    assert spy.qty == 1000
    assert plan.cash_after_rebalance == 0


def test_multiple_symbol_rebalance_actions(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, {"SPY": 100, "QQQ": 100, "NVDA": 100})
    store = make_store(db_path, cash=100000)
    account = store.get_account()
    assert account is not None
    store.buy(account["id"], "SPY", qty=300, price=100)
    store.buy(account["id"], "QQQ", qty=250, price=100)
    store.buy(account["id"], "NVDA", qty=250, price=100)

    plan = make_engine(db_path, tmp_path / "reports").plan(
        {"SPY": 0.4, "QQQ": 0.2, "NVDA": 0.3, "cash": 0.1},
        commission_rate=0.0,
    )
    by_symbol = {item.symbol: item for item in plan.items}

    assert by_symbol["SPY"].action == "BUY"
    assert by_symbol["SPY"].qty == 100
    assert by_symbol["QQQ"].action == "SELL"
    assert by_symbol["QQQ"].qty == 50
    assert by_symbol["NVDA"].action == "BUY"
    assert by_symbol["NVDA"].qty == 50


def test_commission_is_calculated(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, {"SPY": 100})
    make_store(db_path, cash=100000)

    plan = make_engine(db_path, tmp_path / "reports").plan(
        {"SPY": 1.0, "cash": 0.0},
        commission_rate=0.001,
    )
    spy = next(item for item in plan.items if item.symbol == "SPY")

    assert spy.qty == 999
    assert spy.estimated_trade_cost == 99.9
    assert plan.estimated_total_commission == 99.9
