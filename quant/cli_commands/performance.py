"""Performance profiling CLI commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quant.cli_commands.common import CLIContext, format_optional_number
from quant.performance import PerformanceProfiler
from quant.performance.performance_report import PerformanceReportBuilder


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    profile = subparsers.add_parser("performance-profile", help="Run bounded performance profiling.")
    profile.add_argument("--target", action="append", default=None, help="Profile target; repeatable. Use all for defaults.")
    profile.add_argument("--factor", action="append", default=None, help="Factor to profile; repeatable.")
    profile.add_argument("--max-symbols", type=int, default=5)
    profile.add_argument("--max-factors", type=int, default=2)
    profile.add_argument("--max-folds", type=int, default=1)
    profile.add_argument("--timeout-seconds", type=float, default=180.0)
    profile.add_argument("--workers", type=int, default=1, help="Matrix workers for bulk matrix profiling.")
    profile.add_argument("--bulk-matrix", action=argparse.BooleanOptionalAction, default=True,
        help="Profile the bulk matrix path by default; use --no-bulk-matrix for serial reference diagnostics.")
    profile.add_argument("--strict-in-memory", action="store_true", help="Fail instead of falling back if InMemory provider fails.")

    summary = subparsers.add_parser("performance-summary", help="Show latest performance profile summary.")
    summary.add_argument("--report", default=None)

    report = subparsers.add_parser("performance-report", help="Print latest performance profile report path and key sections.")
    report.add_argument("--report", default=None)


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    if args.command == "performance-profile":
        result = PerformanceProfiler(context).run(
            targets=args.target,
            factors=args.factor,
            max_symbols=args.max_symbols,
            max_factors=args.max_factors,
            max_folds=args.max_folds,
            timeout_seconds=args.timeout_seconds,
            bulk_matrix=args.bulk_matrix,
            workers=args.workers,
            strict_in_memory=args.strict_in_memory,
        )
        _print_profile(result)
        return 0

    if args.command in {"performance-summary", "performance-report"}:
        result = _load_report(args.report)
        if not result:
            print("No performance profile report found.")
            return 1
        _print_profile(result, verbose=args.command == "performance-report")
        return 0

    raise ValueError(f"unsupported performance command: {args.command}")


def _load_report(path: str | None) -> dict | None:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return PerformanceReportBuilder().latest_profile()


def _print_profile(report: dict, verbose: bool = False) -> None:
    print("Performance Profile Summary")
    print(f"status: measured")
    print(f"total_runtime_seconds: {format_optional_number((report.get('summary') or {}).get('total_runtime_seconds'))}")
    print(f"target_count: {(report.get('summary') or {}).get('target_count')}")
    print("slowest_modules:")
    for row in (report.get("slowest_modules") or [])[:5]:
        print(f"{row.get('module')}: {format_optional_number(row.get('runtime_seconds'))}s status={row.get('status')}")
    print("slowest_functions:")
    for row in (report.get("slowest_functions") or [])[:5]:
        print(f"{row.get('category')}:{row.get('name')} {format_optional_number(row.get('runtime_seconds'))}s")
    print("slowest_queries:")
    for row in (report.get("slowest_queries") or [])[:5]:
        print(f"{row.get('name')}: {format_optional_number(row.get('runtime_seconds'))}s calls={row.get('count')}")
    print("recommendations:")
    for item in (report.get("recommendations") or [])[:8]:
        print(f"- {item}")
    provider_rows = [
        row for row in report.get("target_results") or []
        if (row.get("details") or {}).get("provider_type") is not None
    ]
    if provider_rows:
        print("hpc_provider_details:")
        for row in provider_rows:
            details = row.get("details") or {}
            name = row.get("factor") or row.get("strategy") or row.get("target")
            print(
                f"- {row.get('target')} {name}: "
                f"provider_type={details.get('provider_type')} "
                f"cache_strategy={details.get('cache_strategy')} "
                f"fallback_used={details.get('fallback_used')} "
                f"matrix_build_seconds={format_optional_number(details.get('matrix_build_seconds'))} "
                f"eval_seconds={format_optional_number(details.get('eval_seconds'))}"
            )
    if verbose:
        print("target_results:")
        for row in report.get("target_results") or []:
            print(f"- {row.get('target')} {row.get('factor') or row.get('strategy') or ''}: {format_optional_number(row.get('runtime_seconds'))}s")
    print(f"report: {report.get('report_path')}")
    print(f"summary: {report.get('summary_path')}")
