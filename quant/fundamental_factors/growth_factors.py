"""Accounting-based growth factors."""

from __future__ import annotations

from typing import Any


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
