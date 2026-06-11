"""Risk CLI command."""

from __future__ import annotations

import sys


def register_parser(subparsers) -> None:
    subparsers.add_parser("risk", help="Calculate portfolio risk metrics.")


def handle(args, context) -> int:
    report = context.risk_engine.analyze()
    print("Risk Summary")
    print(f"total_assets: {report.total_assets:.2f}")
    print(f"cash_weight_pct: {report.cash_weight_pct:.2f}")
    print(f"single_stock_concentration_pct: {report.single_stock_concentration_pct:.2f}")
    print(f"industry_concentration_pct: {report.industry_concentration_pct:.2f}")
    print(f"top_5_holdings_pct: {report.top_5_holdings_pct:.2f}")
    print(f"risk_score: {report.risk_score:.2f}")
    print("holdings:")
    for holding in report.holdings:
        print(
            f"{holding.symbol:<6} {holding.industry:<24} "
            f"value={holding.value:.2f} weight_pct={holding.weight_pct:.2f}"
        )
    print("industries:")
    for industry in report.industries:
        print(
            f"{industry.industry:<24} value={industry.value:.2f} "
            f"weight_pct={industry.weight_pct:.2f}"
        )
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"report: {report.report_path}")
    return 0

