"""Accounting-based growth factors."""

from __future__ import annotations

from typing import Any

from quant.factors.specs import fundamental_factor_spec


def revenue_growth_factor(metrics: dict[str, Any]) -> float | None:
    return _num(metrics.get("revenue_growth"))


def eps_growth_factor(metrics: dict[str, Any]) -> float | None:
    return _num(metrics.get("eps_growth"))


def growth_composite(metrics: dict[str, Any]) -> float | None:
    return _mean_available(
        [
            revenue_growth_factor(metrics),
            eps_growth_factor(metrics),
        ]
    )


fundamental_growth_score = growth_composite


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
    fundamental_factor_spec("revenue_growth_factor", "fundamental_growth", "Higher revenue growth receives a higher score.", ["revenue_growth"], revenue_growth_factor),
    fundamental_factor_spec("eps_growth_factor", "fundamental_growth", "Higher EPS growth receives a higher score.", ["eps_growth"], eps_growth_factor),
    fundamental_factor_spec("growth_composite", "fundamental_growth", "Composite of revenue and EPS growth signals.", ["revenue_growth", "eps_growth"], growth_composite),
    fundamental_factor_spec("fundamental_growth_score", "fundamental_growth", "Composite accounting-based growth score.", ["revenue_growth", "eps_growth"], growth_composite),
)
