"""Accounting-based growth factors."""

from __future__ import annotations

from typing import Any

from quant.factors.fundamental._utils import clip_value, mean_available, safe_num
from quant.factors.specs import fundamental_factor_spec

def revenue_growth_factor(metrics: dict[str, Any]) -> float | None:
    return clip_value(safe_num(metrics.get("revenue_growth")), -1.0, 2.0)

def eps_growth_factor(metrics: dict[str, Any]) -> float | None:
    return clip_value(safe_num(metrics.get("eps_growth")), -1.0, 2.0)

def growth_composite(metrics: dict[str, Any]) -> float | None:
    return mean_available(
        [
            revenue_growth_factor(metrics),
            eps_growth_factor(metrics),
        ],
        min_count=2,
    )

fundamental_growth_score = growth_composite

FACTOR_SPECS = (
    fundamental_factor_spec("revenue_growth_factor", "fundamental_growth", "Higher revenue growth receives a higher score (clipped to [-1, 2]).", ["revenue_growth"], revenue_growth_factor),
    fundamental_factor_spec("eps_growth_factor", "fundamental_growth", "Higher EPS growth receives a higher score (clipped to [-1, 2]).", ["eps_growth"], eps_growth_factor),
    fundamental_factor_spec("fundamental_growth_score", "fundamental_growth", "Composite accounting-based growth score.", ["revenue_growth", "eps_growth"], growth_composite),
)
