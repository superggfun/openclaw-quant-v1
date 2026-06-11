"""Command line interface for OpenClaw Quant."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quant.cli_commands import (
    alpha,
    backtest,
    cost,
    data,
    execution,
    factor_backtest,
    factor_eval,
    factor_pipeline,
    optimize,
    portfolio,
    portfolio_construction,
    rebalance,
    risk,
    strategy_eval,
)
from quant.cli_commands.common import create_context
from quant.config import DB_PATH


COMMAND_MODULES = [
    data,
    portfolio,
    rebalance,
    risk,
    optimize,
    portfolio_construction,
    alpha,
    factor_eval,
    factor_pipeline,
    factor_backtest,
    strategy_eval,
    cost,
    execution,
    backtest,
]


COMMAND_HANDLERS = {
    "update-prices": data.handle,
    "show-prices": data.handle,
    "list-symbols": data.handle,
    "init-account": portfolio.handle,
    "buy": portfolio.handle,
    "sell": portfolio.handle,
    "portfolio": portfolio.handle,
    "trades": portfolio.handle,
    "allocation": rebalance.handle,
    "rebalance": rebalance.handle,
    "risk": risk.handle,
    "optimize": optimize.handle,
    "portfolio-construct": portfolio_construction.handle,
    "alpha": alpha.handle,
    "factor-eval": factor_eval.handle,
    "factor-pipeline": factor_pipeline.handle,
    "factor-backtest": factor_backtest.handle,
    "strategy-eval": strategy_eval.handle,
    "cost": cost.handle,
    "execute-sim": execution.handle,
    "backtest": backtest.handle,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openclaw-quant")
    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help="SQLite database path. Defaults to data/quant.db.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in COMMAND_MODULES:
        module.register_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = create_context(Path(args.db_path))
    handler = COMMAND_HANDLERS.get(args.command)
    if handler is None:
        raise ValueError(f"Unknown command: {args.command}")

    try:
        return handler(args, context)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
