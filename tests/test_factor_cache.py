from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.cli_commands.common import create_context
from quant.factor_cache import FactorEvalCache, make_universe_hash
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.research_validation import ResearchValidationRunner
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, symbols: list[str], days: int = 150) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 50 + symbol_index * 20
        trend = 0.12 + symbol_index * 0.08
        for offset in range(days):
            close = base + offset * trend + ((offset % 7) - 3) * 0.04 * (symbol_index + 1)
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
    report_date: str,
    fiscal_period_end: str,
    fiscal_quarter: str,
    roe: float,
) -> None:
    store.upsert(
        "fundamental_metrics",
        {
            "symbol": symbol,
            "fiscal_period_end": fiscal_period_end,
            "report_date": report_date,
            "fiscal_year": int(fiscal_period_end[:4]),
            "fiscal_quarter": fiscal_quarter,
            "currency": "USD",
            "pe_ratio": 20,
            "pb_ratio": 5,
            "ev_to_ebitda": 15,
            "roe": roe,
            "roa": roe / 2,
            "gross_margin": 0.45,
            "net_margin": 0.20,
            "debt_to_equity": 0.5,
            "current_ratio": 2.0,
            "quick_ratio": 1.1,
            "revenue_growth": 0.10,
            "eps_growth": 0.12,
        },
    )


def comparable_report(result) -> dict:
    report = result.to_report()
    report.pop("performance_metadata", None)
    for key in ("cache_enabled", "cache_hits", "cache_misses", "matrix_rows", "matrix_build_seconds", "eval_seconds", "speedup_estimate"):
        report.pop(key, None)
    report.pop("report_path", None)
    return report


def test_cache_key_universe_hash_is_stable_and_order_independent() -> None:
    assert make_universe_hash(["MSFT", "AAPL", "MSFT"]) == make_universe_hash(["AAPL", "MSFT"])
    assert make_universe_hash(["AAPL", "MSFT"]) != make_universe_hash(["AAPL", "NVDA"])


def test_data_newest_date_invalidates_cache_key(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["AAA", "BBB"], days=90)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    before = engine._cache_key("momentum_20d", ["AAA", "BBB"], None, None, 5)

    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "date": "2025-01-01",
                    "open": 10,
                    "high": 10,
                    "low": 10,
                    "close": 10,
                    "adj_close": 10,
                    "volume": 1000,
                }
            ]
        )
    )
    after = engine._cache_key("momentum_20d", ["AAA", "BBB"], None, None, 5)

    assert before != after
    assert before.data_newest_date != after.data_newest_date


def test_cached_factor_eval_matches_uncached_metrics(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    seed_prices(db_path, symbols)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    cache = FactorEvalCache()

    uncached = engine.evaluate(
        "momentum_20d",
        start="2024-02-15",
        end="2024-04-15",
        forward_days=10,
        universe=symbols,
    )
    cached = engine.evaluate(
        "momentum_20d",
        start="2024-02-15",
        end="2024-04-15",
        forward_days=10,
        universe=symbols,
        use_cache=True,
        bulk_matrix=False,
        factor_cache=cache,
        cache_stats=True,
    )

    assert cached.performance_metadata is not None
    assert cached.performance_metadata["cache_misses"] >= 1
    assert comparable_report(cached) == comparable_report(uncached)


def test_repeated_cached_factor_eval_records_hits(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    seed_prices(db_path, symbols)
    engine = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports")
    cache = FactorEvalCache()

    engine.evaluate("momentum_20d", forward_days=5, universe=symbols, use_cache=True, bulk_matrix=False, factor_cache=cache, cache_stats=True)
    second = engine.evaluate("momentum_20d", forward_days=5, universe=symbols, use_cache=True, bulk_matrix=False, factor_cache=cache, cache_stats=True)

    assert second.performance_metadata is not None
    assert second.performance_metadata["cache_hits"] >= 1
    assert second.performance_metadata["cache_misses"] == 0
    assert cache.snapshot()["cached_matrices"] >= 1


def test_fundamental_cache_preserves_report_date_no_lookahead(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    symbols = ["AAA", "BBB", "CCC"]
    seed_prices(db_path, symbols)
    fundamental_store = FundamentalStore(db_path)
    for index, symbol in enumerate(symbols):
        seed_metrics(fundamental_store, symbol, "2024-01-15", "2023-12-31", "FY", roe=0.10 + index * 0.05)
        seed_metrics(fundamental_store, symbol, "2024-05-15", "2024-03-31", "Q1", roe=0.80 - index * 0.05)
    engine = FactorEvaluation(SQLitePriceStore(db_path), fundamental_store, report_dir=tmp_path / "reports")
    cache = FactorEvalCache()

    uncached = engine.evaluate(
        "fundamental_quality_score",
        start="2024-04-01",
        end="2024-04-10",
        forward_days=5,
        universe=symbols,
    )
    cached = engine.evaluate(
        "fundamental_quality_score",
        start="2024-04-01",
        end="2024-04-10",
        forward_days=5,
        universe=symbols,
        use_cache=True,
        bulk_matrix=False,
        factor_cache=cache,
        cache_stats=True,
    )

    assert comparable_report(cached) == comparable_report(uncached)
    for observation in cached.observations:
        assert observation.signal_date < "2024-05-15"
        row = engine.factor_registry.latest_fundamental_row(observation.symbol, "fundamental_metrics", observation.signal_date)
        assert row is not None
        assert row["report_date"] == "2024-01-15"


def test_cache_disabled_behavior_has_performance_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, ["AAA", "BBB", "CCC"])
    result = FactorEvaluation(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").evaluate(
        "momentum_20d",
        forward_days=5,
        universe=["AAA", "BBB", "CCC"],
    )

    # Performance metadata is now populated for all runs (bulk_matrix default)
    assert result.performance_metadata is not None
    assert result.performance_metadata.get("cache_enabled") is False
    assert result.performance_metadata.get("bulk_matrix_enabled") is True


def test_research_validation_cache_stats(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=130)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=1,
        max_strategies=0,
        max_folds=1,
        timeout_seconds=30,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        use_cache=True,
        bulk_matrix=False,
        cache_stats=True,
    )

    assert report["cache_summary"]["cache_enabled"] is True
    assert report["cache_summary"]["matrix_misses"] >= 1
    assert report["parameters"]["use_cache"] is True
