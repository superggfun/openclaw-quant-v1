"""Accounting-based quality factors."""

from __future__ import annotations

from typing import Any


def roe_quality_factor(metrics: dict[str, Any]) -> float | None:
    return _num(metrics.get("roe"))


def roa_quality_factor(metrics: dict[str, Any]) -> float | None:
    return _num(metrics.get("roa"))


def gross_margin_factor(metrics: dict[str, Any]) -> float | None:
    return _num(metrics.get("gross_margin"))


def net_margin_factor(metrics: dict[str, Any]) -> float | None:
    return _num(metrics.get("net_margin"))


def quality_composite(metrics: dict[str, Any]) -> float | None:
    return _mean_available(
        [
            roe_quality_factor(metrics),
            roa_quality_factor(metrics),
            gross_margin_factor(metrics),
            net_margin_factor(metrics),
        ]
    )


fundamental_quality_score = quality_composite


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
