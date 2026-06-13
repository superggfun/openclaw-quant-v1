"""Portfolio construction CLI command."""

from __future__ import annotations

import sys

from quant.config import DEFAULT_SYMBOLS
from quant.engines.portfolio.portfolio_construction import SUPPORTED_METHODS


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser("portfolio-construct", help="Construct target portfolio weights.")
    parser.add_argument("--method", choices=sorted(SUPPORTED_METHODS), default="equal_weight")
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to construct. Defaults to the project symbol universe.")
    parser.add_argument("--start", default=None, help="Inclusive start date YYYY-MM-DD.")
    parser.add_argument("--end", default=None, help="Inclusive end/as-of date YYYY-MM-DD.")
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument("--min-cash-weight", type=float, default=0.10)
    parser.add_argument("--max-position-weight", type=float, default=0.20)
    parser.add_argument("--max-sector-weight", type=float, default=0.50)
    parser.add_argument("--output-targets", default=None)


def handle(args, context) -> int:
    result = context.portfolio_construction_engine.construct(
        method=args.method,
        symbols=list(args.symbols or DEFAULT_SYMBOLS),
        start=args.start,
        end=args.end,
        lookback=args.lookback,
        min_cash_weight=args.min_cash_weight,
        max_position_weight=args.max_position_weight,
        max_sector_weight=args.max_sector_weight,
        output_targets=args.output_targets,
    )
    print("Portfolio Construction Summary")
    print(f"method: {result.method}")
    print(f"period: {result.start_date or 'earliest'} to {result.end_date or 'latest'}")
    print(f"lookback: {result.lookback}")
    print(f"no_lookahead: {str(result.no_lookahead).lower()}")
    print("symbols_used:")
    for symbol in result.symbols_used:
        print(symbol)
    if result.excluded_symbols:
        print("excluded_symbols:")
        for symbol in result.excluded_symbols:
            print(f"{symbol}: {result.exclusion_reasons[symbol]}")
    print("target_weights:")
    for symbol, weight in result.target_weights.items():
        print(f"{symbol:<6} {weight * 100:>8.2f}%")
    print(f"portfolio_volatility: {_format_optional_number(result.portfolio_volatility)}")
    print("volatility:")
    for symbol, value in result.volatility.items():
        print(f"{symbol:<6} {value:.6f}")
    print("risk_contribution_pct:")
    for symbol, value in result.risk_contribution_pct.items():
        print(f"{symbol:<6} {value * 100:>8.2f}%")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if result.output_targets_path:
        print(f"targets: {result.output_targets_path}")
    print(f"report: {result.report_path}")
    return 0


def _format_optional_number(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"
