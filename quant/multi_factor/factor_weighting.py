"""Deterministic factor weighting modes for the multi-factor model."""

from __future__ import annotations

import math
from typing import Mapping


class FactorWeighting:
    """Resolve factor weights from equal, custom, IC, or stability inputs."""

    @staticmethod
    def weights(
        factors: list[str],
        mode: str = "equal_weight",
        custom_weights: Mapping[str, float] | None = None,
        ic_metrics: Mapping[str, Mapping[str, float | None]] | None = None,
        stability_scores: Mapping[str, float | None] | None = None,
        coverage: Mapping[str, float | None] | None = None,
    ) -> tuple[dict[str, float], list[str]]:
        mode = mode.strip().lower()
        normalized_factors = [factor.strip().lower() for factor in factors]
        if not normalized_factors:
            raise ValueError("multi-factor model requires at least one factor")
        if mode not in {"equal_weight", "custom_weight", "ic_weighted", "stability_weighted"}:
            raise ValueError("weighting_mode must be one of: equal_weight, custom_weight, ic_weighted, stability_weighted")

        warnings: list[str] = []
        if mode == "custom_weight":
            raw = {
                factor: max(float((custom_weights or {}).get(factor, 0.0)), 0.0)
                for factor in normalized_factors
            }
            if sum(raw.values()) <= 0:
                warnings.append("custom weights are empty; fallback to equal_weight")
                raw = {factor: 1.0 for factor in normalized_factors}
        elif mode == "ic_weighted":
            raw = {
                factor: FactorWeighting._ic_quality((ic_metrics or {}).get(factor, {}))
                for factor in normalized_factors
            }
            if sum(raw.values()) <= 0:
                warnings.append("IC metrics unavailable or non-positive; fallback to equal_weight")
                raw = {factor: 1.0 for factor in normalized_factors}
        elif mode == "stability_weighted":
            raw = {}
            missing_stability = []
            for factor in normalized_factors:
                stability = FactorWeighting._positive((stability_scores or {}).get(factor))
                cover = FactorWeighting._positive((coverage or {}).get(factor))
                if stability is None:
                    missing_stability.append(factor)
                    raw[factor] = 0.0
                    continue
                raw[factor] = stability * (cover if cover is not None else 1.0)
            if missing_stability:
                warnings.append(f"missing stability scores for {', '.join(missing_stability[:5])}")
            if sum(raw.values()) <= 0:
                warnings.append("stability metrics unavailable; fallback to equal_weight")
                raw = {factor: 1.0 for factor in normalized_factors}
        else:
            raw = {factor: 1.0 for factor in normalized_factors}

        total = sum(raw.values())
        return ({factor: raw[factor] / total for factor in sorted(raw)}, warnings)

    @staticmethod
    def _ic_quality(metrics: Mapping[str, float | None]) -> float:
        values = [
            abs(float(metrics.get("ic_mean") or 0.0)),
            abs(float(metrics.get("rank_ic_mean") or 0.0)),
            max(float(metrics.get("icir") or 0.0), 0.0),
        ]
        return sum(value for value in values if math.isfinite(value))

    @staticmethod
    def _positive(value) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return max(number, 0.0)
