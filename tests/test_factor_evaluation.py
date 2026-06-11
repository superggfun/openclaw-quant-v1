from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.factor_eval.factor_evaluation import FactorEvaluation
from quant.storage.sqlite_store import SQLitePriceStore


def seed_factor_prices(db_path: Path, symbols: list[str], days: int = 140) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 80 + symbol_index * 11
        trend = 0.18 + symbol_index * 0.14
        for offset in range(days):
            wave = ((offset % 9) - 4) * 0.03 * (symbol_index + 1)
            acceleration = (offset // 25) * 0.015 * symbol_index
            close = base + offset * trend + offset * acceleration + wave
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


def seed_flat_prices(db_path: Path, symbol: str, days: int = 90) -> None:
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


def make_engine(db_path: Path, report_dir: Path) -> FactorEvaluation:
    return FactorEvaluation(SQLitePriceStore(db_path), report_dir=report_dir)


def test_ic_calculation(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="momentum_20d",
        start="2024-03-15",
        end="2024-04-15",
        forward_days=5,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )

    assert result.ic_count > 0
    assert result.ic_mean is not None
    assert -1 <= result.ic_mean <= 1
    assert Path(result.report_path).exists()


def test_rank_ic_calculation(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="momentum_60d",
        start="2024-03-15",
        end="2024-04-15",
        forward_days=5,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )

    assert result.rank_ic_count > 0
    assert result.rank_ic_mean is not None
    assert -1 <= result.rank_ic_mean <= 1


def test_icir_calculation(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="momentum_20d",
        start="2024-02-15",
        end="2024-04-25",
        forward_days=10,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )

    assert result.ic_count > 1
    if result.ic_std not in {None, 0.0}:
        assert result.icir == pytest.approx(result.ic_mean / result.ic_std)


def test_quintile_grouping(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="momentum_20d",
        start="2024-03-15",
        end="2024-04-15",
        forward_days=5,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )

    assert set(result.quintiles) == {"q1", "q2", "q3", "q4", "q5"}
    assert all(value is not None for value in result.quintiles.values())
    assert result.spread_return == pytest.approx(result.quintiles["q5"] - result.quintiles["q1"])


def test_decay_calculation(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"], days=150)

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="risk_adjusted_momentum",
        start="2024-03-15",
        end="2024-04-15",
        forward_days=20,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )

    assert set(result.decay) == {"1d", "5d", "10d", "20d", "60d"}
    for metrics in result.decay.values():
        assert {"ic", "rank_ic", "ic_count", "rank_ic_count"} <= set(metrics)


def test_no_lookahead_verification(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB", "CCC"])
    engine = make_engine(db_path, tmp_path / "reports")

    before = engine.evaluate(
        factor="momentum_20d",
        start="2024-03-20",
        end="2024-03-20",
        forward_days=5,
        universe=["AAA", "BBB", "CCC"],
    )
    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "date": "2024-03-21",
                    "open": 9999,
                    "high": 9999,
                    "low": 9999,
                    "close": 9999,
                    "adj_close": 9999,
                    "volume": 1000,
                }
            ]
        )
    )
    after = engine.evaluate(
        factor="momentum_20d",
        start="2024-03-20",
        end="2024-03-20",
        forward_days=5,
        universe=["AAA", "BBB", "CCC"],
    )

    before_factors = {(row.signal_date, row.symbol): row.factor_value for row in before.observations}
    after_factors = {(row.signal_date, row.symbol): row.factor_value for row in after.observations}
    assert before_factors == after_factors


def test_empty_factor_handling(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA"], days=10)

    with pytest.raises(ValueError, match="no factor observations"):
        make_engine(db_path, tmp_path / "reports").evaluate(
            factor="momentum_20d",
            universe=["AAA"],
        )


def test_missing_price_handling(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB"], days=90)

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-10",
        forward_days=5,
        universe=["AAA", "BBB", "MISSING"],
    )

    assert "MISSING" in result.excluded_symbols
    assert result.exclusion_reasons["MISSING"] == "no price data"


def test_single_symbol_edge_case(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA"], days=100)

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-20",
        forward_days=5,
        universe=["AAA"],
    )

    assert result.observations
    assert result.ic_count == 0
    assert result.rank_ic_count == 0
    assert result.ic_mean is None
    assert result.rank_ic_mean is None
