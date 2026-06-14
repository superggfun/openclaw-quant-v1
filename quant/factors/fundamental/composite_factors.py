"""Cross-family accounting factor composites.

.. warning::
    This module's ``fundamental_composite_score`` averages raw values from four
    family composites (value, quality, growth, health) without cross-sectional
    rank/z-score normalization.  Because value returns large-magnitude numbers
    (1/PE, 1/PB) while quality and growth return small decimals, a raw average
    still suffers from scale mismatch — it is *not* truly scale-agnostic.

    **Preferred approach:** use ``AlphaEngine`` with ``factor_weights`` config
    to combine the four *individual* family factors
    (``fundamental_value_score``, ``fundamental_quality_score``,
    ``fundamental_growth_score``, ``fundamental_health_score``) after proper
    cross-sectional normalization (rank, z-score, or sector-neutral).

    The composite here is provided as a convenience for quick single-stock
    diagnostics, not as the final portfolio-level factor.
"""

from __future__ import annotations

from quant.factors.fundamental.financial_health_factors import financial_health_composite
from quant.factors.fundamental.growth_factors import growth_composite
from quant.factors.fundamental.quality_factors import quality_composite
from quant.factors.fundamental.value_factors import value_composite
from quant.factors.fundamental._utils import mean_available
from quant.factors.specs import fundamental_factor_spec


def fundamental_composite_score(metrics: dict) -> float | None:
    """Average of the four family composites (value, quality, growth, health).

    Requires at least 3 of 4 families to be non-None, otherwise returns None.
    Individual family composites already use ``min_count=2``, so a stock
    needs at least 2 metrics per family.
    """
    families = [
        value_composite(metrics),
        quality_composite(metrics),
        growth_composite(metrics),
        financial_health_composite(metrics),
    ]
    return mean_available(families, min_count=3)


FACTOR_SPECS = (
    fundamental_factor_spec(
        "fundamental_composite_score",
        "fundamental_composite",
        "Average of value, quality, growth, and financial health family composites.  "
        "Requires ≥3 families; individual families require ≥2 metrics each.",
        ["pe_ratio", "pb_ratio", "ev_to_ebitda", "roe", "roa", "gross_margin", "net_margin",
         "revenue_growth", "eps_growth", "debt_to_equity", "current_ratio", "quick_ratio"],
        fundamental_composite_score,
    ),
)
