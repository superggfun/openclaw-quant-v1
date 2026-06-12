"""CLI command for bounded research validation sprint runs."""

from __future__ import annotations

import argparse

from quant.cli_commands.common import CLIContext, format_optional_number
from quant.research_validation import ResearchValidationRunner


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("research-validation", help="Run bounded research validation sprint workflow.")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--max-factors", type=int, default=None)
    parser.add_argument("--max-strategies", type=int, default=None)
    parser.add_argument("--max-folds", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--factor-family", choices=["price", "fundamental", "all"], default="all")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    report = ResearchValidationRunner(context).run(
        mode=args.mode,
        max_factors=args.max_factors,
        max_strategies=args.max_strategies,
        max_folds=args.max_folds,
        timeout_seconds=args.timeout_seconds,
        batch_size=args.batch_size,
        max_symbols=args.max_symbols,
        factor_family=args.factor_family,
        resume=args.resume,
        skip_existing=args.skip_existing,
    )
    print("Research Validation Summary")
    print(f"mode: {report['mode']}")
    print(f"status: {report['status']}")
    print(f"partial_results: {str(bool(report['partial_results'])).lower()}")
    print(f"runtime_seconds: {format_optional_number(report['runtime_seconds'])}")
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
    print("recommendations:")
    for item in report.get("recommendations", []):
        print(f"- {item}")
    print(f"report: {report['report_path']}")
    print(f"summary: {report['summary_path']}")
    print(f"agent_summary: {report['agent_summary_path']}")
    return 0 if report["status"] in {"PASS", "WARNING"} else 1
