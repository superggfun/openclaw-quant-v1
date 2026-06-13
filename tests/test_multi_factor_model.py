from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quant.engines.alpha.alpha_engine import AlphaEngine
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.engines.multi_factor.factor_combiner import FactorCombiner
from quant.engines.multi_factor.factor_stability import FactorStability
from quant.engines.multi_factor.factor_weighting import FactorWeighting
from quant.engines.multi_factor.multi_factor_model import MultiFactorModel
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, symbols: list[str], days: int = 120) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 100 + symbol_index * 10
        slope = 0.4 + symbol_index * 0.2
        for offset in range(days):
            close = base + offset * slope + ((offset % 7) - 3) * 0.2
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def seed_metrics(store: FundamentalStore, symbol: str, report_date: str = "2024-01-20", **overrides) -> None:
    row = {
        "symbol": symbol,
        "fiscal_period_end": "2023-12-31",
        "report_date": report_date,
        "fiscal_year": 2023,
        "fiscal_quarter": "FY",
        "currency": "USD",
        "pe_ratio": 20,
        "pb_ratio": 5,
        "ev_to_ebitda": 15,
        "roe": 0.20,
        "roa": 0.10,
        "gross_margin": 0.50,
        "net_margin": 0.20,
        "debt_to_equity": 0.5,
        "current_ratio": 2.0,
        "quick_ratio": 1.0,
        "revenue_growth": 0.10,
        "eps_growth": 0.12,
    }
    row.update(overrides)
    store.upsert("fundamental_metrics", row)


def test_rank_and_zscore_normalization() -> None:
    rank = FactorCombiner.normalize({"A": 1, "B": 3, "C": 2}, method="rank")
    zscore = FactorCombiner.normalize({"A": 1, "B": 3, "C": 2}, method="zscore")

    assert rank.values["B"] > rank.values["C"] > rank.values["A"]
    assert round(sum(zscore.values.values()), 12) == 0.0


def test_factor_weighting_modes() -> None:
    factors = ["momentum_60d", "fundamental_quality_score"]
    custom, _ = FactorWeighting.weights(factors, "custom_weight", custom_weights={"momentum_60d": 3, "fundamental_quality_score": 1})
    ic_weighted, _ = FactorWeighting.weights(
        factors,
        "ic_weighted",
        ic_metrics={
            "momentum_60d": {"ic_mean": 0.01, "rank_ic_mean": 0.02, "icir": 0.1},
            "fundamental_quality_score": {"ic_mean": 0.20, "rank_ic_mean": 0.10, "icir": 0.5},
        },
    )
    stability, _ = FactorWeighting.weights(
        factors,
        "stability_weighted",
        stability_scores={"momentum_60d": 0.2, "fundamental_quality_score": 0.8},
        coverage={"momentum_60d": 1.0, "fundamental_quality_score": 0.5},
    )

    assert custom["momentum_60d"] == 0.75
    assert ic_weighted["fundamental_quality_score"] > ic_weighted["momentum_60d"]
    assert stability["fundamental_quality_score"] > stability["momentum_60d"]
    assert round(sum(custom.values()), 12) == 1.0
    assert round(sum(ic_weighted.values()), 12) == 1.0
    assert round(sum(stability.values()), 12) == 1.0


def test_stability_weighting_missing_history_warns_and_falls_back() -> None:
    factors = ["momentum_60d", "fundamental_quality_score"]
    weights, warnings = FactorWeighting.weights(factors, "stability_weighted", stability_scores={}, coverage={})

    assert weights == {"fundamental_quality_score": 0.5, "momentum_60d": 0.5}
    assert any("missing stability scores" in warning for warning in warnings)
    assert any("fallback to equal_weight" in warning for warning in warnings)


def test_multi_factor_model_confidence_and_missing_data() -> None:
    result = MultiFactorModel().run(
        {
            "AAPL": {"momentum_60d": 0.2, "fundamental_quality_score": 0.8},
            "MSFT": {"momentum_60d": 0.1, "fundamental_quality_score": None},
            "NVDA": {"momentum_60d": 0.3, "fundamental_quality_score": 0.5},
        },
        {
            "factors": ["momentum_60d", "fundamental_quality_score"],
            "weighting_mode": "stability_weighted",
            "stability_scores": {"momentum_60d": 0.7, "fundamental_quality_score": 0.6},
            "family_weights": {"PRICE": 0.4, "QUALITY": 0.6},
        },
        write_report=False,
    )

    assert result.coverage["momentum_60d"] == 1.0
    assert result.coverage["fundamental_quality_score"] == round(2 / 3, 6)
    assert result.confidence["overall_confidence"] < 1.0
    assert any("LOW_FACTOR_COVERAGE" in warning for warning in result.warnings)
    assert all(score.final_alpha_score is not None for score in result.scores)
    assert round(sum(result.factor_weights.values()), 12) == 1.0
    assert round(sum(result.family_weights.values()), 12) == 1.0
    assert all(round(sum(weights.values()), 12) == 1.0 for weights in result.factor_weights_by_family.values())


def test_factor_stability_scores_are_bounded() -> None:
    score = FactorStability.score(
        ic_history=[0.1, 0.2, -0.05],
        rank_ic_history=[0.05, 0.07],
        decay={"20d": 0.1},
        walk_forward_score=0.8,
        coverage=0.5,
    )

    assert 0.0 <= score <= 1.0
    assert FactorStability.label(score) in {"stable", "moderate", "unstable"}


def test_alpha_multi_factor_integration_and_no_lookahead(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAPL", "MSFT", "NVDA"]
    seed_prices(db_path, symbols)
    fundamental_store = FundamentalStore(db_path)
    seed_metrics(fundamental_store, "AAPL", pe_ratio=10, roe=0.30, revenue_growth=0.20)
    seed_metrics(fundamental_store, "MSFT", pe_ratio=25, roe=0.20, revenue_growth=0.10)
    seed_metrics(fundamental_store, "NVDA", pe_ratio=40, roe=0.10, revenue_growth=0.30)
    seed_metrics(
        fundamental_store,
        "AAPL",
        report_date="2024-06-01",
        fiscal_period_end="2024-03-31",
        fiscal_quarter="Q1",
        pe_ratio=1,
        roe=0.90,
    )
    engine = AlphaEngine(SQLitePriceStore(db_path), fundamental_store, report_dir=tmp_path / "reports")
    config = {
        "universe": symbols,
        "as_of_date": "2024-04-01",
        "top_n": 2,
        "weighting_mode": "stability_weighted",
        "min_cash_weight": 0.1,
        "max_position_weight": 0.5,
        "family_weights": {"PRICE": 0.25, "VALUE": 0.25, "QUALITY": 0.25, "GROWTH": 0.25},
        "multi_factor": {
            "factors": [
                "momentum_60d",
                "fundamental_value_score",
                "fundamental_quality_score",
                "fundamental_growth_score",
            ],
            "weighting_mode": "stability_weighted",
            "stability_scores": {
                "momentum_60d": 0.6,
                "fundamental_value_score": 0.5,
                "fundamental_quality_score": 0.7,
                "fundamental_growth_score": 0.5,
            },
        },
    }

    before = engine.generate(config)
    db_path_without_future = tmp_path / "quant_without_future.db"
    seed_prices(db_path_without_future, symbols)
    store_without_future = FundamentalStore(db_path_without_future)
    seed_metrics(store_without_future, "AAPL", pe_ratio=10, roe=0.30, revenue_growth=0.20)
    seed_metrics(store_without_future, "MSFT", pe_ratio=25, roe=0.20, revenue_growth=0.10)
    seed_metrics(store_without_future, "NVDA", pe_ratio=40, roe=0.10, revenue_growth=0.30)
    after = AlphaEngine(
        SQLitePriceStore(db_path_without_future),
        store_without_future,
        report_dir=tmp_path / "reports_without_future",
    ).generate(config)
    aapl = next(row for row in before.factors if row.symbol == "AAPL")

    assert before.target_weights == after.target_weights
    assert [row.symbol for row in before.factors if row.rank is not None] == [
        row.symbol for row in after.factors if row.rank is not None
    ]
    assert {
        row.symbol: row.composite_alpha_score for row in before.factors
    } == {
        row.symbol: row.composite_alpha_score for row in after.factors
    }
    assert before.multi_factor_summary is not None
    assert before.multi_factor_report_path
    assert aapl.family_contributions
    assert aapl.factor_confidence
    assert aapl.overall_confidence is not None
    assert round(sum(before.target_weights.values()), 6) == 1.0
    assert before.config["target_weighting_mode"] == "equal_weight"
    assert before.as_of_date == "2024-04-01"
