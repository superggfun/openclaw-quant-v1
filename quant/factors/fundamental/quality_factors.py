"""Accounting-based quality factors."""

from __future__ import annotations

from typing import Any

from quant.factors.fundamental._utils import safe_num, mean_available
from quant.factors.specs import fundamental_factor_spec

def roe_quality_factor(metrics: dict[str, Any]) -> float | None:
    return safe_num(metrics.get("roe"))

def roa_quality_factor(metrics: dict[str, Any]) -> float | None:
    return safe_num(metrics.get("roa"))

def gross_margin_factor(metrics: dict[str, Any]) -> float | None:
    return safe_num(metrics.get("gross_margin"))

def net_margin_factor(metrics: dict[str, Any]) -> float | None:
    return safe_num(metrics.get("net_margin"))

def quality_composite(metrics: dict[str, Any]) -> float | None:
    return mean_available(
        [
            roe_quality_factor(metrics),
            roa_quality_factor(metrics),
            gross_margin_factor(metrics),
            net_margin_factor(metrics),
        ],
        min_count=2,
    )

fundamental_quality_score = quality_composite

FACTOR_SPECS = (
    fundamental_factor_spec("roe_quality_factor", "fundamental_quality", "Higher ROE receives a higher score.", ["roe"], roe_quality_factor),
    fundamental_factor_spec("roa_quality_factor", "fundamental_quality", "Higher ROA receives a higher score.", ["roa"], roa_quality_factor),
    fundamental_factor_spec("gross_margin_factor", "fundamental_quality", "Higher gross margin receives a higher score.", ["gross_margin"], gross_margin_factor),
    fundamental_factor_spec("net_margin_factor", "fundamental_quality", "Higher net margin receives a higher score.", ["net_margin"], net_margin_factor),
    fundamental_factor_spec("fundamental_quality_score", "fundamental_quality", "Composite accounting-based quality score.", ["roe", "roa", "gross_margin", "net_margin"], quality_composite),
)
