from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quant.alpha.alpha_engine import AlphaEngine
from quant.factor_backtest.factor_backtest import FactorBacktest
from quant.factor_eval.factor_evaluation import FactorEvaluation
from quant.factors.factor_registry import FactorRegistry
from quant.fundamental_data.fundamental_store import FundamentalStore
from quant.storage.sqlite_store import SQLitePriceStore
from quant.walk_forward.walk_forward import WalkForwardEngine


def seed_prices(db_path: Path, symbols: list[str], days: int = 180, start: date = date(2024, 1, 1)) -> None:
    rows = []
    for symbol_index, symbol in enumerate(symbols):
        base = 80 + symbol_index * 20
        slope = 0.08 + symbol_index * 0.05
        for offset in range(days):
            close = base + offset * slope + ((offset % (5 + symbol_index)) - 2) * 0.15
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000 + offset,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def seed_metrics(
    store: FundamentalStore,
    symbol: str,
    report_date: str = "2024-01-15",
    fiscal_period_end: str = "2023-12-31",
    fiscal_quarter: str = "FY",
    **overrides,
) -> None:
    row = {
        "symbol": symbol,
        "fiscal_period_end": fiscal_period_end,
        "report_date": report_date,
        "fiscal_year": 2023,
        "fiscal_quarter": fiscal_quarter,
        "currency": "USD",
        "pe_ratio": 20,
        "pb_ratio": 5,
        "ev_to_ebitda": 15,
        "roe": 0.20,
        "roa": 0.10,
        "gross_margin": 0.50,
        "net_margin": 0.22,
        "debt_to_equity": 0.5,
        "current_ratio": 2.0,
        "quick_ratio": 1.0,
        "revenue_growth": 0.10,
        "eps_growth": 0.12,
    }
    row.update(overrides)
    store.upsert("fundamental_metrics", row)


def test_factor_registry_lists_fundamental_metadata() -> None:
    registry = FactorRegistry()
    definition = registry.describe("fundamental_quality_score")

    assert "fundamental_quality_score" in registry.factor_names()
    assert definition.category == "fundamental_quality"
    assert definition.higher_is_better is True
    assert definition.no_lookahead is True
    assert definition.data_source == "fundamental"
    assert definition.fundamental_data_required is True
    assert "fundamental_metrics.report_date" in definition.required_inputs
    assert "roe" in (definition.fundamental_metrics_used or [])
    metadata = registry.metadata("fundamental_quality_score")
    assert metadata["fundamental_data_required"] is True


def test_value_factors_prefer_lower_positive_multiples(tmp_path: Path) -> None:
    store = FundamentalStore(tmp_path / "quant.db")
    seed_metrics(store, "AAPL", pe_ratio=10, pb_ratio=3)
    seed_metrics(store, "MSFT", pe_ratio=30, pb_ratio=8)
    registry = FactorRegistry(store)
    closes = pd.Series([100, 101])

    assert registry.factor_value(closes, "pe_value_factor", "AAPL", "2024-02-01") > registry.factor_value(closes, "pe_value_factor", "MSFT", "2024-02-01")
    assert registry.factor_value(closes, "pb_value_factor", "AAPL", "2024-02-01") > registry.factor_value(closes, "pb_value_factor", "MSFT", "2024-02-01")


def test_quality_growth_and_health_factors(tmp_path: Path) -> None:
    store = FundamentalStore(tmp_path / "quant.db")
    seed_metrics(store, "AAPL", roe=0.30, roa=0.15, revenue_growth=0.20, eps_growth=0.25, debt_to_equity=0.2)
    seed_metrics(store, "MSFT", roe=0.10, roa=0.05, revenue_growth=0.02, eps_growth=0.03, debt_to_equity=1.5)
    registry = FactorRegistry(store)
    closes = pd.Series([100, 101])

    assert registry.factor_value(closes, "roe_quality_factor", "AAPL", "2024-02-01") > registry.factor_value(closes, "roe_quality_factor", "MSFT", "2024-02-01")
    assert registry.factor_value(closes, "roa_quality_factor", "AAPL", "2024-02-01") > registry.factor_value(closes, "roa_quality_factor", "MSFT", "2024-02-01")
    assert registry.factor_value(closes, "revenue_growth_factor", "AAPL", "2024-02-01") > registry.factor_value(closes, "revenue_growth_factor", "MSFT", "2024-02-01")
    assert registry.factor_value(closes, "eps_growth_factor", "AAPL", "2024-02-01") > registry.factor_value(closes, "eps_growth_factor", "MSFT", "2024-02-01")
    assert registry.factor_value(closes, "debt_to_equity_factor", "AAPL", "2024-02-01") > registry.factor_value(closes, "debt_to_equity_factor", "MSFT", "2024-02-01")
    assert registry.factor_value(closes, "current_ratio_factor", "AAPL", "2024-02-01") is not None


def test_missing_data_skips_components_without_fake_values(tmp_path: Path) -> None:
    store = FundamentalStore(tmp_path / "quant.db")
    seed_metrics(store, "AAPL", pe_ratio=10, pb_ratio=None, ev_to_ebitda=None)
    registry = FactorRegistry(store)
    closes = pd.Series([100, 101])

    assert registry.factor_value(closes, "fundamental_value_score", "AAPL", "2024-02-01") == -10
    assert registry.factor_value(closes, "fundamental_value_score", "MSFT", "2024-02-01") is None


def test_report_date_filtering_prevents_lookahead(tmp_path: Path) -> None:
    store = FundamentalStore(tmp_path / "quant.db")
    seed_metrics(store, "AAPL", report_date="2024-01-15", fiscal_period_end="2023-12-31", pe_ratio=20)
    seed_metrics(store, "AAPL", report_date="2024-05-15", fiscal_period_end="2024-03-31", fiscal_quarter="Q1", pe_ratio=5)
    registry = FactorRegistry(store)
    closes = pd.Series([100, 101])

    assert registry.factor_value(closes, "pe_value_factor", "AAPL", "2024-04-01") == -20
    assert registry.factor_value(closes, "pe_value_factor", "AAPL", "2024-06-01") == -5


def test_composite_alpha_uses_fundamental_contributions(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAPL", "MSFT", "NVDA"]
    seed_prices(db_path, symbols, days=100)
    fundamental_store = FundamentalStore(db_path)
    seed_metrics(fundamental_store, "AAPL", pe_ratio=10, roe=0.3, revenue_growth=0.3)
    seed_metrics(fundamental_store, "MSFT", pe_ratio=25, roe=0.2, revenue_growth=0.1)
    seed_metrics(fundamental_store, "NVDA", pe_ratio=40, roe=0.1, revenue_growth=0.2)

    result = AlphaEngine(SQLitePriceStore(db_path), fundamental_store, report_dir=tmp_path / "reports").generate(
        {
            "universe": symbols,
            "as_of_date": "2024-04-01",
            "lookback_short": 20,
            "lookback_long": 60,
            "top_n": 2,
            "factor_weights": {
                "fundamental_value_score": 0.5,
                "fundamental_quality_score": 0.5,
            },
        }
    )

    row = next(item for item in result.factors if item.symbol == "AAPL")
    assert row.composite_alpha_score is not None
    assert row.factor_contributions is not None
    assert abs(sum(row.factor_contributions.values()) - row.composite_alpha_score) < 1e-12
    assert round(sum(result.target_weights.values()), 6) == 1.0


def test_factor_evaluation_and_backtest_support_fundamental_factors(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAPL", "MSFT", "NVDA"]
    seed_prices(db_path, symbols, days=140)
    fundamental_store = FundamentalStore(db_path)
    seed_metrics(fundamental_store, "AAPL", pe_ratio=10, roe=0.3)
    seed_metrics(fundamental_store, "MSFT", pe_ratio=25, roe=0.2)
    seed_metrics(fundamental_store, "NVDA", pe_ratio=40, roe=0.1)
    price_store = SQLitePriceStore(db_path)

    evaluation = FactorEvaluation(price_store, fundamental_store, report_dir=tmp_path / "reports").evaluate(
        "fundamental_quality_score",
        start="2024-02-01",
        end="2024-04-01",
        forward_days=5,
        universe=symbols,
    )
    backtest = FactorBacktest(price_store, fundamental_store, report_dir=tmp_path / "reports").run(
        "fundamental_value_score",
        start="2024-02-01",
        end="2024-04-01",
        holding_period=5,
        universe=symbols,
    )

    assert evaluation.no_lookahead is True
    assert evaluation.factor_coverage["coverage_percentage"] == 1.0
    assert evaluation.observations
    assert backtest.no_lookahead is True
    assert backtest.factor_coverage["coverage_percentage"] == 1.0


def test_walk_forward_accepts_fundamental_factor(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAPL", "MSFT", "NVDA"]
    seed_prices(db_path, symbols, days=420, start=date(2023, 1, 1))
    fundamental_store = FundamentalStore(db_path)
    seed_metrics(fundamental_store, "AAPL", report_date="2023-01-15", pe_ratio=10, roe=0.3)
    seed_metrics(fundamental_store, "MSFT", report_date="2023-01-15", pe_ratio=25, roe=0.2)
    seed_metrics(fundamental_store, "NVDA", report_date="2023-01-15", pe_ratio=40, roe=0.1)

    result = WalkForwardEngine(SQLitePriceStore(db_path), fundamental_store, report_dir=tmp_path / "reports").run(
        strategy="factor_long_short",
        factor="fundamental_quality_score",
        train_years=0.2,
        test_years=0.1,
        universe=symbols,
        max_folds=1,
    )

    assert result.folds
    assert result.folds[0].no_lookahead is True
