"""CLI commands for historical trading simulation."""

from __future__ import annotations

import argparse
from pathlib import Path

from quant.cli_commands.common import (
    CLIContext,
    format_optional_number,
    format_optional_pct,
    load_alpha_config,
    load_cost_config,
    load_market_realism_config,
)
from quant.engines.portfolio.portfolio_construction import SUPPORTED_METHODS
from quant.engines.trading_simulation.trading_simulator import SUPPORTED_REBALANCE_FREQUENCIES


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "trade-sim",
        help="Run historical account-style trading simulation.",
    )
    parser.add_argument("--strategy", default="alpha", choices=["alpha"])
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-01-01")
    parser.add_argument("--initial-cash", type=float, default=100000.0)
    parser.add_argument("--rebalance-frequency", default="monthly", choices=sorted(SUPPORTED_REBALANCE_FREQUENCIES))
    parser.add_argument("--portfolio-method", default="equal_weight", choices=sorted(SUPPORTED_METHODS))
    parser.add_argument("--cost-config", default="examples/cost_config.json")
    parser.add_argument("--market-realism-config", default="examples/market_realism_config.json")
    parser.add_argument("--alpha-config", default="examples/alpha_config.json")
    parser.add_argument("--execution-price", default="close", choices=["close", "open"])
    parser.add_argument("--symbols", help="Comma-separated symbols overriding alpha config universe.")
    parser.add_argument("--portfolio-lookback", type=int, default=60)


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    symbols = None
    if args.symbols:
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    result = context.trading_simulator.run(
        strategy=args.strategy,
        start=args.start,
        end=args.end,
        initial_cash=args.initial_cash,
        rebalance_frequency=args.rebalance_frequency,
        portfolio_method=args.portfolio_method,
        cost_config=load_cost_config(Path(args.cost_config)),
        market_realism_config=load_market_realism_config(Path(args.market_realism_config)),
        alpha_config=load_alpha_config(Path(args.alpha_config)),
        execution_price=args.execution_price,
        symbols=symbols,
        portfolio_lookback=args.portfolio_lookback,
    )

    print("Trading Simulation Summary")
    print(f"strategy: {result.strategy}")
    print(f"portfolio_method: {result.portfolio_method}")
    print(f"period: {args.start} to {args.end}")
    print(f"no_lookahead: {result.no_lookahead}")
    print(f"initial_cash: {result.initial_cash:.2f}")
    print(f"final_equity: {result.final_equity:.2f}")
    print(f"total_return: {format_optional_pct(result.total_return)}")
    print(f"annual_return: {format_optional_pct(result.annual_return)}")
    print(f"volatility: {format_optional_pct(result.volatility)}")
    print(f"sharpe: {format_optional_number(result.sharpe)}")
    print(f"max_drawdown: {format_optional_pct(result.max_drawdown)}")
    print(f"total_cost: {result.total_cost:.2f}")
    print(f"slippage: {result.market_realism.get('total_slippage', 0.0):.2f}")
    print(f"market_impact: {result.market_realism.get('total_market_impact', 0.0):.2f}")
    print(f"liquidity_cost: {result.market_realism.get('total_liquidity_cost', 0.0):.2f}")
    print(f"rejected_trades: {len(result.rejected_trades)}")
    print(f"turnover: {format_optional_pct(result.turnover)}")
    print(f"trade_count: {result.trade_count}")
    print(f"rebalance_events: {len(result.rebalance_events)}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    print(f"report: {result.report_path}")
    return 0
