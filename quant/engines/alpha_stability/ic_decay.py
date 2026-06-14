"""IC Decay Analysis – Module 5.

Measures information coefficient at multiple forward horizons and estimates half-life.
"""

from __future__ import annotations

import math

from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.engines.alpha_stability.models import AuditModuleResult
from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore

DEFAULT_IC_HORIZONS = [1, 5, 10, 20, 40]


def run_ic_decay(
    factor: str,
    price_store: SQLitePriceStore,
    fundamental_store: FundamentalStore | None = None,
    *,
    horizons: list[int] | None = None,
    universe: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> AuditModuleResult:
    """Measure IC at multiple horizons and estimate alpha half-life.

    Uses FactorEvaluation.evaluate(bulk_matrix=True, decay_horizons=...) which builds
    all needed horizons in one FactorMatrixBuilder pass (no per-horizon loop).
    """

    test_horizons = horizons or DEFAULT_IC_HORIZONS
    evaluator = FactorEvaluation(price_store, fundamental_store)

    # Single evaluate call builds all decay horizons at once
    # forward_days=20 is the 'main' horizon, result.decay contains all others
    try:
        result = evaluator.evaluate(
            factor=factor,
            start=start,
            end=end,
            forward_days=20,
            universe=universe,
            bulk_matrix=True,
            decay_horizons=test_horizons,
            write_report=False,
        )
        decay_map = result.decay
    except (ValueError, Exception) as exc:
        return AuditModuleResult(
            module="ic_decay",
            status="fail",
            score=0.0,
            details={"factor": factor, "error": str(exc)},
            warnings=[f"IC decay evaluation failed: {exc}"],
            recommendations=["fix factor evaluation before assessing IC decay"],
        )

    decay_data: list[dict] = []
    ic_values: list[float] = []

    for horizon in test_horizons:
        key = f"{horizon}d"
        entry = decay_map.get(key)
        if entry is not None:
            ic = entry.get("ic")
            rank_ic = entry.get("rank_ic")
        else:
            ic = None
            rank_ic = None
        decay_data.append({
            "horizon_days": horizon,
            "ic": ic,
            "rank_ic": rank_ic,
        })
        if ic is not None:
            ic_values.append(ic)

    half_life = _estimate_half_life(decay_data)
    score, warnings, recommendations = _score(decay_data, half_life, ic_values)
    status = "pass" if score >= 60 else ("warn" if score >= 30 else "fail")

    return AuditModuleResult(
        module="ic_decay",
        status=status,
        score=score,
        details={
            "factor": factor,
            "horizons": test_horizons,
            "decay": decay_data,
            "half_life_days": half_life,
        },
        warnings=warnings,
        recommendations=recommendations,
    )


def _estimate_half_life(decay_data: list[dict]) -> float | None:
    """Exponential fit to IC absolute values to estimate half-life."""
    pairs: list[tuple[float, float]] = []
    for entry in decay_data:
        ic = entry.get("ic")
        if ic is not None and abs(ic) > 1e-9:
            pairs.append((float(entry["horizon_days"]), abs(ic)))

    if len(pairs) < 3:
        return None

    try:
        import numpy as np

        horizons = np.array([p[0] for p in pairs])
        log_ic = np.log(np.array([p[1] for p in pairs]))
        slope, _intercept = np.polyfit(horizons, log_ic, 1)
        lambda_est = -slope
        if lambda_est <= 1e-12:
            return None
        return round(float(math.log(2) / lambda_est), 1)
    except Exception:
        return None


def _score(
    decay_data: list[dict],
    half_life: float | None,
    ic_values: list[float],
) -> tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    recommendations: list[str] = []

    if len(ic_values) < 2:
        return 50.0, ["insufficient IC data across horizons"], []

    # Score based on half-life (longer is better for persistence)
    if half_life is not None:
        if half_life >= 40:
            hl_score = 100.0
        elif half_life >= 20:
            hl_score = 70.0 + (half_life - 20) / 20 * 30.0
        elif half_life >= 10:
            hl_score = 40.0 + (half_life - 10) / 10 * 30.0
        elif half_life >= 5:
            hl_score = 20.0 + (half_life - 5) / 5 * 20.0
        else:
            hl_score = max(0.0, half_life / 5 * 20.0)
    else:
        # If we can't estimate half-life, use IC persistence
        # Check if short-horizon IC and long-horizon IC are both meaningful
        short_ic = next(
            (e["ic"] for e in decay_data if e["horizon_days"] <= 5 and e["ic"] is not None),
            None,
        )
        long_ic = next(
            (e["ic"] for e in decay_data if e["horizon_days"] >= 20 and e["ic"] is not None),
            None,
        )
        if short_ic is not None and long_ic is not None and abs(short_ic) > 1e-9:
            retention = abs(long_ic) / abs(short_ic)
            hl_score = min(100.0, retention * 100.0)
        else:
            hl_score = 50.0

    score = max(0.0, min(100.0, hl_score))

    if half_life is not None and half_life < 5:
        warnings.append(f"very short alpha half-life ({half_life:.1f} days)")
        recommendations.append("signal decays quickly – consider longer holding period alignment")
    elif half_life is not None and half_life < 10:
        warnings.append(f"short alpha half-life ({half_life:.1f} days)")

    # Check if IC goes negative at any horizon
    for entry in decay_data:
        ic = entry.get("ic")
        if ic is not None and ic_values and ic_values[0] > 0 and ic < 0:
            warnings.append(
                f"IC reverses sign at {entry['horizon_days']}-day horizon"
            )
            recommendations.append("signal may reverse at longer horizons – limit holding period")
            break

    return round(score, 2), warnings, recommendations
