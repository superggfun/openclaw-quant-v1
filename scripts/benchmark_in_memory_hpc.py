"""Benchmark SQLite bulk vs InMemory HPC research providers.

The benchmark is diagnostics-only: it runs existing no-lookahead factor
evaluation, factor backtest, and research-validation paths without changing
factor values, labels, IC, rank IC, decay IC, or backtest semantics.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from quant.cli_commands.common import create_context
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.research_validation import ResearchValidationRunner
from quant.storage.sqlite_store import SQLitePriceStore


DEFAULT_DECAY_HORIZONS = [1, 5, 10, 20, 60]


@dataclass(frozen=True)
class BenchmarkRow:
    scenario: str
    provider: str
    wall_time_seconds: float
    speedup_vs_sqlite: float | None
    provider_type: str | None
    cache_strategy: str | None
    fallback_used: bool | None
    matrix_workers: int | None
    matrix_build_seconds: float | None
    eval_seconds: float | None
    observations: int | None
    ic_mean: float | None
    rank_ic_mean: float | None
    decay_ic: dict[str, float | None] | None


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    db_path = prepare_database(args, output_dir, stamp)
    symbols = select_symbols(db_path, args)

    rows: list[BenchmarkRow] = []
    rows.extend(benchmark_factor_eval_pair(args, db_path, symbols, args.price_factor, "price_factor"))
    rows.extend(benchmark_factor_eval_pair(args, db_path, symbols, args.fundamental_factor, "fundamental_factor"))
    rows.extend(benchmark_backtest_pair(args, db_path, symbols, args.price_factor))
    rows.extend(benchmark_research_validation_pair(args, db_path, symbols))
    rows = attach_speedups(rows)

    payload = {
        "benchmark": "in_memory_hpc",
        "db_path": str(db_path),
        "symbols": symbols,
        "start": args.start,
        "end": args.end,
        "matrix_workers": args.matrix_workers,
        "strict_in_memory": True,
        "rows": [asdict(row) for row in rows],
    }
    output_path = output_dir / f"in_memory_hpc_benchmark_{stamp}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print_table(rows)
    print(f"\nWrote benchmark JSON: {output_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark SQLite bulk vs InMemory HPC research providers.")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite DB to benchmark. Defaults to a generated synthetic DB.")
    parser.add_argument("--use-existing-db", action="store_true", help="Use --db-path as-is instead of generating synthetic data.")
    parser.add_argument("--output-dir", default="reports/benchmarks", help="Directory for benchmark JSON output.")
    parser.add_argument("--symbol-count", type=int, default=40, help="Synthetic symbol count or existing-DB max symbols.")
    parser.add_argument("--days", type=int, default=260, help="Synthetic price history length.")
    parser.add_argument("--start", default="2024-04-01", help="Benchmark start date.")
    parser.add_argument("--end", default="2024-08-31", help="Benchmark end date.")
    parser.add_argument("--price-factor", default="momentum_20d", help="Price factor to benchmark.")
    parser.add_argument("--fundamental-factor", default="pe_value_factor", help="Fundamental factor to benchmark.")
    parser.add_argument("--forward-days", type=int, default=20, help="Factor eval forward return horizon.")
    parser.add_argument("--holding-period", type=int, default=20, help="Factor backtest holding period.")
    parser.add_argument("--matrix-workers", type=int, default=1, help="Inner matrix workers.")
    parser.add_argument("--rv-timeout", type=float, default=60.0, help="Research-validation quick timeout.")
    return parser.parse_args()


def prepare_database(args: argparse.Namespace, output_dir: Path, stamp: str) -> Path:
    if args.use_existing_db:
        if args.db_path is None:
            raise ValueError("--use-existing-db requires --db-path")
        return Path(args.db_path)
    db_path = Path(args.db_path) if args.db_path else output_dir / f"in_memory_hpc_synthetic_{stamp}.db"
    seed_synthetic_database(db_path, symbol_count=args.symbol_count, days=args.days)
    return db_path


def seed_synthetic_database(db_path: Path, symbol_count: int, days: int) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    symbols = [f"S{index:04d}" for index in range(symbol_count)]
    price_rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 50.0 + symbol_index * 0.9
        trend = 0.04 + (symbol_index % 11) * 0.006
        for offset in range(days):
            wave = ((offset % 17) - 8) * 0.015 * (1 + (symbol_index % 5))
            close = base + offset * trend + wave
            price_rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 100_000 + offset + symbol_index,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(price_rows))
    fundamentals = FundamentalStore(db_path)
    for symbol_index, symbol in enumerate(symbols):
        seed_metric_row(
            fundamentals,
            symbol,
            report_date="2024-01-20",
            fiscal_period_end="2023-12-31",
            fiscal_quarter="FY",
            pe_ratio=10 + (symbol_index % 23),
            roe=0.08 + (symbol_index % 9) * 0.015,
            revenue_growth=0.02 + (symbol_index % 7) * 0.01,
        )
        seed_metric_row(
            fundamentals,
            symbol,
            report_date="2024-05-20",
            fiscal_period_end="2024-03-31",
            fiscal_quarter="Q1",
            pe_ratio=8 + (symbol_index % 19),
            roe=0.10 + (symbol_index % 11) * 0.012,
            revenue_growth=0.03 + (symbol_index % 5) * 0.012,
        )


def seed_metric_row(
    store: FundamentalStore,
    symbol: str,
    report_date: str,
    fiscal_period_end: str,
    fiscal_quarter: str,
    **overrides: Any,
) -> None:
    row = {
        "symbol": symbol,
        "fiscal_period_end": fiscal_period_end,
        "report_date": report_date,
        "fiscal_year": int(fiscal_period_end[:4]),
        "fiscal_quarter": fiscal_quarter,
        "currency": "USD",
        "pe_ratio": 20.0,
        "pb_ratio": 4.0,
        "ev_to_ebitda": 12.0,
        "roe": 0.15,
        "roa": 0.08,
        "gross_margin": 0.45,
        "net_margin": 0.18,
        "debt_to_equity": 0.6,
        "current_ratio": 1.8,
        "quick_ratio": 1.1,
        "revenue_growth": 0.08,
        "eps_growth": 0.09,
    }
    row.update(overrides)
    store.upsert("fundamental_metrics", row)


def select_symbols(db_path: Path, args: argparse.Namespace) -> list[str]:
    symbols = SQLitePriceStore(db_path).list_symbols()[: max(1, args.symbol_count)]
    if not symbols:
        raise ValueError(f"no symbols found in {db_path}")
    return symbols


def benchmark_factor_eval_pair(
    args: argparse.Namespace,
    db_path: Path,
    symbols: list[str],
    factor: str,
    scenario: str,
) -> list[BenchmarkRow]:
    return [
        benchmark_factor_eval(args, db_path, symbols, factor, scenario, "sqlite"),
        benchmark_factor_eval(args, db_path, symbols, factor, scenario, "in_memory"),
    ]


def benchmark_factor_eval(
    args: argparse.Namespace,
    db_path: Path,
    symbols: list[str],
    factor: str,
    scenario: str,
    provider: str,
) -> BenchmarkRow:
    engine = FactorEvaluation(SQLitePriceStore(db_path), FundamentalStore(db_path), report_dir=Path(args.output_dir))
    started = time.perf_counter()
    result = engine.evaluate(
        factor=factor,
        start=args.start,
        end=args.end,
        forward_days=args.forward_days,
        universe=symbols,
        bulk_matrix=True,
        max_workers=args.matrix_workers,
        decay_horizons=DEFAULT_DECAY_HORIZONS,
        prefer_in_memory=provider == "in_memory",
        strict_in_memory=provider == "in_memory",
        cache_stats=True,
        write_report=False,
    )
    wall = time.perf_counter() - started
    metadata = result.performance_metadata or {}
    return BenchmarkRow(
        scenario=scenario,
        provider=provider,
        wall_time_seconds=round(wall, 6),
        speedup_vs_sqlite=None,
        provider_type=metadata.get("provider_type"),
        cache_strategy=metadata.get("cache_strategy"),
        fallback_used=metadata.get("fallback_used"),
        matrix_workers=metadata.get("matrix_workers"),
        matrix_build_seconds=metadata.get("matrix_build_seconds"),
        eval_seconds=metadata.get("eval_seconds"),
        observations=len(result.observations),
        ic_mean=result.ic_mean,
        rank_ic_mean=result.rank_ic_mean,
        decay_ic={key: value.get("ic") for key, value in result.decay.items()},
    )


def benchmark_backtest_pair(args: argparse.Namespace, db_path: Path, symbols: list[str], factor: str) -> list[BenchmarkRow]:
    return [
        benchmark_backtest(args, db_path, symbols, factor, "sqlite"),
        benchmark_backtest(args, db_path, symbols, factor, "in_memory"),
    ]


def benchmark_backtest(
    args: argparse.Namespace,
    db_path: Path,
    symbols: list[str],
    factor: str,
    provider: str,
) -> BenchmarkRow:
    engine = FactorBacktest(SQLitePriceStore(db_path), FundamentalStore(db_path), report_dir=Path(args.output_dir))
    started = time.perf_counter()
    result = engine.run(
        factor=factor,
        start=args.start,
        end=args.end,
        holding_period=args.holding_period,
        universe=symbols,
        bulk_matrix=True,
        max_workers=args.matrix_workers,
        prefer_in_memory=provider == "in_memory",
        strict_in_memory=provider == "in_memory",
        write_report=False,
    )
    wall = time.perf_counter() - started
    metadata = result.performance_metadata or {}
    return BenchmarkRow(
        scenario="factor_backtest",
        provider=provider,
        wall_time_seconds=round(wall, 6),
        speedup_vs_sqlite=None,
        provider_type=metadata.get("provider_type"),
        cache_strategy=metadata.get("cache_strategy"),
        fallback_used=metadata.get("fallback_used"),
        matrix_workers=metadata.get("matrix_workers"),
        matrix_build_seconds=metadata.get("matrix_build_seconds"),
        eval_seconds=None,
        observations=result.observations,
        ic_mean=result.ic_mean,
        rank_ic_mean=result.rank_ic_mean,
        decay_ic=None,
    )


def benchmark_research_validation_pair(args: argparse.Namespace, db_path: Path, symbols: list[str]) -> list[BenchmarkRow]:
    return [
        benchmark_research_validation(args, db_path, symbols, "sqlite"),
        benchmark_research_validation(args, db_path, symbols, "in_memory"),
    ]


def benchmark_research_validation(
    args: argparse.Namespace,
    db_path: Path,
    symbols: list[str],
    provider: str,
) -> BenchmarkRow:
    run_db = clone_db_for_research_validation(db_path, Path(args.output_dir), provider)
    context = create_context(run_db)
    runner = ResearchValidationRunner(context, report_dir=Path(args.output_dir) / f"rv_{provider}")
    started = time.perf_counter()
    report = runner.run(
        mode="quick",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=args.rv_timeout,
        batch_size=len(symbols),
        max_symbols=len(symbols),
        factor_family="price",
        bulk_matrix=True,
        parallel=False,
        workers=args.matrix_workers,
        prefer_in_memory=provider == "in_memory",
        strict_in_memory=provider == "in_memory",
        write_substep_reports=False,
        write_batch_artifacts=False,
    )
    wall = time.perf_counter() - started
    eval_result = (report.get("factor_eval_results") or [{}])[0]
    eval_metadata = eval_result.get("performance_metadata") or {}
    perf = report.get("performance_metadata") or {}
    return BenchmarkRow(
        scenario="research_validation_quick",
        provider=provider,
        wall_time_seconds=round(wall, 6),
        speedup_vs_sqlite=None,
        provider_type=first_not_none(eval_metadata.get("provider_type"), perf.get("preferred_provider_type")),
        cache_strategy=first_not_none(eval_metadata.get("cache_strategy"), perf.get("cache_strategy")),
        fallback_used=first_not_none(eval_metadata.get("fallback_used"), perf.get("fallback_used")),
        matrix_workers=first_not_none(eval_metadata.get("matrix_workers"), perf.get("matrix_workers")),
        matrix_build_seconds=first_not_none(eval_metadata.get("matrix_build_seconds"), perf.get("matrix_build_seconds")),
        eval_seconds=eval_metadata.get("eval_seconds"),
        observations=eval_result.get("observation_count"),
        ic_mean=eval_result.get("ic_mean"),
        rank_ic_mean=eval_result.get("rank_ic_mean"),
        decay_ic=None,
    )


def clone_db_for_research_validation(db_path: Path, output_dir: Path, provider: str) -> Path:
    target = output_dir / f"rv_{provider}_{time.time_ns()}.db"
    shutil.copy2(db_path, target)
    return target


def attach_speedups(rows: list[BenchmarkRow]) -> list[BenchmarkRow]:
    sqlite_times = {row.scenario: row.wall_time_seconds for row in rows if row.provider == "sqlite"}
    output = []
    for row in rows:
        baseline = sqlite_times.get(row.scenario)
        speedup = None
        if baseline and row.wall_time_seconds > 0:
            speedup = round(baseline / row.wall_time_seconds, 6)
        output.append(BenchmarkRow(**(asdict(row) | {"speedup_vs_sqlite": speedup})))
    return output


def print_table(rows: list[BenchmarkRow]) -> None:
    headers = [
        "scenario",
        "provider",
        "wall_s",
        "speedup",
        "provider_type",
        "cache_strategy",
        "fallback",
        "workers",
        "matrix_s",
        "eval_s",
        "obs",
        "ic",
        "rank_ic",
    ]
    print(" | ".join(headers))
    print(" | ".join("-" * len(header) for header in headers))
    for row in rows:
        values = [
            row.scenario,
            row.provider,
            fmt(row.wall_time_seconds),
            fmt(row.speedup_vs_sqlite),
            str(row.provider_type),
            str(row.cache_strategy),
            str(row.fallback_used),
            str(row.matrix_workers),
            fmt(row.matrix_build_seconds),
            fmt(row.eval_seconds),
            str(row.observations),
            fmt(row.ic_mean),
            fmt(row.rank_ic_mean),
        ]
        print(" | ".join(values))


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
