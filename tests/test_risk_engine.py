from pathlib import Path

import pandas as pd

from quant.engines.portfolio.rebalance_engine import RebalanceEngine
from quant.engines.risk.risk_engine import RiskEngine
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


def setup_portfolio(db_path: Path) -> SQLitePortfolioStore:
    seed_prices(db_path, {"SPY": 100, "QQQ": 100, "NVDA": 100, "AAPL": 100, "GLD": 100})
    store = SQLitePortfolioStore(db_path)
    account = store.init_account(100000)
    store.buy(account["id"], "SPY", qty=300, price=100)
    store.buy(account["id"], "QQQ", qty=200, price=100)
    store.buy(account["id"], "NVDA", qty=100, price=100)
    store.buy(account["id"], "AAPL", qty=100, price=100)
    store.buy(account["id"], "GLD", qty=50, price=100)
    return store


def test_risk_metrics_are_calculated(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    store = setup_portfolio(db_path)
    engine = RiskEngine(store, report_dir=tmp_path / "reports")

    report = engine.analyze()

    assert report.total_assets == 100000
    assert report.cash_weight_pct == 25
    assert report.single_stock_concentration_pct == 30
    assert report.top_5_holdings_pct == 75
    assert 0 <= report.risk_score <= 100
    assert Path(report.report_path).exists()


def test_industry_concentration_is_aggregated(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    store = setup_portfolio(db_path)
    engine = RiskEngine(store, report_dir=tmp_path / "reports")

    report = engine.analyze()
    by_industry = {industry.industry: industry for industry in report.industries}

    assert by_industry["Technology"].weight_pct == 20
    assert by_industry["Equity ETF"].weight_pct == 50
    assert report.industry_concentration_pct == 50


def test_cash_only_account_has_low_concentration(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    store = SQLitePortfolioStore(db_path)
    store.init_account(100000)
    engine = RiskEngine(store, report_dir=tmp_path / "reports")

    report = engine.analyze()

    assert report.cash_weight_pct == 100
    assert report.single_stock_concentration_pct == 0
    assert report.industry_concentration_pct == 0
    assert report.top_5_holdings_pct == 0
    assert report.risk_score == 15


def test_unknown_industry_generates_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, {"XYZ": 100})
    store = SQLitePortfolioStore(db_path)
    account = store.init_account(100000)
    store.buy(account["id"], "XYZ", qty=100, price=100)
    engine = RiskEngine(store, report_dir=tmp_path / "reports")

    report = engine.analyze()

    assert "industry is unknown for XYZ" in report.warnings


def test_risk_engine_uses_rebalance_allocation_source(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    store = setup_portfolio(db_path)
    risk_report = RiskEngine(store, report_dir=tmp_path / "risk_reports").analyze()
    allocation = RebalanceEngine(store, report_dir=tmp_path / "rebalance_reports").allocation()

    assert risk_report.total_assets == allocation.total_assets
    assert risk_report.cash_value == allocation.cash

