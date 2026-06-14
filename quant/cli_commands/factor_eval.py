"""Factor evaluation CLI command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quant.cli_commands.common import format_optional_number, format_optional_pct, load_factor_pipeline_config
from quant.factor_cache import FactorEvalCache
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS


def register_parser(subparsers) -> None:
    factor_eval = subparsers.add_parser("factor-eval", help="Evaluate alpha factor predictive quality.")
    factor_eval.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), required=True)
    factor_eval.add_argument("--start", default=None, help="Inclusive signal start date YYYY-MM-DD.")
    factor_eval.add_argument("--end", default=None, help="Inclusive signal end date YYYY-MM-DD.")
    factor_eval.add_argument("--forward-days", type=int, default=20)
    factor_eval.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")
    factor_eval.add_argument("--use-cache", action="store_true", help="Use the opt-in in-memory factor matrix cache.")
    factor_eval.add_argument("--cache-stats", action="store_true", help="Print factor matrix cache diagnostics.")
    factor_eval.add_argument("--workers", type=int, default=4, help="Parallel workers for matrix build (default: 4).")
    factor_eval.add_argument("--bulk-matrix", action=argparse.BooleanOptionalAction, default=True,
        help="Use bulk factor matrix (default: on).  Disable with --no-bulk-matrix for the serial reference path.")
    factor_eval.add_argument("--serial", action="store_true",
        help="Force the slow serial reference path (implies --no-bulk-matrix for backward compat).")
    factor_eval.add_argument("--save-factor-history", action="store_true", help="Persist factor values and evaluation history.")
    factor_eval.add_argument("--save-regime-history", action="store_true", help="Persist factor diagnostics by current regime history.")


def handle(args, context) -> int:
    bulk = args.bulk_matrix and not args.serial
    if not bulk:
        print("[factor-eval] Using serial reference path — slow; only intended for debugging.", flush=True)
    result = context.factor_evaluation.evaluate(
        factor=args.factor,
        start=args.start,
        end=args.end,
        forward_days=args.forward_days,
        pipeline_config=load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
        use_cache=args.use_cache,
        factor_cache=FactorEvalCache() if args.use_cache else None,
        bulk_matrix=bulk,
        max_workers=args.workers,
        cache_stats=args.cache_stats,
    )
    print("Factor Evaluation Summary")
    print(f"factor: {result.factor}")
    print(f"period: {result.start_date or 'earliest'} to {result.end_date or 'latest'}")
    print(f"forward_days: {result.forward_days}")
    print(f"no_lookahead: {str(result.no_lookahead).lower()}")
    print(f"observations: {len(result.observations)}")
    print(f"ic_mean: {format_optional_number(result.ic_mean)}")
    print(f"ic_std: {format_optional_number(result.ic_std)}")
    print(f"ic_positive_rate: {format_optional_pct(result.ic_positive_rate)}")
    print(f"ic_count: {result.ic_count}")
    print(f"rank_ic_mean: {format_optional_number(result.rank_ic_mean)}")
    print(f"rank_ic_std: {format_optional_number(result.rank_ic_std)}")
    print(f"rank_ic_positive_rate: {format_optional_pct(result.rank_ic_positive_rate)}")
    print(f"icir: {format_optional_number(result.icir)}")
    print("quintiles:")
    for quintile in ["q1", "q2", "q3", "q4", "q5"]:
        print(f"{quintile}: {format_optional_number(result.quintiles.get(quintile))}")
    print(f"spread_return: {format_optional_number(result.spread_return)}")
    if result.factor_coverage:
        print("factor_coverage:")
        print(f"coverage_percentage: {format_optional_pct(result.factor_coverage.get('coverage_percentage'))}")
        print(f"missing_percentage: {format_optional_pct(result.factor_coverage.get('missing_percentage'))}")
        print(f"metrics_used: {','.join(result.factor_coverage.get('fundamental_metrics_used') or [])}")
        print(f"no_lookahead_filter: {result.factor_coverage.get('no_lookahead_filter')}")
    if args.cache_stats and result.performance_metadata:
        stats = result.performance_metadata.get("cache_stats") or {}
        print("cache_stats:")
        print(f"cache_enabled: {str(result.performance_metadata.get('cache_enabled')).lower()}")
        print(f"matrix_hits: {stats.get('matrix_hits', 0)}")
        print(f"matrix_misses: {stats.get('matrix_misses', 0)}")
        print(f"factor_value_hits: {stats.get('factor_value_hits', 0)}")
        print(f"factor_value_misses: {stats.get('factor_value_misses', 0)}")
        print(f"future_return_hits: {stats.get('future_return_hits', 0)}")
        print(f"future_return_misses: {stats.get('future_return_misses', 0)}")
        print(f"cache_memory_estimate: {stats.get('cache_memory_estimate', 0)}")
        print(f"matrix_rows: {result.performance_metadata.get('matrix_rows')}")
        print(f"eval_seconds: {format_optional_number(result.performance_metadata.get('eval_seconds'))}")
    print("decay:")
    for horizon, metrics in result.decay.items():
        print(
            f"{horizon}: ic={format_optional_number(metrics['ic'])} "
            f"rank_ic={format_optional_number(metrics['rank_ic'])} "
            f"ic_count={metrics['ic_count']}"
        )
    if result.excluded_symbols:
        print("excluded_symbols:")
        for symbol in result.excluded_symbols:
            print(f"{symbol}: {result.exclusion_reasons[symbol]}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.save_factor_history:
        context.factor_registry_store.sync()
        saved = context.factor_store.save_factor_evaluation(result)
        print("saved_factor_history:")
        print(f"factor_values: {saved['saved_factor_values']}")
        print(f"coverage: {format_optional_pct(saved.get('coverage'))}")
        print(f"confidence: {format_optional_number(saved.get('confidence'))}")
    if args.save_regime_history:
        if context.regime_history_store.latest() is None:
            context.regime_analytics.detect_and_save()
        saved = context.regime_analytics.save_factor_evaluation_by_regime(result)
        print("saved_regime_history:")
        print(f"regime_rows: {saved['saved_regime_rows']}")
    print(f"report: {result.report_path}")
    return 0
