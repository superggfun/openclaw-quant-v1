"""Analytics helpers for persisted factor history."""

from __future__ import annotations

import math
from typing import Any


class FactorAnalytics:
    """Compute deterministic factor health and confidence diagnostics."""

    @staticmethod
    def health_score(row: dict[str, Any]) -> float:
        icir = FactorAnalytics._score_abs(row.get("icir"), cap=1.0)
        coverage = FactorAnalytics._score_pct(row.get("coverage"))
        stability = FactorAnalytics._score_pct(row.get("stability_score"))
        drawdown = FactorAnalytics._drawdown_score(row.get("drawdown"))
        return round((0.35 * icir + 0.30 * coverage + 0.25 * stability + 0.10 * drawdown) * 100.0, 6)

    @staticmethod
    def confidence_score(coverage: float | None, stability: float | None, ic_count: int | None = None) -> float:
        coverage_score = FactorAnalytics._score_pct(coverage)
        stability_score = FactorAnalytics._score_pct(stability)
        count_score = min(max(float(ic_count or 0) / 30.0, 0.0), 1.0)
        return round(0.45 * coverage_score + 0.35 * stability_score + 0.20 * count_score, 6)

    @staticmethod
    def decay_score(decay: dict | None) -> float | None:
        if not decay:
            return None
        values = []
        for metrics in decay.values():
            if isinstance(metrics, dict):
                value = FactorAnalytics._num(metrics.get("ic"))
                if value is not None:
                    values.append(abs(value))
        if not values:
            return None
        return round(min(sum(values) / len(values), 1.0), 6)

    @staticmethod
    def consistency_score(values: list[float | None]) -> float | None:
        clean = [float(value) for value in values if FactorAnalytics._num(value) is not None]
        if not clean:
            return None
        if len(clean) == 1:
            return 1.0
        mean_abs = sum(abs(value) for value in clean) / len(clean)
        variance = sum((value - sum(clean) / len(clean)) ** 2 for value in clean) / (len(clean) - 1)
        penalty = math.sqrt(variance)
        if mean_abs <= 0:
            return 0.0
        return round(max(0.0, min(1.0, 1.0 - penalty / mean_abs)), 6)

    @staticmethod
    def _score_abs(value: Any, cap: float) -> float:
        number = FactorAnalytics._num(value)
        if number is None:
            return 0.0
        return min(abs(number) / cap, 1.0)

    @staticmethod
    def _score_pct(value: Any) -> float:
        number = FactorAnalytics._num(value)
        if number is None:
            return 0.0
        return min(max(number, 0.0), 1.0)

    @staticmethod
    def _drawdown_score(value: Any) -> float:
        number = FactorAnalytics._num(value)
        if number is None:
            return 0.5
        return min(max(1.0 + number, 0.0), 1.0)

    @staticmethod
    def _num(value: Any) -> float | None:
        try:
            if value is None:
                return None
            number = float(value)
            if not math.isfinite(number):
                return None
            return number
        except (TypeError, ValueError):
            return None
