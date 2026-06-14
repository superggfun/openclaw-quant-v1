"""Accounting-based value factors."""

from __future__ import annotations

from typing import Any

from quant.factors.fundamental._utils import safe_num, mean_available
from quant.factors.specs import fundamental_factor_spec

def pe_value_factor(metrics: dict[str, Any]) -> float | None:
    return _to_earnings_yield(metrics.get("pe_ratio"))

def pb_value_factor(metrics: dict[str, Any]) -> float | None:
    return _to_earnings_yield(metrics.get("pb_ratio"))

def ev_ebitda_factor(metrics: dict[str, Any]) -> float | None:
    return _to_earnings_yield(metrics.get("ev_to_ebitda"))

def value_composite(metrics: dict[str, Any]) -> float | None:
    return mean_available(
        [
            pe_value_factor(metrics),
            pb_value_factor(metrics),
            ev_ebitda_factor(metrics),
        ],
        min_count=2,
    )

fundamental_value_score = value_composite

def _to_earnings_yield(value: Any) -> float | None:
    """Convert a valuation multiple to an earnings-like yield (1 / value).

    Yield has well-behaved marginal differences: PE 5→15 is a much
    bigger drop (0.20→0.067) than PE 60→70 (0.017→0.014).
    """
    number = safe_num(value)
    if number is None or number <= 0:
        return None
    return 1.0 / number

FACTOR_SPECS = (
    fundamental_factor_spec("pe_value_factor", "fundamental_value", "Lower PE ratio receives a higher score.", ["pe_ratio"], pe_value_factor),
    fundamental_factor_spec("pb_value_factor", "fundamental_value", "Lower PB ratio receives a higher score.", ["pb_ratio"], pb_value_factor),
    fundamental_factor_spec("ev_ebitda_factor", "fundamental_value", "Lower EV/EBITDA receives a higher score.", ["ev_to_ebitda"], ev_ebitda_factor),
    fundamental_factor_spec("fundamental_value_score", "fundamental_value", "Composite accounting-based value score (yield-based).", ["pe_ratio", "pb_ratio", "ev_to_ebitda"], value_composite),
)
