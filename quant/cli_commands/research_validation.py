"""CLI command for bounded research validation sprint runs."""

from __future__ import annotations

import argparse

from quant.cli_commands.common import CLIContext, format_optional_number
from quant.engines.execution.cost_engine import COST_PROFILE_NAMES
from quant.research_validation import ResearchValidationRunner


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("research-validation", help="Run bounded research validation sprint workflow.")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--start", default=None, help="Signal-date window start, YYYY-MM-DD. Quick defaults to 2024-01-01.")
    parser.add_argument("--end", default=None, help="Signal-date window end, YYYY-MM-DD. Quick defaults to latest available price date.")
    parser.add_argument("--max-factors", type=int, default=None)
    parser.add_argument("--max-strategies", type=int, default=None)
    parser.add_argument("--max-folds", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--factor-family", choices=["price", "fundamental", "all"], default="all")
    parser.add_argument("--cost-profile", choices=COST_PROFILE_NAMES, default="conservative")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--use-cache", action="store_true", help="Use the opt-in in-memory factor matrix cache for factor-eval steps.")
    parser.add_argument("--bulk-matrix", action=argparse.BooleanOptionalAction, default=True, help="Use semantic-preserving bulk factor observation matrices.")
    parser.add_argument("--parallel", action="store_true", help="Parallelize independent factor batch computations.")
    parser.add_argument(
        "--workers", type=int, default=None,
        help="When --parallel: outer factor-batch workers. "
             "Otherwise: inner matrix-build workers (default: 4)."
    )
    parser.add_argument("--parallel-target", choices=["factor_batch"], default="factor_batch")
    parser.add_argument("--cache-stats", action="store_true", help="Include factor matrix cache diagnostics in the report and CLI output.")
    parser.add_argument("--write-substep-reports", action="store_true", help="Write sub-step reports under the run-specific substeps directory.")
    parser.add_argument("--write-batch-artifacts", action="store_true", help="Write detailed batch artifacts under the run-specific artifacts directory.")
    parser.add_argument("--write-intermediate-reports", action="store_true", help="Allow nested alpha/multi-factor/portfolio/trade-sim intermediate reports under the run-specific substeps directory.")
    parser.add_argument("--write-charts", "--charts", dest="write_charts", action="store_true", help="Generate research-validation charts under the run-specific charts directory.")
    parser.add_argument("--write-debug-logs", action="store_true", help="Reserve run-specific logs directory for debug/HPC logs. Disabled by default.")
    parser.add_argument("--artifact-dir", default=None, help="Run artifact directory. Defaults to reports/runs/<run_id>.")


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    if args.use_cache and args.bulk_matrix:
        raise ValueError("--use-cache and --bulk-matrix are mutually exclusive; pass --no-bulk-matrix to use cache")
    runner = ResearchValidationRunner(context)
    preview = runner.preview(
        mode=args.mode,
        start=args.start,
        end=args.end,
        max_factors=args.max_factors,
        max_strategies=args.max_strategies,
        max_folds=args.max_folds,
        batch_size=args.batch_size,
        max_symbols=args.max_symbols,
        factor_family=args.factor_family,
        parallel=args.parallel,
        workers=args.workers,
    )
    print("Research Validation Plan")
    print(f"mode: {args.mode}")
    print(f"symbols: {preview['symbol_count']}")
    print(f"factors: {preview['factor_count']} ({', '.join(preview['factors'][:10])})")
    print(f"date_range: {preview['effective_start_date']} to {preview['effective_end_date']}")
    print(f"frequency: {preview['frequency']}")
    print(f"trading_days: {preview['trading_day_count']}")
    print(f"forward_days: {preview['forward_days']}")
    print(f"holding_period: {preview['holding_period']}")
    print(f"batch_size: {preview['batch_size']}")
    print(f"batch_count: {preview['batch_count']}")
    print(f"workers: {preview['workers']}")
    print(f"cost_profile: {args.cost_profile}")
    print(f"expected_task_count: {preview['expected_task_count']}")
    print(f"charts_enabled: {str(bool(args.write_charts)).lower()}")
    print(f"write_substep_reports: {str(bool(args.write_substep_reports)).lower()}")
    print(f"write_batch_artifacts: {str(bool(args.write_batch_artifacts)).lower()}")
    print(f"write_intermediate_reports: {str(bool(args.write_intermediate_reports)).lower()}")
    report = runner.run(
        mode=args.mode,
        start=args.start,
        end=args.end,
        max_factors=args.max_factors,
        max_strategies=args.max_strategies,
        max_folds=args.max_folds,
        timeout_seconds=args.timeout_seconds,
        batch_size=args.batch_size,
        max_symbols=args.max_symbols,
        factor_family=args.factor_family,
        cost_profile=args.cost_profile,
        resume=args.resume,
        skip_existing=args.skip_existing,
        use_cache=args.use_cache,
        bulk_matrix=args.bulk_matrix,
        parallel=args.parallel,
        workers=args.workers,
        parallel_target=args.parallel_target,
        cache_stats=args.cache_stats,
        charts=args.write_charts,
        write_substep_reports=args.write_substep_reports,
        write_batch_artifacts=args.write_batch_artifacts,
        write_intermediate_reports=args.write_intermediate_reports,
        write_debug_logs=args.write_debug_logs,
        artifact_dir=args.artifact_dir,
    )
    print("Research Validation Summary")
    print(f"mode: {report['mode']}")
    print(f"status: {report['status']}")
    print(f"partial_results: {str(bool(report['partial_results'])).lower()}")
    print(f"runtime_seconds: {format_optional_number(report['runtime_seconds'])}")
    print(f"date_range: {report.get('effective_start_date')} to {report.get('effective_end_date')}")
    print(f"frequency: {report.get('frequency')}")
    print(f"trading_days: {report.get('trading_day_count')}")
    print(f"charts_enabled: {str(bool(report.get('charts_enabled'))).lower()}")
    print(f"chart_count: {report.get('chart_count')}")
    print(f"run_artifact_dir: {report.get('run_artifact_dir')}")
    print(f"manifest: {report.get('manifest_path')}")
    print(f"completed_steps: {len(report['completed_steps'])}")
    print(f"skipped_steps: {len(report['skipped_steps'])}")
    print(f"timed_out_steps: {len(report['timed_out_steps'])}")
    print(f"current_regime: {report.get('current_regime')}")
    diagnostics = report.get("symbol_diagnostics") or {}
    print(f"symbols_evaluated: {diagnostics.get('selected_symbol_count')}")
    print(f"symbols_skipped: {diagnostics.get('skipped_symbol_count')}")
    print(f"completed_batches: {len((report.get('batching') or {}).get('completed_batches') or [])}")
    print("top_factors:")
    for row in report.get("top_10_factors", [])[:10]:
        print(
            f"{row['factor']}: score={format_optional_number(row.get('evidence_score'))} "
            f"ic={format_optional_number(row.get('ic'))} confidence={format_optional_number(row.get('confidence'))}"
        )
    print("top_strategies:")
    for row in report.get("top_5_strategies", [])[:5]:
        print(
            f"{row.get('strategy')}: gate={row.get('gate_status')} "
            f"return={format_optional_number(row.get('total_return'))} warnings={row.get('warning_count')}"
        )
    print("warnings:")
    for row in report.get("warning_statistics", [])[:10]:
        print(f"{row['code']}: {row['count']}")
    print("slowest_steps:")
    for row in report.get("slowest_steps", [])[:5]:
        print(f"{row['name']} {row['target']}: {format_optional_number(row['runtime_seconds'])}s status={row['status']}")
    print("factor_evidence_summary:")
    for row in report.get("factor_evidence_summary", [])[:5]:
        print(
            f"{row['factor']}: eval_batches={row.get('eval_batches')} "
            f"backtest_batches={row.get('backtest_batches')} observations={row.get('observations')}"
        )
    if args.cache_stats:
        cache_summary = report.get("cache_summary") or {}
        print("cache_summary:")
        print(f"cache_enabled: {str(cache_summary.get('cache_enabled')).lower()}")
        print(f"matrix_hits: {cache_summary.get('matrix_hits', 0)}")
        print(f"matrix_misses: {cache_summary.get('matrix_misses', 0)}")
        print(f"factor_value_hits: {cache_summary.get('factor_value_hits', 0)}")
        print(f"factor_value_misses: {cache_summary.get('factor_value_misses', 0)}")
        print(f"cache_memory_estimate: {cache_summary.get('cache_memory_estimate', 0)}")
    metadata = report.get("performance_metadata") or {}
    if args.cache_stats or args.bulk_matrix or args.parallel:
        print("performance_metadata:")
        print(f"bulk_matrix_enabled: {str(metadata.get('bulk_matrix_enabled')).lower()}")
        print(f"parallel_enabled: {str(metadata.get('parallel_enabled')).lower()}")
        print(f"workers: {metadata.get('workers')}")
        print(f"factor_batches: {metadata.get('factor_batches')}")
        print(f"chart_write_seconds: {format_optional_number(metadata.get('chart_write_seconds'))}")
    print("recommendations:")
    for item in report.get("recommendations", []):
        print(f"- {item}")
    print(f"report: {report['report_path']}")
    print(f"summary: {report['summary_path']}")
    print(f"agent_summary: {report['agent_summary_path']}")
    return 0 if report["status"] in {"PASS", "WARNING"} else 1
