from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.cli import main
from quant.factor_backtest.factor_backtest import FactorBacktest
from quant.factor_eval.factor_evaluation import FactorEvaluation
from quant.storage.sqlite_store import SQLitePriceStore


def seed_trending_prices(db_path: Path, symbols: list[str], days: int = 100) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        slope = 0.1 + symbol_index * 0.1
        for offset in range(days):
            close = 100 + offset * slope
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


def seed_flat_prices(db_path: Path, symbol: str, days: int = 90) -> None:
    rows = []
    start = date(2024, 1, 1)
    for offset in range(days):
        rows.append(
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
        )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def pipeline_config() -> dict:
    return {
        "missing": "drop",
        "winsorization": {"enabled": True, "lower_quantile": 0.05, "upper_quantile": 0.95},
        "zscore": True,
        "rank_normalization": False,
        "sector_neutralization": {
            "enabled": True,
            "sector_map": {
                "A": "One",
                "B": "One",
                "C": "Two",
                "D": "Two",
                "E": "Three",
            },
        },
        "market_beta_neutralization": {"enabled": False},
    }


def test_factor_backtest_quantile_grouping(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-01",
        holding_period=1,
        quantiles=5,
        universe=symbols,
    )

    period = result.periods[0]
    assert period.short_symbols == ["A"]
    assert period.long_symbols == ["E"]
    assert set(period.quantile_returns) == {"q1", "q2", "q3", "q4", "q5"}
    assert result.top_quantile_return == period.quantile_returns["q5"]
    assert result.bottom_quantile_return == period.quantile_returns["q1"]


def test_factor_backtest_long_short_return(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-01",
        holding_period=1,
        quantiles=5,
        universe=symbols,
    )

    period = result.periods[0]
    assert period.long_short_return == pytest.approx(period.long_return - period.short_return)
    assert result.long_short_return == pytest.approx(period.long_short_return)


def test_factor_backtest_long_short_exposures(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-03",
        holding_period=1,
        quantiles=5,
        universe=symbols,
    )

    for period in result.periods:
        assert period.long_weight_sum == pytest.approx(1.0)
        assert period.short_weight_sum == pytest.approx(-1.0)
        assert period.net_exposure == pytest.approx(0.0)
        assert period.gross_exposure == pytest.approx(2.0)
    assert result.net_exposure == pytest.approx(0.0)
    assert result.gross_exposure == pytest.approx(2.0)


def test_factor_backtest_supports_configurable_long_short_quantiles(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-01",
        holding_period=1,
        quantiles=5,
        long_quantile=4,
        short_quantile=2,
        universe=symbols,
    )

    assert result.long_quantile == 4
    assert result.short_quantile == 2
    assert result.periods[0].long_symbols == ["D"]
    assert result.periods[0].short_symbols == ["B"]


def test_factor_backtest_no_lookahead(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)
    store = SQLitePriceStore(db_path)
    engine = FactorBacktest(store, report_dir=tmp_path / "reports")

    before = engine.run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-01",
        holding_period=5,
        quantiles=5,
        universe=symbols,
    )
    store.upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "A",
                    "date": "2024-03-02",
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
    after = engine.run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-01",
        holding_period=5,
        quantiles=5,
        universe=symbols,
    )

    assert before.periods[0].long_symbols == after.periods[0].long_symbols
    assert before.periods[0].short_symbols == after.periods[0].short_symbols
    assert before.long_symbols_by_date == after.long_symbols_by_date
    assert before.short_symbols_by_date == after.short_symbols_by_date
    assert before.no_lookahead is True


def test_factor_backtest_pipeline_no_lookahead(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)
    store = SQLitePriceStore(db_path)
    engine = FactorBacktest(store, report_dir=tmp_path / "reports")

    before = engine.run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-01",
        holding_period=5,
        quantiles=5,
        universe=symbols,
        pipeline_config=pipeline_config(),
    )
    store.upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "E",
                    "date": "2024-03-03",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "adj_close": 1,
                    "volume": 1000,
                }
            ]
        )
    )
    after = engine.run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-01",
        holding_period=5,
        quantiles=5,
        universe=symbols,
        pipeline_config=pipeline_config(),
    )

    assert before.long_symbols_by_date == after.long_symbols_by_date
    assert before.short_symbols_by_date == after.short_symbols_by_date


def test_factor_backtest_pipeline_compatibility(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-10",
        holding_period=2,
        quantiles=5,
        universe=symbols,
        pipeline_config=pipeline_config(),
    )

    assert result.pipeline_config is not None
    assert result.observations > 0
    assert result.ic_count > 0


def test_factor_backtest_factor_eval_metric_consistency(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)
    store = SQLitePriceStore(db_path)
    kwargs = {
        "factor": "momentum_20d",
        "start": "2024-03-01",
        "end": "2024-03-10",
        "universe": symbols,
        "pipeline_config": pipeline_config(),
    }

    backtest = FactorBacktest(store, report_dir=tmp_path / "reports").run(
        holding_period=5,
        quantiles=5,
        **kwargs,
    )
    evaluation = FactorEvaluation(store, report_dir=tmp_path / "reports").evaluate(
        forward_days=5,
        **kwargs,
    )

    assert backtest.observations == len(evaluation.observations)
    assert backtest.ic_mean == pytest.approx(evaluation.ic_mean)
    assert backtest.rank_ic_mean == pytest.approx(evaluation.rank_ic_mean)
    assert backtest.icir == pytest.approx(evaluation.icir)


def test_factor_backtest_report_contains_quality_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["A", "B", "C", "D", "E"]
    seed_trending_prices(db_path, symbols)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-02",
        holding_period=1,
        quantiles=5,
        universe=symbols,
        pipeline_config=pipeline_config(),
        pipeline_config_path="examples/factor_pipeline_config.json",
    )
    report = pd.read_json(result.report_path, typ="series").to_dict()

    assert report["pipeline_enabled"] is True
    assert report["pipeline_config_path"] == "examples/factor_pipeline_config.json"
    assert report["rebalance_dates"] == ["2024-03-01", "2024-03-02"]
    assert "long_symbols_by_date" in report
    assert "short_symbols_by_date" in report
    assert "long_leg_return" in report
    assert "short_leg_return" in report
    assert "gross_exposure" in report
    assert "net_exposure" in report


def test_factor_backtest_sharpe_uses_arithmetic_period_mean(tmp_path: Path) -> None:
    returns = [0.4, 0.4, -0.7]
    sharpe = FactorBacktest._sharpe(returns)
    expected = (pd.Series(returns, dtype="float64").mean() / pd.Series(returns, dtype="float64").std()) * (252.0 ** 0.5)

    assert FactorBacktest._compound_return(returns) < 0
    assert sharpe > 0
    assert sharpe == pytest.approx(expected)


def test_factor_backtest_excludes_insufficient_data(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trending_prices(db_path, ["A", "B", "C", "D", "E"], days=90)
    seed_trending_prices(db_path, ["NEW"], days=10)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-05",
        holding_period=1,
        universe=["A", "B", "C", "D", "E", "NEW"],
    )

    assert "NEW" in result.excluded_symbols
    assert result.exclusion_reasons["NEW"] == "no valid factor and future-return pairs"


def test_factor_backtest_zero_volatility_and_missing_price_do_not_crash(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trending_prices(db_path, ["A", "B", "C", "D", "E"], days=100)
    seed_flat_prices(db_path, "FLAT", days=100)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="risk_adjusted_momentum",
        start="2024-03-15",
        end="2024-03-20",
        holding_period=1,
        universe=["A", "B", "C", "D", "E", "FLAT", "MISSING"],
    )

    assert result.observations > 0
    assert result.exclusion_reasons["FLAT"] == "no valid factor and future-return pairs"
    assert result.exclusion_reasons["MISSING"] == "no price data"


def test_factor_backtest_incomplete_long_short_period_warns(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_trending_prices(db_path, ["A"], days=100)

    result = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        factor="momentum_20d",
        start="2024-03-01",
        end="2024-03-03",
        holding_period=1,
        universe=["A"],
    )

    assert result.long_short_return is None
    assert result.gross_exposure is None
    assert result.net_exposure is None
    assert any("incomplete long-short construction" in warning for warning in result.warnings)


def test_factor_backtest_cli_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "quant.db"
    seed_trending_prices(db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=100)

    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "factor-backtest",
            "--factor",
            "momentum_20d",
            "--start",
            "2024-03-01",
            "--end",
            "2024-03-05",
            "--holding-period",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Factor Backtest Summary" in output
    assert "long_short_return:" in output
    assert "report:" in output
