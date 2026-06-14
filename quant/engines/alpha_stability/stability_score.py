"""Stability Score – Module 6.

Composite 0-100 score combining multiple audit dimensions.
"""

from __future__ import annotations

from quant.engines.alpha_stability.models import AuditModuleResult


DEFAULT_WEIGHTS = {
    "fold_consistency": 0.20,
    "universe_stability": 0.15,
    "cost_robustness": 0.20,
    "turnover_quality": 0.15,
    "decile_monotonicity": 0.15,
    "ic_persistence": 0.15,
}


def compute_stability_score(
    *,
    universe_result: AuditModuleResult | None = None,
    cost_result: AuditModuleResult | None = None,
    turnover_result: AuditModuleResult | None = None,
    ic_decay_result: AuditModuleResult | None = None,
    decile_result: AuditModuleResult | None = None,
    fold_consistency_score: float | None = None,
    weights: dict[str, float] | None = None,
) -> AuditModuleResult:
    """Compute composite stability score from individual audit results."""

    w = weights or dict(DEFAULT_WEIGHTS)
    # Normalise weights to sum to 1
    total_weight = sum(w.values())
    if total_weight > 0:
        w = {k: v / total_weight for k, v in w.items()}

    component_scores: dict[str, float | None] = {
        "fold_consistency": fold_consistency_score,
        "universe_stability": universe_result.score if universe_result else None,
        "cost_robustness": cost_result.score if cost_result else None,
        "turnover_quality": turnover_result.score if turnover_result else None,
        "decile_monotonicity": decile_result.score if decile_result else None,
        "ic_persistence": ic_decay_result.score if ic_decay_result else None,
    }

    # Compute weighted average of available components
    weighted_sum = 0.0
    weight_sum = 0.0
    available_components: dict[str, float] = {}

    for key, score in component_scores.items():
        if score is not None:
            component_weight = w.get(key, 0.0)
            weighted_sum += score * component_weight
            weight_sum += component_weight
            available_components[key] = score

    if weight_sum > 0:
        composite = weighted_sum / weight_sum
    else:
        composite = 0.0

    composite = max(0.0, min(100.0, composite))

    # Gather all warnings and recommendations
    all_warnings: list[str] = []
    all_recommendations: list[str] = []
    sub_results = [universe_result, cost_result, turnover_result, decile_result, ic_decay_result]
    for sub in sub_results:
        if sub is not None:
            all_warnings.extend(sub.warnings)
            all_recommendations.extend(sub.recommendations)

    missing = [k for k, v in component_scores.items() if v is None]
    if missing:
        all_warnings.append(f"missing components: {', '.join(missing)}")

    status = "pass" if composite >= 60 else ("warn" if composite >= 30 else "fail")

    return AuditModuleResult(
        module="stability_score",
        status=status,
        score=round(composite, 2),
        details={
            "composite_score": round(composite, 2),
            "component_scores": {
                k: round(v, 2) if v is not None else None
                for k, v in component_scores.items()
            },
            "weights": {k: round(v, 4) for k, v in w.items()},
            "available_components": len(available_components),
            "total_components": len(component_scores),
        },
        warnings=all_warnings,
        recommendations=list(dict.fromkeys(all_recommendations)),  # dedupe
    )
