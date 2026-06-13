from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.engines.alpha.alpha_engine import AlphaEngine
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.engines.factor_pipeline.factor_pipeline import FactorPipeline
from quant.storage.sqlite_store import SQLitePriceStore


def seed_pipeline_prices(db_path: Path, symbols: list[str], days: int = 120) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 75 + symbol_index * 12
        slope = 0.22 + symbol_index * 0.17
        for offset in range(days):
            close = base + offset * slope + ((offset % 7) - 3) * 0.04 * (symbol_index + 1)
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


def pipeline_config(**overrides) -> dict:
    config = {
        "missing": "drop",
        "winsorization": {"enabled": False, "lower_quantile": 0.05, "upper_quantile": 0.95},
        "zscore": False,
        "rank_normalization": False,
        "sector_neutralization": {
            "enabled": False,
            "sector_map": {
                "AAA": "Tech",
                "BBB": "Tech",
                "CCC": "Energy",
                "DDD": "Energy",
                "SPY": "Equity ETF",
                "QQQ": "Equity ETF",
                "NVDA": "Technology",
            },
        },
        "market_beta_neutralization": {"enabled": False},
    }
    config.update(overrides)
    return config


def test_missing_value_handling(tmp_path: Path) -> None:
    result = FactorPipeline(pipeline_config(), report_dir=tmp_path).run(
        {"AAA": 1.0, "BBB": None, "CCC": 3.0},
        factor="momentum_20d",
        as_of_date="2024-03-01",
    )

    assert result.cleaned_factor_values == {"AAA": 1.0, "CCC": 3.0}
    assert result.excluded_symbols == ["BBB"]
    assert result.exclusion_reasons["BBB"] == "missing factor value"
    assert Path(result.report_path).exists()


def test_winsorization(tmp_path: Path) -> None:
    config = pipeline_config(
        winsorization={"enabled": True, "lower_quantile": 0.25, "upper_quantile": 0.75}
    )

    result = FactorPipeline(config, report_dir=tmp_path).run(
        {"AAA": 1.0, "BBB": 2.0, "CCC": 100.0},
        factor="momentum_20d",
        as_of_date="2024-03-01",
    )

    assert result.cleaned_factor_values["AAA"] == pytest.approx(1.5)
    assert result.cleaned_factor_values["CCC"] == pytest.approx(51.0)
    assert "winsorization" in result.preprocessing_steps_applied


def test_zscore(tmp_path: Path) -> None:
    result = FactorPipeline(pipeline_config(zscore=True), report_dir=tmp_path).run(
        {"AAA": 1.0, "BBB": 2.0, "CCC": 3.0},
        factor="momentum_20d",
        as_of_date="2024-03-01",
    )

    cleaned = pd.Series(result.cleaned_factor_values, dtype="float64")
    assert cleaned.mean() == pytest.approx(0.0)
    assert cleaned.std() == pytest.approx(1.0)


def test_rank_normalization(tmp_path: Path) -> None:
    result = FactorPipeline(pipeline_config(rank_normalization=True), report_dir=tmp_path).run(
        {"AAA": 1.0, "BBB": 2.0, "CCC": 3.0},
        factor="momentum_20d",
        as_of_date="2024-03-01",
    )

    assert result.cleaned_factor_values["AAA"] == pytest.approx(-1 / 3)
    assert result.cleaned_factor_values["BBB"] == pytest.approx(1 / 3)
    assert result.cleaned_factor_values["CCC"] == pytest.approx(1.0)


def test_sector_neutralization(tmp_path: Path) -> None:
    config = pipeline_config(
        sector_neutralization={
            "enabled": True,
            "sector_map": {"AAA": "Tech", "BBB": "Tech", "CCC": "Energy", "DDD": "Energy"},
        }
    )

    result = FactorPipeline(config, report_dir=tmp_path).run(
        {"AAA": 1.0, "BBB": 3.0, "CCC": 10.0, "DDD": 14.0},
        factor="momentum_20d",
        as_of_date="2024-03-01",
    )

    assert result.cleaned_factor_values["AAA"] == pytest.approx(-1.0)
    assert result.cleaned_factor_values["BBB"] == pytest.approx(1.0)
    assert result.cleaned_factor_values["CCC"] == pytest.approx(-2.0)
    assert result.cleaned_factor_values["DDD"] == pytest.approx(2.0)
    assert result.sector_neutralization_result["Tech"]["mean_after"] == pytest.approx(0.0)


def test_alpha_compatibility(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_pipeline_prices(db_path, ["SPY", "QQQ", "NVDA"])
    engine = AlphaEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.generate(
        config={
            "universe": ["SPY", "QQQ", "NVDA"],
            "top_n": 2,
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
        },
        pipeline_config=pipeline_config(zscore=True),
    )

    assert result.pipeline_report_path is not None
    assert Path(result.pipeline_report_path).exists()
    assert round(sum(result.target_weights.values()), 6) == 1.0
    assert len(result.selected_symbols) == 2


def test_factor_eval_compatibility(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_pipeline_prices(db_path, ["AAA", "BBB", "CCC", "DDD"], days=130)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    result = engine.evaluate(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-04-01",
        forward_days=5,
        universe=["AAA", "BBB", "CCC", "DDD"],
        pipeline_config=pipeline_config(zscore=True),
    )

    assert result.pipeline_config is not None
    assert result.observations
    assert result.ic_count > 0


def test_pipeline_no_lookahead_behavior(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_pipeline_prices(db_path, ["SPY", "QQQ", "NVDA"])
    store = SQLitePriceStore(db_path)
    engine = AlphaEngine(store, report_dir=tmp_path / "reports")
    config = {
        "universe": ["SPY", "QQQ", "NVDA"],
        "as_of_date": "2024-03-15",
        "top_n": 2,
        "weighting_mode": "score_weighted",
        "min_cash_weight": 0.1,
        "max_position_weight": 0.5,
    }
    pipe_config = pipeline_config(zscore=True)

    before = engine.generate(config=config, pipeline_config=pipe_config)
    store.upsert_prices(
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
    after = engine.generate(config=config, pipeline_config=pipe_config)

    assert before.selected_symbols == after.selected_symbols
    assert before.target_weights == after.target_weights
    assert before.as_of_date == "2024-03-15"
    assert after.as_of_date == "2024-03-15"

