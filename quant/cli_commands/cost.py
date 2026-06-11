"""Cost CLI command."""

from __future__ import annotations

from pathlib import Path

from quant.cli_commands.common import (
    apply_cost_overrides,
    estimate_costs,
    load_cost_config,
    load_targets,
    print_cost_report,
    trades_from_rebalance_plan,
)


def register_parser(subparsers) -> None:
    cost = subparsers.add_parser("cost", help="Estimate transaction costs for rebalance suggestions.")
    cost.add_argument("--targets", default="examples/optimized_targets.json")
    cost.add_argument("--config", default="examples/cost_config.json")
    cost.add_argument("--model", choices=["fixed", "linear", "combined"], default=None)
    cost.add_argument("--fixed-fee", type=float, default=None)
    cost.add_argument("--commission-rate", type=float, default=None)
    cost.add_argument("--min-commission", type=float, default=None)
    cost.add_argument("--slippage-bps", type=float, default=None)
    cost.add_argument("--min-trade-notional", type=float, default=None)


def handle(args, context) -> int:
    targets = load_targets(Path(args.targets))
    plan = context.rebalance_engine.plan(targets)
    cost_config = load_cost_config(Path(args.config))
    apply_cost_overrides(cost_config, args)
    cost_report = estimate_costs(cost_config, trades_from_rebalance_plan(plan))
    print_cost_report(cost_report)
    return 0

