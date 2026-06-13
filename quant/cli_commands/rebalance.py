"""Allocation and rebalance CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

from quant.cli_commands.common import (
    estimate_costs,
    format_optional_money,
    load_cost_config,
    load_targets,
    print_cost_report,
    trades_from_rebalance_plan,
)
from quant.engines.portfolio.rebalance_engine import DEFAULT_COMMISSION_RATE


def register_parser(subparsers) -> None:
    subparsers.add_parser("allocation", help="Show current portfolio allocation.")

    rebalance = subparsers.add_parser("rebalance", help="Calculate a portfolio rebalance plan.")
    rebalance.add_argument("--targets", required=True, help="Path to target allocation JSON.")
    rebalance.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_RATE)
    rebalance.add_argument("--with-costs", action="store_true", help="Include transaction cost estimate.")
    rebalance.add_argument("--cost-config", default="examples/cost_config.json")


def handle(args, context) -> int:
    rebalance_engine = context.rebalance_engine

    if args.command == "allocation":
        snapshot = rebalance_engine.allocation()
        print(f"total_assets: {snapshot.total_assets:.2f}")
        print("symbol current_value current_weight_pct qty        price")
        for item in snapshot.items:
            print(
                f"{item.symbol:<6} {item.current_value:>13.2f} "
                f"{item.current_weight * 100:>18.2f} "
                f"{item.qty:>10.6g} {format_optional_money(item.price):>10}"
            )
        return 0

    if args.command == "rebalance":
        targets = load_targets(Path(args.targets))
        plan = rebalance_engine.plan(targets, commission_rate=args.commission)
        print("Rebalance Plan")
        print(f"total_assets: {plan.total_assets:.2f}")
        print(f"cash_before: {plan.cash_before:.2f}")
        print(f"cash_after_rebalance: {plan.cash_after_rebalance:.2f}")
        print(f"estimated_total_commission: {plan.estimated_total_commission:.2f}")
        print(
            "symbol current_value target_value difference "
            "current_pct target_pct action qty est_trade_cost"
        )
        for item in plan.items:
            print(
                f"{item.symbol:<6} {item.current_value:>13.2f} "
                f"{item.target_value:>12.2f} {item.difference:>10.2f} "
                f"{item.current_weight * 100:>11.2f} {item.target_weight * 100:>10.2f} "
                f"{item.action:<6} {item.qty:>5} {item.estimated_trade_cost:>14.2f}"
            )
        suggestions = [item for item in plan.items if item.action in {"BUY", "SELL"} and item.qty > 0]
        if suggestions:
            print("suggestions:")
            for item in suggestions:
                print(f"{item.action} {item.symbol} {item.qty} shares")
        else:
            print("suggestions: no trades")
        for warning in plan.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if args.with_costs:
            cost_config = load_cost_config(Path(args.cost_config))
            cost_report = estimate_costs(cost_config, trades_from_rebalance_plan(plan))
            print_cost_report(cost_report)
        print(f"report: {plan.report_path}")
        return 0

    raise ValueError(f"Unknown rebalance command: {args.command}")

