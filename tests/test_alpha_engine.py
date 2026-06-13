from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.engines.alpha.alpha_engine import AlphaEngine
from quant.engines.portfolio.rebalance_engine import RebalanceEngine
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


def seed_price_series(db_path: Path, symbols: list[str], days: int = 90) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        for offset in range(days):
            close = 100 + symbol_index * 5 + offset * (1 + symbol_index * 0.3)
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def seed_flat_price_series(db_path: Path, symbol: str, days: int = 90) -> None:
    start = date(2024, 1, 1)
    rows = [
        {
            "symbol": symbol,
            "date": (start + timedelta(days=offset)).isoformat(),
            "open": 100,
            "high": 100,
            "low": 100,
            "close": 100,
            "adj_close": 100,
            "volume": 1000,
        }
        for offset in range(days)
    ]
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def make_engine(db_path: Path, report_dir: Path) -> AlphaEngine:
    return AlphaEngine(SQLitePriceStore(db_path), report_dir=report_dir)


def test_alpha_generates_factor_values_and_ranks(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ", "NVDA"])
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.generate(
        {
            "universe": ["SPY", "QQQ", "NVDA"],
            "lookback_short": 20,
            "lookback_long": 60,
            "top_n": 2,
            "weighting_mode": "equal_weight",
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
        }
    )

    assert len(result.factors) == 3
    assert result.as_of_date == "2024-03-30"
    assert result.data_end_date == "2024-03-30"
    assert result.lookback_used == {
        "momentum_20d": 20,
        "momentum_60d": 60,
        "volatility_20d": 20,
    }
    assert all(row.momentum_20d is not None for row in result.factors)
    assert all(row.momentum_60d is not None for row in result.factors)
    assert all(row.volatility_20d is not None for row in result.factors)
    assert all(row.risk_adjusted_momentum is not None for row in result.factors)
    assert sorted(row.rank for row in result.factors if row.rank is not None) == [1, 2, 3]
    assert len(result.selected_symbols) == 2
    assert Path(result.report_path).exists()


def test_equal_weight_targets_respect_cash_and_top_n(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ", "NVDA"])
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.generate(
        {
            "universe": ["SPY", "QQQ", "NVDA"],
            "top_n": 2,
            "weighting_mode": "equal_weight",
            "min_cash_weight": 0.2,
            "max_position_weight": 0.5,
        }
    )

    selected_weights = [
        weight
        for symbol, weight in result.target_weights.items()
        if symbol != "cash"
    ]
    assert result.target_weights["cash"] == 0.2
    assert selected_weights == [0.4, 0.4]
    assert round(sum(result.target_weights.values()), 6) == 1.0


def test_score_weighted_targets_use_scores(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ", "NVDA"])
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.generate(
        {
            "universe": ["SPY", "QQQ", "NVDA"],
            "top_n": 3,
            "weighting_mode": "score_weighted",
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
        }
    )

    weights = [
        weight
        for symbol, weight in result.target_weights.items()
        if symbol != "cash"
    ]
    assert len(set(weights)) > 1
    assert result.target_weights["cash"] == round(1.0 - sum(weights), 6)


def test_alpha_targets_can_be_used_by_rebalance(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    target_path = tmp_path / "alpha_targets.json"
    seed_price_series(db_path, ["SPY", "QQQ"])
    SQLitePortfolioStore(db_path).init_account(100000)
    engine = make_engine(db_path, tmp_path / "reports")

    engine.generate(
        {
            "universe": ["SPY", "QQQ"],
            "top_n": 2,
            "weighting_mode": "equal_weight",
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
        },
        output_targets=target_path,
    )
    targets = pd.read_json(target_path, typ="series").to_dict()
    plan = RebalanceEngine(SQLitePortfolioStore(db_path), report_dir=tmp_path / "reports").plan(targets)

    assert plan.items
    assert plan.cash_after_rebalance >= 0


def test_alpha_no_data_has_clear_error(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "quant.db", tmp_path / "reports")

    with pytest.raises(ValueError, match="no symbols have enough price history"):
        engine.generate({"universe": ["SPY"]})


def test_as_of_date_excludes_future_data(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ"], days=90)
    engine = make_engine(db_path, tmp_path / "reports")
    config = {
        "universe": ["SPY", "QQQ"],
        "as_of_date": "2024-03-15",
        "top_n": 2,
        "weighting_mode": "score_weighted",
        "min_cash_weight": 0.1,
        "max_position_weight": 0.5,
    }

    before = engine.generate(config)
    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "SPY",
                    "date": "2024-04-15",
                    "open": 10000,
                    "high": 10000,
                    "low": 10000,
                    "close": 10000,
                    "adj_close": 10000,
                    "volume": 1000,
                }
            ]
        )
    )
    after = engine.generate(config)

    assert before.target_weights == after.target_weights
    assert before.as_of_date == "2024-03-15"
    assert after.as_of_date == "2024-03-15"
    assert all(row.data_end_date <= "2024-03-15" for row in after.factors if row.data_end_date)


def test_insufficient_data_symbol_is_excluded(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY"], days=90)
    seed_price_series(db_path, ["NEW"], days=10)
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.generate({"universe": ["SPY", "NEW"], "top_n": 2, "max_position_weight": 0.5})

    assert "NEW" in result.excluded_symbols
    assert "need at least" in result.exclusion_reasons["NEW"]
    assert "SPY" in result.selected_symbols


def test_zero_volatility_does_not_explode(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY"], days=90)
    seed_flat_price_series(db_path, "FLAT", days=90)
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.generate({"universe": ["SPY", "FLAT"], "top_n": 2, "max_position_weight": 0.5})
    flat = next(row for row in result.factors if row.symbol == "FLAT")

    assert flat.risk_adjusted_momentum is None
    assert "FLAT" in result.excluded_symbols
    assert result.exclusion_reasons["FLAT"] == "volatility_20d is zero"


def test_output_targets_sum_to_one_and_respect_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_price_series(db_path, ["SPY", "QQQ", "NVDA"], days=90)
    engine = make_engine(db_path, tmp_path / "reports")

    result = engine.generate(
        {
            "universe": ["SPY", "QQQ", "NVDA"],
            "top_n": 3,
            "min_cash_weight": 0.25,
            "max_position_weight": 0.2,
        }
    )

    assert round(sum(result.target_weights.values()), 6) == 1.0
    assert result.target_weights["cash"] >= 0.25
    assert all(
        weight <= 0.2
        for symbol, weight in result.target_weights.items()
        if symbol != "cash"
    )


def test_alpha_rejects_invalid_lookbacks(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "quant.db", tmp_path / "reports")

    with pytest.raises(ValueError, match="lookback_long must be greater than lookback_short"):
        engine.generate(
            {
                "universe": ["SPY"],
                "lookback_short": 60,
                "lookback_long": 20,
            }
        )
