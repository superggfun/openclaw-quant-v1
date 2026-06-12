"""Default performance profile target registry."""

from __future__ import annotations


DEFAULT_PROFILE_FACTORS = [
    "momentum_20d",
    "momentum_60d",
    "growth_score",
    "fundamental_quality_score",
    "fundamental_value_score",
]

DEFAULT_PROFILE_TARGETS = [
    "factor_eval",
    "factor_backtest",
    "walk_forward",
    "strategy_run",
    "research_validation",
]


def normalize_targets(targets: list[str] | None) -> list[str]:
    selected = targets or list(DEFAULT_PROFILE_TARGETS)
    normalized = []
    for target in selected:
        value = str(target).strip().lower().replace("-", "_")
        if value == "all":
            return list(DEFAULT_PROFILE_TARGETS)
        if value not in DEFAULT_PROFILE_TARGETS:
            raise ValueError(f"unsupported profile target: {target}")
        if value not in normalized:
            normalized.append(value)
    return normalized
