"""Registry metadata for accounting-based fundamental factors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from quant.fundamental_factors.financial_health_factors import (
    current_ratio_factor,
    debt_to_equity_factor,
    financial_health_composite,
    quick_ratio_factor,
)
from quant.fundamental_factors.growth_factors import (
    eps_growth_factor,
    growth_composite,
    revenue_growth_factor,
)
from quant.fundamental_factors.quality_factors import (
    gross_margin_factor,
    net_margin_factor,
    quality_composite,
    roa_quality_factor,
    roe_quality_factor,
)
from quant.fundamental_factors.value_factors import (
    ev_ebitda_factor,
    pb_value_factor,
    pe_value_factor,
    value_composite,
)

FundamentalMetricFunction = Callable[[dict], float | None]


@dataclass(frozen=True)
class FundamentalFactorSpec:
    name: str
    category: str
    description: str
    metrics_used: list[str]
    compute: FundamentalMetricFunction


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


def fundamental_factor_definitions() -> list[FundamentalFactorSpec]:
    return [
        FundamentalFactorSpec("pe_value_factor", "fundamental_value", "Lower PE ratio receives a higher score.", ["pe_ratio"], pe_value_factor),
        FundamentalFactorSpec("pb_value_factor", "fundamental_value", "Lower PB ratio receives a higher score.", ["pb_ratio"], pb_value_factor),
        FundamentalFactorSpec("ev_ebitda_factor", "fundamental_value", "Lower EV/EBITDA receives a higher score.", ["ev_to_ebitda"], ev_ebitda_factor),
        FundamentalFactorSpec("value_composite", "fundamental_value", "Composite of PE, PB, and EV/EBITDA value signals.", ["pe_ratio", "pb_ratio", "ev_to_ebitda"], value_composite),
        FundamentalFactorSpec("fundamental_value_score", "fundamental_value", "Composite accounting-based value score.", ["pe_ratio", "pb_ratio", "ev_to_ebitda"], value_composite),
        FundamentalFactorSpec("roe_quality_factor", "fundamental_quality", "Higher ROE receives a higher score.", ["roe"], roe_quality_factor),
        FundamentalFactorSpec("roa_quality_factor", "fundamental_quality", "Higher ROA receives a higher score.", ["roa"], roa_quality_factor),
        FundamentalFactorSpec("gross_margin_factor", "fundamental_quality", "Higher gross margin receives a higher score.", ["gross_margin"], gross_margin_factor),
        FundamentalFactorSpec("net_margin_factor", "fundamental_quality", "Higher net margin receives a higher score.", ["net_margin"], net_margin_factor),
        FundamentalFactorSpec("quality_composite", "fundamental_quality", "Composite of profitability and margin quality signals.", ["roe", "roa", "gross_margin", "net_margin"], quality_composite),
        FundamentalFactorSpec("fundamental_quality_score", "fundamental_quality", "Composite accounting-based quality score.", ["roe", "roa", "gross_margin", "net_margin"], quality_composite),
        FundamentalFactorSpec("revenue_growth_factor", "fundamental_growth", "Higher revenue growth receives a higher score.", ["revenue_growth"], revenue_growth_factor),
        FundamentalFactorSpec("eps_growth_factor", "fundamental_growth", "Higher EPS growth receives a higher score.", ["eps_growth"], eps_growth_factor),
        FundamentalFactorSpec("growth_composite", "fundamental_growth", "Composite of revenue and EPS growth signals.", ["revenue_growth", "eps_growth"], growth_composite),
        FundamentalFactorSpec("fundamental_growth_score", "fundamental_growth", "Composite accounting-based growth score.", ["revenue_growth", "eps_growth"], growth_composite),
        FundamentalFactorSpec("debt_to_equity_factor", "fundamental_health", "Lower debt-to-equity receives a higher score.", ["debt_to_equity"], debt_to_equity_factor),
        FundamentalFactorSpec("current_ratio_factor", "fundamental_health", "Current ratio closest to 2.0 receives a higher score.", ["current_ratio"], current_ratio_factor),
        FundamentalFactorSpec("quick_ratio_factor", "fundamental_health", "Quick ratio closest to 1.0 receives a higher score.", ["quick_ratio"], quick_ratio_factor),
        FundamentalFactorSpec("financial_health_composite", "fundamental_health", "Composite of leverage and liquidity health signals.", ["debt_to_equity", "current_ratio", "quick_ratio"], financial_health_composite),
        FundamentalFactorSpec("fundamental_health_score", "fundamental_health", "Composite accounting-based financial health score.", ["debt_to_equity", "current_ratio", "quick_ratio"], financial_health_composite),
        FundamentalFactorSpec(
            "fundamental_composite_score",
            "fundamental_composite",
            "Composite of value, quality, growth, and financial health scores.",
            ["pe_ratio", "pb_ratio", "ev_to_ebitda", "roe", "roa", "gross_margin", "net_margin", "revenue_growth", "eps_growth", "debt_to_equity", "current_ratio", "quick_ratio"],
            fundamental_composite_score,
        ),
    ]
