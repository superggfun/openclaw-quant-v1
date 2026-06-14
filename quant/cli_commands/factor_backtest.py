"""Factor backtest CLI command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quant.cli_commands.common import format_optional_number, format_optional_pct, load_factor_pipeline_config
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS


def register_parser(subparsers) -> None:
    factor_backtest = subparsers.add_parser("factor-backtest", help="Run a long-short factor backtest.")
    factor_backtest.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), required=True)
    factor_backtest.add_argument("--start", default=None, help="Inclusive signal start date YYYY-MM-DD.")
    factor_backtest.add_argument("--end", default=None, help="Inclusive signal end date YYYY-MM-DD.")
    factor_backtest.add_argument("--holding-period", type=int, default=20)
    factor_backtest.add_argument("--quantiles", type=int, default=5)
    factor_backtest.add_argument("--long-quantile", type=int, default=None)
    factor_backtest.add_argument("--short-quantile", type=int, default=1)
    factor_backtest.add_argument("--workers", type=int, default=4, help="Parallel workers for matrix build (default: 4).")
    factor_backtest.add_argument("--bulk-matrix", action=argparse.BooleanOptionalAction, default=True,
        help="Use bulk factor matrix (default: on).  Disable with --no-bulk-matrix for the serial reference path.")
    factor_backtest.add_argument("--serial", action="store_true",
        help="Force the slow serial reference path (implies --no-bulk-matrix for backward compat).")
    factor_backtest.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")
    factor_backtest.add_argument("--report", action="store_true", help="Write JSON report. Reports are written by default.")
    factor_backtest.add_argument("--save-factor-history", action="store_true", help="Persist factor backtest history.")
    factor_backtest.add_argument("--save-regime-history", action="store_true", help="Persist factor backtest diagnostics by current regime history.")


def handle(args, context) -> int:
    bulk = args.bulk_matrix and not args.serial
    if not bulk:
        print("[factor-backtest] Using serial reference path — slow; only intended for debugging.", flush=True)
    result = context.factor_backtest_engine.run(
        factor=args.factor,
        start=args.start,
        end=args.end,
        holding_period=args.holding_period,
        quantiles=args.quantiles,
        long_quantile=args.long_quantile,
        short_quantile=args.short_quantile,
        pipeline_config=load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
        pipeline_config_path=args.pipeline,
        bulk_matrix=bulk,
        max_workers=args.workers,
    )
    print("Factor Backtest Summary")
    print(f"factor: {result.factor}")
    print(f"period: {result.start_date or 'earliest'} to {result.end_date or 'latest'}")
    print(f"holding_period: {result.holding_period}")
    print(f"quantiles: {result.quantiles}")
    print(f"long_quantile: {result.long_quantile}")
    print(f"short_quantile: {result.short_quantile}")
    print(f"no_lookahead: {str(result.no_lookahead).lower()}")
    print(f"signal_execution_lag: {result.signal_execution_lag}")
    print(f"observations: {result.observations}")
    print("quantile_returns:")
    for quantile, value in result.quantile_returns.items():
        print(f"{quantile}: {format_optional_number(value)}")
    print(f"top_quantile_return: {format_optional_number(result.top_quantile_return)}")
    print(f"bottom_quantile_return: {format_optional_number(result.bottom_quantile_return)}")
    print(f"long_short_return: {format_optional_number(result.long_short_return)}")
    print(f"long_short_annual_return: {format_optional_number(result.long_short_annual_return)}")
    print(f"long_short_volatility: {format_optional_number(result.long_short_volatility)}")
    print(f"long_short_sharpe: {format_optional_number(result.long_short_sharpe)}")
    print(f"max_drawdown: {format_optional_number(result.max_drawdown)}")
    print(f"hit_rate: {format_optional_pct(result.hit_rate)}")
    print(f"turnover: {format_optional_number(result.turnover)}")
    print(f"gross_exposure: {format_optional_number(result.gross_exposure)}")
    print(f"net_exposure: {format_optional_number(result.net_exposure)}")
    print(f"ic_mean: {format_optional_number(result.ic_mean)}")
    print(f"rank_ic_mean: {format_optional_number(result.rank_ic_mean)}")
    print(f"icir: {format_optional_number(result.icir)}")
    if result.factor_coverage:
        print("factor_coverage:")
        print(f"coverage_percentage: {format_optional_pct(result.factor_coverage.get('coverage_percentage'))}")
        print(f"missing_percentage: {format_optional_pct(result.factor_coverage.get('missing_percentage'))}")
        print(f"metrics_used: {','.join(result.factor_coverage.get('fundamental_metrics_used') or [])}")
        print(f"no_lookahead_filter: {result.factor_coverage.get('no_lookahead_filter')}")
    if result.excluded_symbols:
        print("excluded_symbols:")
        for symbol in result.excluded_symbols:
            print(f"{symbol}: {result.exclusion_reasons[symbol]}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.save_factor_history:
        context.factor_registry_store.sync()
        saved = context.factor_store.save_factor_backtest(result)
        print("saved_factor_history:")
        print(f"backtest_rows: {saved['saved_backtest_history']}")
        print(f"coverage: {format_optional_pct(saved.get('coverage'))}")
        print(f"confidence: {format_optional_number(saved.get('confidence'))}")
    if args.save_regime_history:
        if context.regime_history_store.latest() is None:
            context.regime_analytics.detect_and_save()
        saved = context.regime_analytics.save_factor_backtest_by_regime(result)
        print("saved_regime_history:")
        print(f"regime_rows: {saved['saved_regime_rows']}")
    print(f"report: {result.report_path}")
    return 0
