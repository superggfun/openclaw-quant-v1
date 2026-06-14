"""Shared utilities for no-lookahead factor research engines."""

from quant.engines.factor_common.coverage import factor_coverage, factor_coverage_warnings
from quant.engines.factor_common.pipeline import apply_factor_pipeline
from quant.engines.factor_common.reporting import write_factor_report
from quant.engines.factor_common.stats import (
    annual_return,
    annual_volatility,
    compound_return,
    cross_section_correlations,
    cumulative_spread_return,
    hit_rate,
    max_drawdown,
    mean,
    positive_rate,
    sharpe,
    spread_max_drawdown,
    std,
)
from quant.engines.factor_common.symbols import exclude_symbol, normalize_symbols

__all__ = [
    "annual_return",
    "annual_volatility",
    "apply_factor_pipeline",
    "compound_return",
    "cross_section_correlations",
    "cumulative_spread_return",
    "exclude_symbol",
    "factor_coverage",
    "factor_coverage_warnings",
    "hit_rate",
    "max_drawdown",
    "mean",
    "normalize_symbols",
    "positive_rate",
    "sharpe",
    "spread_max_drawdown",
    "std",
    "write_factor_report",
]
