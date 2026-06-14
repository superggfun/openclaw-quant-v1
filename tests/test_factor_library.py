from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.engines.alpha.alpha_engine import AlphaEngine
from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.factors.registry import FACTOR_DEFINITIONS, discover_factor_modules, discover_factor_specs
from quant.factors.price.factor_registry import FactorRegistry
from quant.storage.sqlite_store import SQLitePriceStore


def seed_factor_library_prices(db_path: Path, symbols: list[str], days: int = 170) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 70 + symbol_index * 13
        slope = 0.10 + symbol_index * 0.08
        for offset in range(days):
            wave = ((offset % (7 + symbol_index)) - 3) * 0.12 * (symbol_index + 1)
            cycle = ((offset // 18) % 3) * 0.08 * symbol_index
            close = base + offset * slope + wave + cycle
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


def test_factor_registry_lists_new_factor_families() -> None:
    registry = FactorRegistry()
    names = set(registry.factor_names())

    assert {
        "value_score",
        "quality_score",
        "growth_score",
        "reversal_5d",
        "reversal_20d",
        "low_volatility_score",
    } <= names
    quality = registry.describe("quality_score")
    assert quality.category == "quality"
    assert quality.required_inputs == ["close"]
    assert quality.higher_is_better is True
    assert quality.no_lookahead is True
    assert registry.describe("volatility_20d").higher_is_better is False


def test_factor_specs_are_auto_discovered() -> None:
    modules = discover_factor_modules()
    discovered = discover_factor_specs(modules)

    assert discovered == FACTOR_DEFINITIONS
    assert "momentum_20d" in discovered
    assert "fundamental_quality_score" in discovered
    assert discovered["momentum_20d"].compute.__module__.endswith(".momentum_factors")
    assert discovered["fundamental_quality_score"].data_source == "fundamental"


def test_price_proxy_factors_produce_values() -> None:
    closes = pd.Series([100 + index * 0.2 + ((index % 5) - 2) * 0.1 for index in range(150)])
    registry = FactorRegistry()

    for factor in [
        "value_score",
        "quality_score",
        "growth_score",
        "reversal_5d",
        "reversal_20d",
        "low_volatility_score",
    ]:
        value = registry.factor_value(closes, factor)
        assert value is not None
        assert pd.notna(value)
        assert value not in {float("inf"), float("-inf")}


def test_reversal_score_prefers_recent_underperformance() -> None:
    registry = FactorRegistry()
    rising = pd.Series([100 + index for index in range(40)])
    falling = pd.Series([140 - index for index in range(40)])

    assert registry.factor_value(falling, "reversal_20d") > registry.factor_value(rising, "reversal_20d")


def test_low_volatility_score_prefers_lower_realized_volatility() -> None:
    registry = FactorRegistry()
    calm = pd.Series([100 + index * 0.1 + ((index % 2) * 0.01) for index in range(60)])
    noisy = pd.Series([100 + index * 0.1 + ((index % 2) * 2.0) for index in range(60)])

    assert registry.factor_value(calm, "low_volatility_score") > registry.factor_value(noisy, "low_volatility_score")


def test_composite_alpha_generates_breakdown(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_library_prices(db_path, ["AAA", "BBB", "CCC", "DDD"])

    result = AlphaEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").generate(
        {
            "universe": ["AAA", "BBB", "CCC", "DDD"],
            "top_n": 3,
            "weighting_mode": "score_weighted",
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
            "factor_weights": {
                "momentum_60d": 0.4,
                "quality_score": 0.3,
                "growth_score": 0.2,
                "reversal_20d": 0.1,
            },
        }
    )

    scored_rows = [row for row in result.factors if not row.excluded]
    assert scored_rows
    assert all(row.composite_alpha_score is not None for row in scored_rows)
    assert all(row.factor_contributions for row in scored_rows)
    for row in scored_rows:
        assert sum((row.factor_contributions or {}).values()) == pytest.approx(row.composite_alpha_score)
    assert round(sum(result.target_weights.values()), 6) == 1.0
    assert result.target_weights["cash"] + 1e-6 >= 0.1
    assert "composite_alpha_score" in Path(result.report_path).read_text(encoding="utf-8")


def test_missing_factor_values_do_not_crash_composite_alpha(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_library_prices(db_path, ["AAA", "BBB", "CCC"], days=90)

    result = AlphaEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").generate(
        {
            "universe": ["AAA", "BBB", "CCC"],
            "top_n": 2,
            "weighting_mode": "score_weighted",
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
            "factor_weights": {
                "value_score": 0.5,
                "quality_score": 0.5,
            },
        }
    )

    assert result.selected_symbols
    assert all((row.factor_contributions or {}).get("value_score", 0.0) == 0.0 for row in result.factors if not row.excluded)


def test_factor_evaluation_accepts_new_factor(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_library_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").evaluate(
        factor="quality_score",
        start="2024-03-20",
        end="2024-05-01",
        forward_days=5,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )

    assert result.observations
    assert result.factor_family == "quality"
    assert result.factor_type == "price_proxy"
    assert result.factor_higher_is_better is True
    assert result.factor_no_lookahead is True


def test_factor_backtest_accepts_new_factor(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_library_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="reversal_20d",
        start="2024-03-20",
        end="2024-05-01",
        holding_period=5,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )

    assert result.observations > 0
    assert result.factor_family == "reversal"
    assert result.no_lookahead is True
    assert result.factor_higher_is_better is True


def test_new_factor_no_lookahead(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_library_prices(db_path, ["AAA", "BBB", "CCC"])
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    before = engine.evaluate(
        factor="growth_score",
        start="2024-04-10",
        end="2024-04-10",
        forward_days=5,
        universe=["AAA", "BBB", "CCC"],
    )
    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "date": "2024-05-30",
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
        factor="growth_score",
        start="2024-04-10",
        end="2024-04-10",
        forward_days=5,
        universe=["AAA", "BBB", "CCC"],
    )

    before_scores = {(row.signal_date, row.symbol): row.factor_value for row in before.observations}
    after_scores = {(row.signal_date, row.symbol): row.factor_value for row in after.observations}
    assert before_scores == after_scores


def test_all_new_factors_no_lookahead(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_library_prices(db_path, ["AAA", "BBB", "CCC"], days=170)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    factors = [
        "value_score",
        "quality_score",
        "growth_score",
        "reversal_5d",
        "reversal_20d",
        "low_volatility_score",
    ]
    for factor in factors:
        before = engine.evaluate(
            factor=factor,
            start="2024-05-15",
            end="2024-05-15",
            forward_days=5,
            universe=["AAA", "BBB", "CCC"],
        )
        SQLitePriceStore(db_path).upsert_prices(
            pd.DataFrame(
                [
                    {
                        "symbol": "AAA",
                        "date": "2024-06-10",
                        "open": 5000,
                        "high": 5000,
                        "low": 5000,
                        "close": 5000,
                        "adj_close": 5000,
                        "volume": 1000,
                    }
                ]
            )
        )
        after = engine.evaluate(
            factor=factor,
            start="2024-05-15",
            end="2024-05-15",
            forward_days=5,
            universe=["AAA", "BBB", "CCC"],
        )
        assert [(row.symbol, row.factor_value) for row in before.observations] == [
            (row.symbol, row.factor_value) for row in after.observations
        ]


def test_factor_backtest_warns_when_spread_compounds_to_minus_100(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    rows = []
    start = date(2024, 1, 1)
    for offset in range(80):
        if offset < 60:
            high_score_close = 100 - offset
            low_score_close = 100 + offset
        elif offset == 65:
            high_score_close = 1
            low_score_close = 250
        else:
            high_score_close = 40
            low_score_close = 160
        for symbol, close in {"LOSER": high_score_close, "WINNER": low_score_close}.items():
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

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="reversal_20d",
        start="2024-02-15",
        end="2024-03-01",
        holding_period=5,
        quantiles=2,
        universe=["LOSER", "WINNER"],
    )

    assert any(
        "rounded to -100%" in warning or "period return was <= -100%" in warning
        for warning in result.warnings
    )


def test_unknown_factor_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported factor"):
        FactorRegistry().describe("not_a_factor")
