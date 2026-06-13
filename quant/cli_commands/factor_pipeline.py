"""Factor pipeline CLI command."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from quant.cli_commands.common import (
    factor_values_for_pipeline,
    format_optional_number,
    load_factor_pipeline_config,
)
from quant.config import DEFAULT_SYMBOLS
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS
from quant.engines.factor_pipeline.factor_pipeline import FactorPipeline


def register_parser(subparsers) -> None:
    factor_pipeline = subparsers.add_parser("factor-pipeline", help="Run factor preprocessing for one signal date.")
    factor_pipeline.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), required=True)
    factor_pipeline.add_argument("--config", default="examples/factor_pipeline_config.json")
    factor_pipeline.add_argument("--as-of-date", default=None)
    factor_pipeline.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))


def handle(args, context) -> int:
    pipeline_config = load_factor_pipeline_config(Path(args.config))
    raw_values = factor_values_for_pipeline(
        price_store=context.price_store,
        factor=args.factor,
        symbols=args.symbols,
        as_of_date=args.as_of_date,
    )
    result = FactorPipeline(pipeline_config).run(
        raw_values,
        factor=args.factor,
        as_of_date=args.as_of_date or "latest",
    )
    print("Factor Pipeline Summary")
    print(f"factor: {result.factor}")
    print(f"as_of_date: {result.as_of_date}")
    print(f"no_lookahead: {str(result.no_lookahead).lower()}")
    print(f"preprocessing_steps_applied: {', '.join(result.preprocessing_steps_applied)}")
    print("raw_factor_values:")
    for symbol, value in sorted(result.raw_factor_values.items()):
        print(f"{symbol:<6} {format_optional_number(value)}")
    print("cleaned_factor_values:")
    for symbol, value in sorted(result.cleaned_factor_values.items()):
        print(f"{symbol:<6} {value:.6f}")
    print(f"before_summary_statistics: {json.dumps(result.before_summary_statistics, sort_keys=True)}")
    print(f"after_summary_statistics: {json.dumps(result.after_summary_statistics, sort_keys=True)}")
    if result.sector_neutralization_result:
        print("sector_neutralization_result:")
        for sector, metrics in sorted(result.sector_neutralization_result.items()):
            print(f"{sector}: {json.dumps(metrics, sort_keys=True)}")
    if result.excluded_symbols:
        print("excluded_symbols:")
        for symbol in result.excluded_symbols:
            print(f"{symbol}: {result.exclusion_reasons[symbol]}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"report: {result.report_path}")
    return 0

