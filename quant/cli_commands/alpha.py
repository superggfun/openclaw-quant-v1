"""Alpha CLI command."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from quant.cli_commands.common import (
    format_optional_number,
    format_optional_rank,
    load_alpha_config,
    load_factor_pipeline_config,
)


def register_parser(subparsers) -> None:
    alpha = subparsers.add_parser("alpha", help="Generate alpha factors and target weights.")
    alpha.add_argument("--config", default="examples/alpha_config.json")
    alpha.add_argument("--output-targets", default=None)
    alpha.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")


def handle(args, context) -> int:
    config = load_alpha_config(Path(args.config))
    pipeline_config = load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None
    result = context.alpha_engine.generate(
        config=config,
        output_targets=args.output_targets,
        pipeline_config=pipeline_config,
    )
    print("Alpha Summary")
    print(f"as_of_date: {result.as_of_date or 'latest'}")
    print(f"data_start_date: {result.data_start_date or 'N/A'}")
    print(f"data_end_date: {result.data_end_date or 'N/A'}")
    print(f"lookback_used: {json.dumps(result.lookback_used, sort_keys=True)}")
    print(f"suggested_execution_date: {result.suggested_execution_date or 'next_available_session'}")
    print(f"weighting_mode: {result.config['weighting_mode']}")
    if result.config.get("target_weighting_mode") and result.config["target_weighting_mode"] != result.config["weighting_mode"]:
        print(f"target_weighting_mode: {result.config['target_weighting_mode']}")
    if result.multi_factor_summary:
        confidence = result.multi_factor_summary.get("confidence") or {}
        print("multi_factor:")
        print(f"weighting_mode: {result.multi_factor_summary.get('weighting_mode')}")
        print(f"overall_confidence: {format_optional_number(confidence.get('overall_confidence'))}")
    print("factors:")
    print(
        "symbol rank selected excluded momentum_20d momentum_60d volatility_20d "
        "risk_adjusted_momentum composite_alpha_score overall_confidence family_contributions factor_contributions"
    )
    for row in result.factors:
        print(
            f"{row.symbol:<6} {format_optional_rank(row.rank):>4} "
            f"{str(row.selected):<8} "
            f"{str(row.excluded):<8} "
            f"{format_optional_number(row.momentum_20d):>12} "
            f"{format_optional_number(row.momentum_60d):>12} "
            f"{format_optional_number(row.volatility_20d):>14} "
            f"{format_optional_number(row.risk_adjusted_momentum):>23} "
            f"{format_optional_number(row.composite_alpha_score):>21} "
            f"{format_optional_number(row.overall_confidence):>18} "
            f"{json.dumps(row.family_contributions or {}, sort_keys=True)} "
            f"{json.dumps(row.factor_contributions or {}, sort_keys=True)}"
        )
    if result.excluded_symbols:
        print("excluded_symbols:")
        for symbol in result.excluded_symbols:
            print(f"{symbol}: {result.exclusion_reasons[symbol]}")
    print("selected_symbols:")
    for symbol in result.selected_symbols:
        print(symbol)
    print("target_weights:")
    for symbol, weight in result.target_weights.items():
        print(f"{symbol:<6} {weight * 100:>8.2f}%")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if result.pipeline_report_path:
        print(f"pipeline_report: {result.pipeline_report_path}")
    if result.multi_factor_report_path:
        print(f"multi_factor_report: {result.multi_factor_report_path}")
    if result.targets_path:
        print(f"targets: {result.targets_path}")
    print(f"report: {result.report_path}")
    return 0
