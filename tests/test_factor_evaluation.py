from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.engines.factor_eval.factor_evaluation import FactorEvaluation, FactorObservation, _estimate_half_life
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


class LatestDatesOnlyStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def latest_dates(self, symbols: list[str]) -> dict[str, str | None]:
        return {symbol.upper(): f"2024-01-0{index + 1}" for index, symbol in enumerate(symbols)}

    def latest_date(self, symbol: str) -> str | None:
        raise AssertionError("expected bulk latest_dates path")


class BulkHistoryOnlyStore:
    def __init__(self, db_path: Path, days: int = 45) -> None:
        self.db_path = db_path
        self.days = days
        self.bulk_calls = 0

    def get_price_history_many(self, symbols: list[str], start: str | None = None, end: str | None = None):
        self.bulk_calls += 1
        histories = {}
        start_date = date(2024, 1, 1)
        for symbol_index, symbol in enumerate(symbols):
            histories[symbol.upper()] = pd.DataFrame(
                [
                    {
                        "symbol": symbol.upper(),
                        "date": (start_date + timedelta(days=offset)).isoformat(),
                        "open": 100 + symbol_index + offset,
                        "high": 100 + symbol_index + offset,
                        "low": 100 + symbol_index + offset,
                        "close": 100 + symbol_index + offset,
                        "adj_close": 100 + symbol_index + offset,
                        "volume": 1000,
                    }
                    for offset in range(self.days)
                ]
            )
        return histories

    def get_price_history(self, *args, **kwargs):
        raise AssertionError("expected bulk price history path")


def test_data_newest_date_uses_bulk_latest_dates(tmp_path: Path) -> None:
    engine = FactorEvaluation(LatestDatesOnlyStore(tmp_path / "unused.db"), report_dir=tmp_path / "reports")

    assert engine._data_newest_date(["aaa", "BBB"]) == "2024-01-02"


def test_observations_use_bulk_price_history(tmp_path: Path) -> None:
    store = BulkHistoryOnlyStore(tmp_path / "unused.db")
    engine = FactorEvaluation(store, report_dir=tmp_path / "reports")

    observations, excluded, reasons, warnings = engine._serial_reference_observations(
        "momentum_20d",
        ["aaa", "BBB"],
        start="2024-01-25",
        end="2024-01-28",
        forward_days=5,
    )

    assert observations
    assert excluded == []
    assert reasons == {}
    assert warnings == []
    assert store.bulk_calls == 1


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


def test_factor_eval_lower_is_better_reverses_quintile_spread() -> None:
    observations = [
        FactorObservation("2024-01-01", "2024-01-02", "LOW", 1.0, 0.03, 1),
        FactorObservation("2024-01-01", "2024-01-02", "LOW_MID", 1.5, 0.025, 1),
        FactorObservation("2024-01-01", "2024-01-02", "MID", 2.0, 0.02, 1),
        FactorObservation("2024-01-01", "2024-01-02", "HIGH_MID", 2.5, 0.015, 1),
        FactorObservation("2024-01-01", "2024-01-02", "HIGH", 3.0, 0.01, 1),
    ]

    directional = FactorEvaluation._directional_observations(observations, higher_is_better=False)
    quintiles = FactorEvaluation._quintiles(directional)

    assert quintiles["q5"] == pytest.approx(0.03)
    assert quintiles["q1"] == pytest.approx(0.01)
    assert FactorEvaluation._spread_return(quintiles) == pytest.approx(0.02)


def test_factor_eval_run_uses_lower_is_better_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = make_engine(tmp_path / "quant.db", tmp_path / "reports")
    observations = [
        FactorObservation("2024-01-01", "2024-01-02", "LOW", 1.0, 0.03, 1),
        FactorObservation("2024-01-01", "2024-01-02", "LOW_MID", 1.5, 0.025, 1),
        FactorObservation("2024-01-01", "2024-01-02", "MID", 2.0, 0.02, 1),
        FactorObservation("2024-01-01", "2024-01-02", "HIGH_MID", 2.5, 0.015, 1),
        FactorObservation("2024-01-01", "2024-01-02", "HIGH", 3.0, 0.01, 1),
    ]
    metadata = {
        "factor_family": "risk",
        "factor_type": "test",
        "factor_category": "risk",
        "factor_description": "lower is better test",
        "factor_inputs": [],
        "higher_is_better": False,
        "no_lookahead": True,
    }

    monkeypatch.setattr(engine.factor_registry, "metadata", lambda factor: metadata)
    monkeypatch.setattr(engine, "_factor_coverage", lambda factor, symbols, observations: None)
    monkeypatch.setattr(engine, "_factor_coverage_warnings", lambda factor, coverage: [])
    monkeypatch.setattr(engine, "_serial_reference_observations", lambda *args, **kwargs: (observations, [], {}, []))
    monkeypatch.setattr(engine, "_decay", lambda **kwargs: {})

    result = engine.evaluate(
        factor="momentum_20d",
        start="2024-01-01",
        end="2024-01-01",
        forward_days=1,
        universe=["LOW", "LOW_MID", "MID", "HIGH_MID", "HIGH"],
        bulk_matrix=False,
    )

    assert result.factor_higher_is_better is False
    assert result.quintiles["q5"] == pytest.approx(0.03)
    assert result.quintiles["q1"] == pytest.approx(0.01)
    assert result.spread_return == pytest.approx(0.02)


def test_factor_eval_no_lookahead_fields_use_factor_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = make_engine(tmp_path / "quant.db", tmp_path / "reports")
    observations = [
        FactorObservation("2024-01-01", "2024-01-02", "AAA", 1.0, 0.01, 1),
        FactorObservation("2024-01-01", "2024-01-02", "BBB", 2.0, 0.02, 1),
    ]
    metadata = {
        "factor_family": "test",
        "factor_type": "experimental",
        "factor_category": "test",
        "factor_description": "lookahead-prone test factor",
        "factor_inputs": [],
        "higher_is_better": True,
        "no_lookahead": False,
    }

    monkeypatch.setattr(engine.factor_registry, "metadata", lambda factor: metadata)
    monkeypatch.setattr(engine, "_factor_coverage", lambda factor, symbols, observations: None)
    monkeypatch.setattr(engine, "_factor_coverage_warnings", lambda factor, coverage: [])
    monkeypatch.setattr(engine, "_serial_reference_observations", lambda *args, **kwargs: (observations, [], {}, []))
    monkeypatch.setattr(engine, "_decay", lambda **kwargs: {})

    result = engine.evaluate(
        factor="momentum_20d",
        start="2024-01-01",
        end="2024-01-01",
        forward_days=1,
        universe=["AAA", "BBB"],
        bulk_matrix=False,
    )
    report = result.to_report()

    assert result.evaluator_no_lookahead is True
    assert result.factor_no_lookahead is False
    assert result.overall_no_lookahead is False
    assert result.no_lookahead is False
    assert report["evaluator_no_lookahead"] is True
    assert report["factor_no_lookahead"] is False
    assert report["overall_no_lookahead"] is False
    assert report["no_lookahead"] is False


def test_quintiles_are_date_weighted() -> None:
    observations = [
        *[
            FactorObservation("2024-01-01", "2024-01-02", f"D1_{index}", float(index), value, 1)
            for index, value in enumerate([0.0, 0.0, 0.0, 0.0, 0.50], start=1)
        ],
        *[
            FactorObservation("2024-01-02", "2024-01-03", f"D2_{index}", float(index), 0.0, 1)
            for index in range(1, 11)
        ],
    ]

    quintiles = FactorEvaluation._quintiles(observations)

    assert quintiles["q5"] == pytest.approx(0.25)


def test_half_life_rejects_rank_ic_sign_flip() -> None:
    assert _estimate_half_life(
        {
            "1d": {"ic": 0.10, "rank_ic": 0.10},
            "5d": {"ic": 0.08, "rank_ic": -0.08},
            "20d": {"ic": 0.04, "rank_ic": 0.04},
        }
    ) is None


def test_factor_eval_report_contains_half_life_and_compact_default(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"], days=150)

    result = make_engine(db_path, tmp_path / "reports").evaluate(
        factor="momentum_20d",
        start="2024-03-15",
        end="2024-04-15",
        forward_days=5,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
    )
    compact = result.to_report()
    full = result.to_report(include_observations=True)

    assert "half_life_days" in compact
    assert compact["half_life_method"] == "rank_ic_abs_exp_fit"
    assert compact["forward_return_basis"] == "signal_close_to_future_close"
    assert compact["tradable_return"] is False
    assert compact["observations_count"] == len(result.observations)
    assert "observations" not in compact
    assert len(full["observations"]) == len(result.observations)


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


def test_validate_uses_instance_factor_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = make_engine(tmp_path / "quant.db", tmp_path / "reports")
    observations = [
        FactorObservation("2024-01-01", "2024-01-02", "AAA", 1.0, 0.01, 1),
        FactorObservation("2024-01-01", "2024-01-02", "BBB", 2.0, 0.02, 1),
    ]
    metadata = {
        "factor_family": "plugin",
        "factor_type": "custom",
        "factor_category": "custom",
        "factor_description": "custom instance factor",
        "factor_inputs": [],
        "higher_is_better": True,
        "no_lookahead": True,
    }

    monkeypatch.setattr(engine.factor_registry, "factor_names", lambda: ["custom_factor"])
    monkeypatch.setattr(engine.factor_registry, "metadata", lambda factor: metadata)
    monkeypatch.setattr(engine, "_factor_coverage", lambda factor, symbols, observations: None)
    monkeypatch.setattr(engine, "_factor_coverage_warnings", lambda factor, coverage: [])
    monkeypatch.setattr(engine, "_serial_reference_observations", lambda *args, **kwargs: (observations, [], {}, []))
    monkeypatch.setattr(engine, "_decay", lambda **kwargs: {})

    result = engine.evaluate(
        factor="custom_factor",
        start="2024-01-01",
        end="2024-01-01",
        forward_days=1,
        universe=["AAA", "BBB"],
        bulk_matrix=False,
    )

    assert result.factor == "custom_factor"


def test_factor_eval_rejects_non_iso_dates(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "quant.db", tmp_path / "reports")

    with pytest.raises(ValueError, match="start must be an ISO date"):
        engine.evaluate(factor="momentum_20d", start="2024-2-1", end="2024-10-01")


def test_serial_observations_skip_zero_signal_close(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    rows = [
        {
            "symbol": "AAA",
            "date": (date(2024, 1, 1) + timedelta(days=offset)).isoformat(),
            "open": 0 if offset == 25 else 100 + offset,
            "high": 0 if offset == 25 else 100 + offset,
            "low": 0 if offset == 25 else 100 + offset,
            "close": 0 if offset == 25 else 100 + offset,
            "adj_close": 0 if offset == 25 else 100 + offset,
            "volume": 1000,
        }
        for offset in range(50)
    ]
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))
    engine = make_engine(db_path, tmp_path / "reports")

    observations, _, _, _ = engine._serial_reference_observations(
        "momentum_20d",
        ["AAA"],
        start="2024-01-26",
        end="2024-01-26",
        forward_days=5,
    )

    assert observations == []


def test_performance_metadata_marks_serial_reference() -> None:
    metadata = FactorEvaluation._performance_metadata(
        cache=None,
        cache_before={},
        matrix_metadata=None,
        cache_enabled=False,
        bulk_matrix=False,
        cache_stats=True,
    )

    assert metadata is not None
    assert metadata["serial_reference"] is True
