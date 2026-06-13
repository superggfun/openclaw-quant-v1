"""Alpha CLI command."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from quant.cli_commands.common import (
    format_optional_number,
    format_optional_rank,
    load_alpha_config,
    load_factor_pipeline_config,
)

logger = logging.getLogger(__name__)


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
    logger.info("Alpha Summary")
    logger.info("as_of_date: %s", result.as_of_date or 'latest')
    logger.info("data_start_date: %s", result.data_start_date or 'N/A')
    logger.info("data_end_date: %s", result.data_end_date or 'N/A')
    logger.info("lookback_used: %s", json.dumps(result.lookback_used, sort_keys=True))
    logger.info("suggested_execution_date: %s", result.suggested_execution_date or 'next_available_session')
    logger.info("weighting_mode: %s", result.config['weighting_mode'])
    if result.config.get("target_weighting_mode") and result.config["target_weighting_mode"] != result.config["weighting_mode"]:
        logger.info("target_weighting_mode: %s", result.config['target_weighting_mode'])
    if result.multi_factor_summary:
        confidence = result.multi_factor_summary.get("confidence") or {}
        logger.info("multi_factor:")
        logger.info("weighting_mode: %s", result.multi_factor_summary.get('weighting_mode'))
        logger.info("overall_confidence: %s", format_optional_number(confidence.get('overall_confidence')))
    logger.info("factors:")
    logger.info(
        "symbol rank selected excluded momentum_20d momentum_60d volatility_20d "
        "risk_adjusted_momentum composite_alpha_score overall_confidence family_contributions factor_contributions"
    )
    for row in result.factors:
        logger.info(
            "%s %s %s %s %s %s %s %s %s %s %s %s",
            f"{row.symbol:<6}",
            f"{format_optional_rank(row.rank):>4}",
            f"{str(row.selected):<8}",
            f"{str(row.excluded):<8}",
            f"{format_optional_number(row.momentum_20d):>12}",
            f"{format_optional_number(row.momentum_60d):>12}",
            f"{format_optional_number(row.volatility_20d):>14}",
            f"{format_optional_number(row.risk_adjusted_momentum):>23}",
            f"{format_optional_number(row.composite_alpha_score):>21}",
            f"{format_optional_number(row.overall_confidence):>18}",
            json.dumps(row.family_contributions or {}, sort_keys=True),
            json.dumps(row.factor_contributions or {}, sort_keys=True),
        )
    if result.excluded_symbols:
        logger.info("excluded_symbols:")
        for symbol in result.excluded_symbols:
            logger.info("%s: %s", symbol, result.exclusion_reasons[symbol])
    logger.info("selected_symbols:")
    for symbol in result.selected_symbols:
        logger.info(symbol)
    logger.info("target_weights:")
    for symbol, weight in result.target_weights.items():
        logger.info("%s %s%%", f"{symbol:<6}", f"{weight * 100:>8.2f}")
    for warning in result.warnings:
        logger.warning("warning: %s", warning)
    if result.pipeline_report_path:
        logger.info("pipeline_report: %s", result.pipeline_report_path)
    if result.multi_factor_report_path:
        logger.info("multi_factor_report: %s", result.multi_factor_report_path)
    if result.targets_path:
        logger.info("targets: %s", result.targets_path)
    logger.info("report: %s", result.report_path)
    return 0
