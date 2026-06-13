from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.cli_commands.common import create_context
from quant.factor_acceleration import FactorBatchTask, FactorMatrixBuilder, run_factor_batch_tasks
from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.factors.store.factor_store import FactorStore
from quant.factors.price.factor_registry import FactorRegistry
from quant.research_validation import ResearchValidationRunner
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, symbols: list[str], days: int = 150) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 70 + symbol_index * 13
        trend = 0.11 + symbol_index * 0.07
        for offset in range(days):
            close = base + offset * trend + ((offset % 11) - 5) * 0.025 * (symbol_index + 1)
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


def comparable_eval(result) -> dict:
    report = result.to_report()
    report.pop("performance_metadata", None)
    for key in ("cache_enabled", "cache_hits", "cache_misses", "matrix_rows", "matrix_build_seconds", "eval_seconds", "speedup_estimate"):
        report.pop(key, None)
    return report


def comparable_backtest(result) -> dict:
    report = result.to_report()
    report.pop("report_path", None)
    return report


def factor_store_counts(db_path: Path) -> dict[str, int]:
    FactorStore(db_path)
    tables = [
        "factor_definitions",
        "factor_values",
        "factor_evaluation_history",
        "factor_backtest_history",
        "factor_stability_history",
        "factor_versions",
    ]
    with FactorStore(db_path).connect() as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
            for table in tables
        }


def test_get_price_history_many_matches_single_symbol_loop(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC"]
    seed_prices(db_path, symbols, days=40)
    store = SQLitePriceStore(db_path)

    many = store.get_price_history_many(symbols, start="2024-01-10", end="2024-01-20")

    assert set(many) == set(symbols)
    for symbol in symbols:
        pd.testing.assert_frame_equal(
            many[symbol].reset_index(drop=True),
            store.get_price_history(symbol, start="2024-01-10", end="2024-01-20").reset_index(drop=True),
        )


def test_observation_matrix_preserves_no_lookahead_factor_values(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["AAA", "BBB"], days=100)
    store = SQLitePriceStore(db_path)
    registry = FactorRegistry()
    builder = FactorMatrixBuilder(store, registry)

    before = builder.build("momentum_20d", ["AAA", "BBB"], "2024-03-20", "2024-03-20", 5)
    store.upsert_prices(
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
    after = builder.build("momentum_20d", ["AAA", "BBB"], "2024-03-20", "2024-03-20", 5)

    before_values = {(row.signal_date, row.symbol): row.factor_value for row in before.valid_rows}
    after_values = {(row.signal_date, row.symbol): row.factor_value for row in after.valid_rows}
    assert before_values == after_values


def test_bulk_factor_eval_matches_legacy_and_decay(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    seed_prices(db_path, symbols)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    legacy = engine.evaluate("momentum_20d", start="2024-02-15", end="2024-04-15", forward_days=10, universe=symbols)
    bulk = engine.evaluate("momentum_20d", start="2024-02-15", end="2024-04-15", forward_days=10, universe=symbols, bulk_matrix=True, cache_stats=True)

    assert comparable_eval(bulk) == comparable_eval(legacy)
    assert bulk.performance_metadata is not None
    assert bulk.performance_metadata["bulk_matrix_enabled"] is True
    assert bulk.performance_metadata["bulk_read_seconds"] is not None
    assert bulk.decay == legacy.decay


@pytest.mark.parametrize(
    "factor",
    [
        "momentum_20d",
        "momentum_60d",
        "volatility_20d",
        "risk_adjusted_momentum",
        "value_score",
        "quality_score",
        "growth_score",
        "reversal_5d",
        "reversal_20d",
        "low_volatility_score",
    ],
)
def test_bulk_factor_eval_matches_legacy_for_all_price_factors(tmp_path: Path, factor: str) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    seed_prices(db_path, symbols, days=180)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    legacy = engine.evaluate(factor, start="2024-05-01", end="2024-05-20", forward_days=5, universe=symbols)
    bulk = engine.evaluate(factor, start="2024-05-01", end="2024-05-20", forward_days=5, universe=symbols, bulk_matrix=True)

    assert comparable_eval(bulk) == comparable_eval(legacy)


def test_factor_backtest_bulk_matches_legacy(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    seed_prices(db_path, symbols)
    engine = FactorBacktest(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    legacy = engine.run("momentum_20d", start="2024-02-15", end="2024-04-15", holding_period=10, universe=symbols)
    bulk = engine.run("momentum_20d", start="2024-02-15", end="2024-04-15", holding_period=10, universe=symbols, bulk_matrix=True)

    assert comparable_backtest(bulk) == comparable_backtest(legacy)


def test_parallel_worker_does_not_write_factor_store(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])
    before = factor_store_counts(db_path)
    task = FactorBatchTask(
        kind="factor_eval",
        factor="momentum_20d",
        batch_index=1,
        batch_count=1,
        symbols=["AAA", "BBB", "CCC", "DDD", "EEE"],
        db_path=str(db_path),
        report_dir=str(tmp_path / "reports"),
        bulk_matrix=True,
    )

    results = run_factor_batch_tasks([task], workers=1)

    assert results[0].error is None
    assert results[0].result is not None
    assert factor_store_counts(db_path) == before


def test_parallel_runner_respects_zero_timeout_without_writes(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["AAA", "BBB", "CCC"])
    before = factor_store_counts(db_path)
    task = FactorBatchTask(
        kind="factor_eval",
        factor="momentum_20d",
        batch_index=1,
        batch_count=1,
        symbols=["AAA", "BBB", "CCC"],
        db_path=str(db_path),
        report_dir=str(tmp_path / "reports"),
        bulk_matrix=True,
    )

    results = run_factor_batch_tasks([task], workers=1, timeout_seconds=0)

    assert results[0].status == "TIMEOUT"
    assert results[0].result is None
    assert factor_store_counts(db_path) == before


def test_parallel_research_validation_matches_serial_small_config(tmp_path: Path) -> None:
    symbols = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"]
    serial_context = create_context(tmp_path / "serial.db")
    parallel_context = create_context(tmp_path / "parallel.db")
    seed_prices(serial_context.db_path, symbols, days=130)
    seed_prices(parallel_context.db_path, symbols, days=130)

    serial = ResearchValidationRunner(serial_context, report_dir=tmp_path / "serial_reports").run(
        mode="quick",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=30,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
    )
    parallel = ResearchValidationRunner(parallel_context, report_dir=tmp_path / "parallel_reports").run(
        mode="quick",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=30,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
        parallel=True,
        workers=2,
        write_batch_artifacts=True,
    )

    assert parallel["performance_metadata"]["parallel_enabled"] is True
    assert parallel["factor_evidence_summary"] == serial["factor_evidence_summary"]
    assert parallel["top_10_factors"][0]["factor"] == serial["top_10_factors"][0]["factor"]


def test_research_validation_parallel_aggregate_is_compact_with_artifacts(tmp_path: Path) -> None:
    symbols = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"]
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, symbols, days=130)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=30,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
        parallel=True,
        workers=2,
        write_batch_artifacts=True,
    )

    assert report["factor_eval_results"]
    eval_result = report["factor_eval_results"][0]
    assert "observations" not in eval_result
    assert eval_result["observation_count"] > 0
    assert {"ic_mean", "rank_ic_mean", "icir", "coverage", "warnings", "report_path"} <= set(eval_result)

    assert report["factor_backtest_results"]
    backtest_result = report["factor_backtest_results"][0]
    assert "periods" not in backtest_result
    assert "long_symbols_by_date" not in backtest_result
    assert "short_symbols_by_date" not in backtest_result
    assert "observations" not in backtest_result
    assert backtest_result["observation_count"] > 0
    assert {"long_short_return", "sharpe", "max_drawdown", "turnover", "ic_mean", "rank_ic_mean", "coverage"} <= set(backtest_result)

    artifact_path = Path(backtest_result["artifact_path"])
    assert artifact_path.exists()
    artifact_text = artifact_path.read_text(encoding="utf-8")
    assert '"periods"' in artifact_text
    assert '"long_symbols_by_date"' in artifact_text
    assert any(row["code"] == "REPORT_COMPACTED" for row in report["warning_statistics"])
    assert report["performance_metadata"]["aggregate_report_size_bytes"] > 0
    assert report["performance_metadata"]["detailed_artifact_count"] >= 1


def test_batch_factor_store_writes_preserve_row_counts(tmp_path: Path) -> None:
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    individual_db = tmp_path / "individual.db"
    batch_db = tmp_path / "batch.db"
    seed_prices(individual_db, symbols, days=140)
    seed_prices(batch_db, symbols, days=140)

    individual_eval = FactorEvaluation(SQLitePriceStore(individual_db), report_dir=tmp_path / "individual_reports").evaluate(
        "momentum_20d",
        start="2024-03-01",
        end="2024-04-15",
        forward_days=5,
        universe=symbols,
        bulk_matrix=True,
        write_report=False,
    )
    individual_backtest = FactorBacktest(SQLitePriceStore(individual_db), report_dir=tmp_path / "individual_reports").run(
        "momentum_20d",
        start="2024-03-01",
        end="2024-04-15",
        holding_period=5,
        universe=symbols,
        bulk_matrix=True,
        write_report=False,
    )
    individual_store = FactorStore(individual_db)
    individual_store.save_factor_evaluation(individual_eval)
    individual_store.save_factor_backtest(individual_backtest)

    batch_eval = FactorEvaluation(SQLitePriceStore(batch_db), report_dir=tmp_path / "batch_reports").evaluate(
        "momentum_20d",
        start="2024-03-01",
        end="2024-04-15",
        forward_days=5,
        universe=symbols,
        bulk_matrix=True,
        write_report=False,
    )
    batch_backtest = FactorBacktest(SQLitePriceStore(batch_db), report_dir=tmp_path / "batch_reports").run(
        "momentum_20d",
        start="2024-03-01",
        end="2024-04-15",
        holding_period=5,
        universe=symbols,
        bulk_matrix=True,
        write_report=False,
    )
    batch_store = FactorStore(batch_db)
    batch_store.save_factor_evaluations([batch_eval])
    batch_store.save_factor_backtests([batch_backtest])

    assert factor_store_counts(batch_db) == factor_store_counts(individual_db)


def test_parallel_research_validation_auto_batching_feeds_workers() -> None:
    batch_size = ResearchValidationRunner._effective_batch_size(
        symbol_count=80,
        mode="quick",
        requested_batch_size=None,
        parallel=True,
        workers=16,
    )
    batches = ResearchValidationRunner._symbol_batches([f"S{index}" for index in range(80)], batch_size)

    assert batch_size == 3
    assert len(batches) >= 16
    assert ResearchValidationRunner._effective_batch_size(80, "quick", None, False, 16) == 10


def test_parallel_research_validation_falls_back_to_serial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=130)

    def fail_parallel(*args, **kwargs):
        raise RuntimeError("forced parallel failure")

    monkeypatch.setattr("quant.research_validation.research_validation.run_factor_batch_tasks", fail_parallel)
    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=30,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
        parallel=True,
        workers=2,
    )

    assert any(row["code"] == "PARALLEL_FALLBACK_SERIAL" for row in report["warning_statistics"])
    assert report["factor_eval_results"]


def test_report_filenames_are_unique_under_rapid_repeated_calls(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    seed_prices(db_path, symbols)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")

    first = engine.evaluate("momentum_20d", universe=symbols, forward_days=5)
    second = engine.evaluate("momentum_20d", universe=symbols, forward_days=5)

    assert first.report_path != second.report_path
    assert Path(first.report_path).exists()
    assert Path(second.report_path).exists()
