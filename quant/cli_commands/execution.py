"""Execution simulation CLI command."""

from __future__ import annotations

import sys
from pathlib import Path

from quant.cli_commands.common import load_cost_config, load_targets
from quant.engines.execution.cost_engine import COST_PROFILE_NAMES


def register_parser(subparsers) -> None:
    execute_sim = subparsers.add_parser("execute-sim", help="Simulate execution of rebalance suggestions.")
    execute_sim.add_argument("--targets", required=True, help="Path to target allocation JSON.")
    execute_sim.add_argument(
        "--mode",
        choices=["immediate", "next_day_open", "twap", "partial_fill"],
        default="immediate",
    )
    execute_sim.add_argument("--date", default=None, help="Optional execution reference date YYYY-MM-DD.")
    execute_sim.add_argument("--cost-profile", choices=COST_PROFILE_NAMES, default="conservative")
    execute_sim.add_argument("--cost-config", default="examples/cost_config.json")
    execute_sim.add_argument("--twap-slices", type=int, default=4)
    execute_sim.add_argument("--fill-ratio", type=float, default=0.5)


def handle(args, context) -> int:
    targets = load_targets(Path(args.targets))
    cost_config = load_cost_config(Path(args.cost_config), args.cost_profile)
    result = context.execution_engine.run(
        targets=targets,
        mode=args.mode,
        execution_date=args.date,
        cost_config=cost_config,
        twap_slices=args.twap_slices,
        fill_ratio=args.fill_ratio,
    )
    print("Execution Simulation Summary")
    print(f"mode: {result.mode}")
    print(f"intended_trades: {len(result.intended_trades)}")
    print(f"executed_trades: {len(result.executed_trades)}")
    print(f"unfilled_trades: {len(result.unfilled_trades)}")
    print(f"total_cost: {result.execution_costs['total_cost']:.2f}")
    print(f"slippage_estimate: {result.slippage_estimate:.2f}")
    print(f"final_cash: {result.final_cash:.2f}")
    print("executed:")
    for trade in result.executed_trades:
        print(
            f"{trade.side:<4} {trade.symbol:<6} shares={trade.shares} "
            f"price={trade.price:.2f} notional={trade.notional:.2f} "
            f"cost={trade.total_cost:.2f} batch={trade.batch}"
        )
    if result.unfilled_trades:
        print("unfilled:")
        for trade in result.unfilled_trades:
            print(
                f"{trade.side:<4} {trade.symbol:<6} shares={trade.shares} "
                f"price={trade.price:.2f} reason={trade.reason}"
            )
    print("final_positions:")
    for symbol, qty in result.final_positions.items():
        print(f"{symbol:<6} {qty:.6g}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"report: {result.report_path}")
    return 0
