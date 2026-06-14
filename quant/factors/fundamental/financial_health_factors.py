"""Accounting-based financial health factors."""

from __future__ import annotations

from typing import Any

from quant.factors.fundamental._utils import safe_num, mean_available
from quant.factors.specs import fundamental_factor_spec

def debt_to_equity_factor(metrics: dict[str, Any]) -> float | None:
    value = safe_num(metrics.get("debt_to_equity"))
    if value is None or value < 0:
        return None
    return -value

def current_ratio_factor(metrics: dict[str, Any]) -> float | None:
    return _healthy_liquidity_score(metrics.get("current_ratio"), target=2.0)

def quick_ratio_factor(metrics: dict[str, Any]) -> float | None:
    return _healthy_liquidity_score(metrics.get("quick_ratio"), target=1.0)

def financial_health_composite(metrics: dict[str, Any]) -> float | None:
    return mean_available(
        [
            debt_to_equity_factor(metrics),
            current_ratio_factor(metrics),
            quick_ratio_factor(metrics),
        ],
        min_count=2,
    )

fundamental_health_score = financial_health_composite

def _healthy_liquidity_score(value: Any, target: float, tolerance: float = 1.0) -> float | None:
    """Score liquidity with a tolerance band around *target*.

    Values within *tolerance* of the target get a perfect 0; beyond that,
    the score decays linearly with distance.

    .. note::
        This is a rough cross-industry heuristic.  Optimal ratios vary
        widely by sector (retail vs software vs financials).  Prefer
        industry-neutral rank/z-score normalization in the alpha engine.
    """
    number = safe_num(value)
    if number is None or number <= 0:
        return None
    distance = abs(number - target)
    if distance <= tolerance:
        return 0.0
    return -(distance - tolerance)

FACTOR_SPECS = (
    fundamental_factor_spec("debt_to_equity_factor", "fundamental_health", "Lower debt-to-equity receives a higher score.", ["debt_to_equity"], debt_to_equity_factor),
    fundamental_factor_spec("current_ratio_factor", "fundamental_health", "Current ratio near 2.0 (±1.0 tolerance) receives a higher score.", ["current_ratio"], current_ratio_factor),
    fundamental_factor_spec("quick_ratio_factor", "fundamental_health", "Quick ratio near 1.0 (±1.0 tolerance) receives a higher score.", ["quick_ratio"], quick_ratio_factor),
    fundamental_factor_spec("fundamental_health_score", "fundamental_health", "Composite accounting-based financial health score.", ["debt_to_equity", "current_ratio", "quick_ratio"], financial_health_composite),
)
