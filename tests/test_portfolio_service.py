from pathlib import Path

import pandas as pd
import pytest

from quant.services.portfolio_service import PortfolioService
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


def make_service(db_path: Path) -> PortfolioService:
    return PortfolioService(SQLitePortfolioStore(db_path))


def seed_latest_price(db_path: Path, symbol: str = "SPY", close: float = 110.0) -> None:
    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
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
            ]
        )
    )


def test_init_account(tmp_path: Path) -> None:
    service = make_service(tmp_path / "quant.db")

    account = service.init_account(100000)
    snapshot = service.portfolio()

    assert account["cash"] == 100000
    assert account["initial_cash"] == 100000
    assert snapshot.cash == 100000
    assert snapshot.total_assets == 100000


def test_buy_success(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_latest_price(db_path, close=110.0)
    service = make_service(db_path)
    service.init_account(100000)

    position = service.buy("SPY", qty=10, price=100)
    snapshot = service.portfolio()

    assert position["symbol"] == "SPY"
    assert position["qty"] == 10
    assert position["avg_cost"] == 100
    assert snapshot.cash == 99000
    assert snapshot.positions[0].current_price == 110
    assert snapshot.positions[0].market_value == 1100
    assert snapshot.positions[0].unrealized_pnl == 100
    assert snapshot.total_assets == 100100
    assert len(service.trades()) == 1


def test_buy_fails_when_cash_is_insufficient(tmp_path: Path) -> None:
    service = make_service(tmp_path / "quant.db")
    service.init_account(100)

    with pytest.raises(ValueError, match="insufficient cash"):
        service.buy("SPY", qty=2, price=100)

    snapshot = service.portfolio()
    assert snapshot.cash == 100
    assert snapshot.positions == []
    assert service.trades() == []


def test_sell_success(tmp_path: Path) -> None:
    service = make_service(tmp_path / "quant.db")
    service.init_account(100000)
    service.buy("SPY", qty=10, price=100)

    position = service.sell("SPY", qty=4, price=120)

    snapshot = service.portfolio()
    assert position is not None
    assert position["qty"] == 6
    assert position["avg_cost"] == 100
    assert snapshot.cash == 99480
    assert len(service.trades()) == 2
    assert service.trades()[1]["side"] == "SELL"


def test_sell_fails_when_position_is_insufficient(tmp_path: Path) -> None:
    service = make_service(tmp_path / "quant.db")
    service.init_account(100000)
    service.buy("SPY", qty=3, price=100)

    with pytest.raises(ValueError, match="insufficient position"):
        service.sell("SPY", qty=4, price=100)

    snapshot = service.portfolio()
    assert snapshot.positions[0].qty == 3
    assert len(service.trades()) == 1


def test_portfolio_state_persists_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    service = make_service(db_path)
    service.init_account(100000)
    service.buy("AAPL", qty=5, price=200)

    restarted = make_service(db_path)
    snapshot = restarted.portfolio()

    assert snapshot.cash == 99000
    assert len(snapshot.positions) == 1
    assert snapshot.positions[0].symbol == "AAPL"
    assert snapshot.positions[0].qty == 5
    assert restarted.trades()[0]["symbol"] == "AAPL"

