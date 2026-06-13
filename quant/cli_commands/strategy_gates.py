"""CLI commands for Strategy Evaluation Gates."""

from __future__ import annotations

import argparse
from pathlib import Path

from quant.cli_commands.common import CLIContext
from quant.engines.strategy_gates.gate_runner import DEFAULT_GATE_CONFIG_PATH, StrategyGateRunner


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    gate = subparsers.add_parser("strategy-gate", help="Run Strategy Evaluation Gates for an offline strategy.")
    gate.add_argument("--strategy", default="momentum_fundamental")
    gate.add_argument("--file", default=None)
    gate.add_argument("--strategy-dir", default="strategies")
    gate.add_argument("--config", default=str(DEFAULT_GATE_CONFIG_PATH))

    report = subparsers.add_parser("strategy-gate-report", help="Show the latest Strategy Gate report.")
    report.add_argument("--latest", action="store_true", help="Load the latest strategy_gate report.")
    report.add_argument("--strategy-dir", default="strategies")


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    runner = StrategyGateRunner(context, strategy_dir=Path(getattr(args, "strategy_dir", "strategies")))

    if args.command == "strategy-gate":
        result = runner.run(strategy=args.strategy, file=args.file, config_path=args.config)
        _print_gate_report(result)
        return 0 if result.get("overall_status") not in {"FAIL", "REJECTED"} else 1

    if args.command == "strategy-gate-report":
        result = runner.latest_report()
        _print_gate_report(result)
        return 0 if result.get("status") != "NO_REPORTS" else 1

    raise ValueError(f"unsupported strategy gate command: {args.command}")


def _print_gate_report(result: dict) -> None:
    print("Strategy Gate Summary")
    print(f"strategy_name: {result.get('strategy_name')}")
    print(f"strategy_version: {result.get('strategy_version')}")
    print(f"overall_status: {result.get('overall_status') or result.get('status')}")
    print(f"warnings: {len(result.get('warnings') or [])}")
    print(f"rejections: {len(result.get('rejection_reasons') or [])}")
    for gate in result.get("gate_results") or []:
        print(f"gate {gate.get('gate_name')}: {gate.get('status')} {gate.get('reason_code')}")
    for warning in result.get("warnings") or []:
        print(f"warning: {warning}")
    for reason in result.get("rejection_reasons") or []:
        print(f"rejection: {reason}")
    if result.get("report_path"):
        print(f"report: {result['report_path']}")
