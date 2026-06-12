"""Daily research scheduler CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from quant.cli_commands.common import CLIContext, format_optional_pct
from quant.scheduler.research_scheduler import ResearchScheduler


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    run = subparsers.add_parser("research-run", help="Run the daily offline research pipeline.")
    run.add_argument("--config", default="examples/research_scheduler_config.json")
    run.add_argument("--symbols", default=None, help="Comma or space separated symbols overriding config.")
    run.add_argument("--factor", action="append", dest="factors", help="Factor to evaluate. May be repeated.")
    run.add_argument("--skip-data-refresh", action="store_true")
    run.add_argument("--skip-trade-sim", action="store_true")
    run.add_argument("--skip-visualization", action="store_true")
    run.add_argument("--skip-agent-export", action="store_true")

    subparsers.add_parser("research-status", help="Show latest daily research run status.")

    history = subparsers.add_parser("research-history", help="Show scheduler run history.")
    history.add_argument("--limit", type=int, default=20)

    report = subparsers.add_parser("research-report", help="Show latest or selected daily research run report summary.")
    report.add_argument("--run-id", default=None)


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    scheduler = ResearchScheduler(context, context.db_path)
    if args.command == "research-run":
        overrides = {}
        if args.symbols:
            overrides["symbols"] = args.symbols
        if args.factors:
            overrides["factors"] = args.factors
        if args.skip_data_refresh:
            overrides["run_data_refresh"] = False
        if args.skip_trade_sim:
            overrides["run_trade_sim"] = False
        if args.skip_visualization:
            overrides["run_visualization"] = False
        if args.skip_agent_export:
            overrides["run_agent_export"] = False
        report = scheduler.run(config_path=Path(args.config), overrides=overrides)
        summary = report.get("daily_research_summary") or {}
        trade = summary.get("trade_sim_summary") or {}
        print("Daily Research Run Summary")
        print(f"run_id: {report['run_id']}")
        print(f"status: {report['status']}")
        print(f"duration_seconds: {report['duration_seconds']:.2f}")
        print(f"current_regime: {summary.get('current_regime') or 'UNKNOWN'}")
        print(f"pipeline_mode: {report.get('pipeline_mode') or 'unknown'}")
        print(f"lightweight_default: {str(bool(report.get('lightweight_default'))).lower()}")
        print(f"best_factors: {', '.join(summary.get('best_factors') or []) or 'none'}")
        print(f"weak_factors: {', '.join(summary.get('weak_factors') or []) or 'none'}")
        print(f"trade_sim_return: {format_optional_pct(trade.get('total_return'))}")
        print(f"generated_reports: {len(report.get('generated_reports') or [])}")
        print(f"generated_visualizations: {len(report.get('generated_visualizations') or [])}")
        for warning in report.get("warnings") or []:
            print(f"warning: {warning}")
        print(f"report: {report['report_path']}")
        return 0

    if args.command == "research-status":
        status = scheduler.status()
        latest = status.get("latest_run") or {}
        print("Research Status")
        print(f"status: {status['status']}")
        if latest:
            print(f"run_id: {latest.get('run_id')}")
            print(f"timestamp: {latest.get('timestamp')}")
            print(f"regime: {latest.get('regime')}")
            print(f"trade_sim_return: {format_optional_pct(latest.get('trade_sim_return'))}")
        return 0

    if args.command == "research-history":
        history = scheduler.history(limit=args.limit)
        print("Research History")
        print(f"total_runs: {history['summary']['total_runs']}")
        for row in history["runs"]:
            print(
                f"{row['timestamp']} {row['run_id']} status={row['status']} "
                f"regime={row.get('regime')} trade_sim_return={format_optional_pct(row.get('trade_sim_return'))}"
            )
        return 0

    if args.command == "research-report":
        report = scheduler.latest_report(run_id=args.run_id)
        summary = report.get("daily_research_summary") or {}
        print("Research Report")
        print(f"status: {report.get('status', 'NO_RUNS')}")
        print(f"run_id: {report.get('run_id', 'N/A')}")
        print(f"current_regime: {summary.get('current_regime') or 'UNKNOWN'}")
        print(f"pipeline_mode: {report.get('pipeline_mode') or 'unknown'}")
        print(f"lightweight_default: {str(bool(report.get('lightweight_default'))).lower()}")
        print(f"best_factors: {', '.join(summary.get('best_factors') or []) or 'none'}")
        print(f"warnings: {len(report.get('warnings') or [])}")
        if report.get("report_path"):
            print(f"report: {report['report_path']}")
        return 0

    raise ValueError(f"unsupported scheduler command: {args.command}")
