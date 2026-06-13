"""Cross-family accounting factor composites."""

from __future__ import annotations

from quant.factors.fundamental.financial_health_factors import financial_health_composite
from quant.factors.fundamental.growth_factors import growth_composite
from quant.factors.fundamental.quality_factors import quality_composite
from quant.factors.fundamental.value_factors import value_composite
from quant.factors.specs import fundamental_factor_spec


def fundamental_composite_score(metrics: dict) -> float | None:
    values = [
        value_composite(metrics),
        quality_composite(metrics),
        growth_composite(metrics),
        financial_health_composite(metrics),
    ]
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


FACTOR_SPECS = (
    fundamental_factor_spec(
        "fundamental_composite_score",
        "fundamental_composite",
        "Composite of value, quality, growth, and financial health scores.",
        ["pe_ratio", "pb_ratio", "ev_to_ebitda", "roe", "roa", "gross_margin", "net_margin", "revenue_growth", "eps_growth", "debt_to_equity", "current_ratio", "quick_ratio"],
        fundamental_composite_score,
    ),
)
