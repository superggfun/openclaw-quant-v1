"""CLI commands for Strategy DSL definitions."""

from __future__ import annotations

import argparse
from pathlib import Path

from quant.cli_commands.common import CLIContext, format_optional_pct
from quant.strategy_dsl.strategy_registry import StrategyRegistry


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    strategy_list = subparsers.add_parser("strategy-list", help="List Strategy DSL definitions.")
    strategy_list.add_argument("--strategy-dir", default="strategies")

    show = subparsers.add_parser("strategy-show", help="Show a Strategy DSL definition.")
    show.add_argument("--strategy", default="momentum_fundamental")
    show.add_argument("--file", default=None)
    show.add_argument("--strategy-dir", default="strategies")

    validate = subparsers.add_parser("strategy-validate", help="Validate a Strategy DSL definition.")
    validate.add_argument("--strategy", default="momentum_fundamental")
    validate.add_argument("--file", default=None)
    validate.add_argument("--strategy-dir", default="strategies")
    validate.add_argument("--report", action="store_true", help="Write validation report to reports/.")

    run = subparsers.add_parser("strategy-run", help="Run a Strategy DSL definition through offline trade simulation.")
    run.add_argument("--strategy", default="momentum_fundamental")
    run.add_argument("--file", default=None)
    run.add_argument("--strategy-dir", default="strategies")
    run.add_argument("--start", default="2024-01-01")
    run.add_argument("--end", default="2025-01-01")
    run.add_argument("--initial-cash", type=float, default=100000.0)
    run.add_argument("--rebalance-frequency", default="monthly", choices=["daily", "weekly", "monthly"])


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    registry = StrategyRegistry(context, strategy_dir=Path(args.strategy_dir))

    if args.command == "strategy-list":
        result = registry.list_strategies()
        print("Strategies")
        print(f"strategy_count: {result['strategy_count']}")
        for row in result["strategies"]:
            print(
                f"{row.get('name')} version={row.get('version', 'N/A')} "
                f"valid={str(bool(row.get('valid'))).lower()} file={row.get('file')}"
            )
        return 0

    if args.command == "strategy-show":
        result = registry.show(strategy=args.strategy, file=args.file)
        strategy = result["strategy"]
        print("Strategy Definition")
        print(f"name: {strategy['name']}")
        print(f"version: {strategy['version']}")
        print(f"description: {strategy['description']}")
        print(f"factors: {', '.join(item.get('name', '') for item in strategy.get('factors', []))}")
        print(f"portfolio_method: {(strategy.get('portfolio') or {}).get('method', 'equal_weight')}")
        print(f"valid: {str(bool(result['validation']['valid'])).lower()}")
        print(f"source_path: {result['source_path']}")
        return 0

    if args.command == "strategy-validate":
        result = registry.validate(strategy=args.strategy, file=args.file, write_report=args.report)
        print("Strategy Validation")
        print(f"strategy_name: {result['strategy_name']}")
        print(f"strategy_version: {result['strategy_version']}")
        print(f"valid: {str(bool(result['valid'])).lower()}")
        print(f"errors: {len(result['errors'])}")
        print(f"warnings: {len(result['warnings'])}")
        for error in result["errors"]:
            print(f"error: {error}")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
        if result.get("report_path"):
            print(f"report: {result['report_path']}")
        return 0 if result["valid"] else 1

    if args.command == "strategy-run":
        result = registry.run(
            strategy=args.strategy,
            file=args.file,
            start=args.start,
            end=args.end,
            initial_cash=args.initial_cash,
            rebalance_frequency=args.rebalance_frequency,
        )
        summary = result.get("trade_sim_summary") or {}
        print("Strategy Run Summary")
        print(f"strategy_name: {result['strategy_name']}")
        print(f"strategy_version: {result['strategy_version']}")
        print(f"status: {result['status']}")
        print(f"final_equity: {summary.get('final_equity')}")
        print(f"total_return: {format_optional_pct(summary.get('total_return'))}")
        print(f"max_drawdown: {format_optional_pct(summary.get('max_drawdown'))}")
        print(f"trade_count: {summary.get('trade_count')}")
        print(f"trade_sim_report: {(result.get('artifacts') or {}).get('trade_sim_report_path')}")
        print(f"report: {result['report_path']}")
        return 0

    raise ValueError(f"unsupported strategy DSL command: {args.command}")
