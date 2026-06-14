"""Lightweight factor stability helpers."""

from __future__ import annotations

import math
from typing import Mapping


class FactorStability:
    """Score factor stability from IC history, decay, walk-forward, and coverage."""

    @staticmethod
    def score(
        ic_history: list[float] | None = None,
        rank_ic_history: list[float] | None = None,
        decay: Mapping[str, float | None] | None = None,
        walk_forward_score: float | None = None,
        coverage: float | None = None,
    ) -> float:
        components = []
        for series in [ic_history or [], rank_ic_history or []]:
            finite = [float(value) for value in series if FactorStability._finite(value)]
            if finite:
                mean_abs = min(abs(sum(finite) / len(finite)) * 5.0, 1.0)
                consistency = sum(1 for value in finite if value >= 0) / len(finite)
                components.append((mean_abs + consistency) / 2.0)
        if decay:
            finite_decay = [abs(float(value)) for value in decay.values() if FactorStability._finite(value)]
            if finite_decay:
                components.append(min(sum(finite_decay) / len(finite_decay) * 5.0, 1.0))
        if FactorStability._finite(walk_forward_score):
            components.append(max(min(float(walk_forward_score), 1.0), 0.0))
        if FactorStability._finite(coverage):
            components.append(max(min(float(coverage), 1.0), 0.0))
        if not components:
            return 0.0
        return round(sum(components) / len(components), 6)

    @staticmethod
    def label(score: float | None) -> str:
        if score is None:
            return "unknown"
        if score >= 0.70:
            return "stable"
        if score >= 0.40:
            return "moderate"
        return "unstable"

    @staticmethod
    def _finite(value) -> bool:
        try:
            number = float(value)
            return math.isfinite(number)
        except (TypeError, ValueError):
            return False
