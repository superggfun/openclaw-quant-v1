"""Accounting-based quality factors."""

from __future__ import annotations

from typing import Any

from quant.factors.specs import fundamental_factor_spec


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


FACTOR_SPECS = (
    fundamental_factor_spec("roe_quality_factor", "fundamental_quality", "Higher ROE receives a higher score.", ["roe"], roe_quality_factor),
    fundamental_factor_spec("roa_quality_factor", "fundamental_quality", "Higher ROA receives a higher score.", ["roa"], roa_quality_factor),
    fundamental_factor_spec("gross_margin_factor", "fundamental_quality", "Higher gross margin receives a higher score.", ["gross_margin"], gross_margin_factor),
    fundamental_factor_spec("net_margin_factor", "fundamental_quality", "Higher net margin receives a higher score.", ["net_margin"], net_margin_factor),
    fundamental_factor_spec("quality_composite", "fundamental_quality", "Composite of profitability and margin quality signals.", ["roe", "roa", "gross_margin", "net_margin"], quality_composite),
    fundamental_factor_spec("fundamental_quality_score", "fundamental_quality", "Composite accounting-based quality score.", ["roe", "roa", "gross_margin", "net_margin"], quality_composite),
)
