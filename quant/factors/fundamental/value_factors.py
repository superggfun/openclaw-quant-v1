"""Accounting-based value factors."""

from __future__ import annotations

from typing import Any

from quant.factors.specs import fundamental_factor_spec


def pe_value_factor(metrics: dict[str, Any]) -> float | None:
    return _lower_positive_is_better(metrics.get("pe_ratio"))


def pb_value_factor(metrics: dict[str, Any]) -> float | None:
    return _lower_positive_is_better(metrics.get("pb_ratio"))


def ev_ebitda_factor(metrics: dict[str, Any]) -> float | None:
    return _lower_positive_is_better(metrics.get("ev_to_ebitda"))


def value_composite(metrics: dict[str, Any]) -> float | None:
    return _mean_available(
        [
            pe_value_factor(metrics),
            pb_value_factor(metrics),
            ev_ebitda_factor(metrics),
        ]
    )


fundamental_value_score = value_composite


def _lower_positive_is_better(value: Any) -> float | None:
    number = _num(value)
    if number is None or number <= 0:
        return None
    return -number


def _mean_available(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


FACTOR_SPECS = (
    fundamental_factor_spec("pe_value_factor", "fundamental_value", "Lower PE ratio receives a higher score.", ["pe_ratio"], pe_value_factor),
    fundamental_factor_spec("pb_value_factor", "fundamental_value", "Lower PB ratio receives a higher score.", ["pb_ratio"], pb_value_factor),
    fundamental_factor_spec("ev_ebitda_factor", "fundamental_value", "Lower EV/EBITDA receives a higher score.", ["ev_to_ebitda"], ev_ebitda_factor),
    fundamental_factor_spec("value_composite", "fundamental_value", "Composite of PE, PB, and EV/EBITDA value signals.", ["pe_ratio", "pb_ratio", "ev_to_ebitda"], value_composite),
    fundamental_factor_spec("fundamental_value_score", "fundamental_value", "Composite accounting-based value score.", ["pe_ratio", "pb_ratio", "ev_to_ebitda"], value_composite),
)
