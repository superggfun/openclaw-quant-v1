"""Accounting-based financial health factors."""

from __future__ import annotations

from typing import Any


def debt_to_equity_factor(metrics: dict[str, Any]) -> float | None:
    value = _num(metrics.get("debt_to_equity"))
    if value is None or value < 0:
        return None
    return -value


def current_ratio_factor(metrics: dict[str, Any]) -> float | None:
    return _healthy_liquidity_score(metrics.get("current_ratio"), target=2.0)


def quick_ratio_factor(metrics: dict[str, Any]) -> float | None:
    return _healthy_liquidity_score(metrics.get("quick_ratio"), target=1.0)


def financial_health_composite(metrics: dict[str, Any]) -> float | None:
    return _mean_available(
        [
            debt_to_equity_factor(metrics),
            current_ratio_factor(metrics),
            quick_ratio_factor(metrics),
        ]
    )


fundamental_health_score = financial_health_composite


def _healthy_liquidity_score(value: Any, target: float) -> float | None:
    number = _num(value)
    if number is None or number <= 0:
        return None
    return -abs(number - target)


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
