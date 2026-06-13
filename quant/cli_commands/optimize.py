"""Optimizer CLI command."""

from __future__ import annotations

import sys
from pathlib import Path

from quant.cli_commands.common import load_optimizer_config
from quant.engines.portfolio.optimizer_engine import DEFAULT_CONSTRAINTS


def register_parser(subparsers) -> None:
    optimize = subparsers.add_parser("optimize", help="Generate an optimized target allocation.")
    optimize.add_argument("--config", default="examples/optimizer_config.json")
    optimize.add_argument("--mode", choices=["equal_weight", "risk_adjusted", "constrained"], default=None)
    optimize.add_argument("--output-targets", default=None)
    optimize.add_argument("--max-position-weight", type=float, default=None)
    optimize.add_argument("--min-cash-weight", type=float, default=None)
    optimize.add_argument("--max-sector-weight", type=float, default=None)


def handle(args, context) -> int:
    config = load_optimizer_config(Path(args.config))
    mode = args.mode or config.get("mode", "equal_weight")
    constraints = dict(DEFAULT_CONSTRAINTS)
    constraints.update(config.get("constraints", {}))
    if args.max_position_weight is not None:
        constraints["max_position_weight"] = args.max_position_weight
    if args.min_cash_weight is not None:
        constraints["min_cash_weight"] = args.min_cash_weight
    if args.max_sector_weight is not None:
        constraints["max_sector_weight"] = args.max_sector_weight

    targets_path = args.output_targets or config.get("output_targets", "examples/optimized_targets.json")
    result = context.optimizer_engine.optimize(
        mode=mode,
        symbols=config.get("symbols"),
        constraints=constraints,
        targets_path=targets_path,
    )
    print("Optimizer Summary")
    print(f"mode: {result.mode}")
    print(f"risk_score_before: {result.risk_score_before:.2f}")
    print(f"estimated_risk_score_after: {result.estimated_risk_score_after:.2f}")
    print("optimized_allocation:")
    for symbol, weight in result.optimized_allocation.items():
        print(f"{symbol:<6} {weight * 100:>8.2f}%")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"targets: {result.targets_path}")
    print(f"report: {result.report_path}")
    return 0

