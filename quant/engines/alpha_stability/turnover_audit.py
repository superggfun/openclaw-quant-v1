"""Turnover Audit – Module 3.

Analyses portfolio turnover from backtest periods and flags excessive churn.
"""

from __future__ import annotations

import statistics

from quant.engines.factor_backtest.factor_backtest import FactorBacktestResult
from quant.engines.alpha_stability.models import AuditModuleResult

# Threshold: >500% annualised turnover is excessive
EXCESSIVE_ANNUALISED_TURNOVER = 5.0


def run_turnover_audit(
    result: FactorBacktestResult,
    *,
    holding_period: int | None = None,
    trading_days_per_year: int = 252,
) -> AuditModuleResult:
    """Audit turnover characteristics from a completed factor backtest."""

    hp = holding_period or result.holding_period
    period_turnovers = [
        p.turnover
        for p in result.periods
        if p.turnover is not None
    ]

    if not period_turnovers:
        return AuditModuleResult(
            module="turnover_audit",
            status="warn",
            score=50.0,
            details={"factor": result.factor, "error": "no turnover data"},
            warnings=["no turnover data available from backtest periods"],
            recommendations=[],
        )

    avg_turnover = statistics.mean(period_turnovers)
    median_turnover = statistics.median(period_turnovers)
    max_turnover = max(period_turnovers)
    min_turnover = min(period_turnovers)
    std_turnover = statistics.stdev(period_turnovers) if len(period_turnovers) >= 2 else 0.0

    # Annualise: rebalances per year = trading_days / holding_period
    rebalances_per_year = trading_days_per_year / max(hp, 1)
    annualised_turnover = avg_turnover * rebalances_per_year

    excessive = annualised_turnover > EXCESSIVE_ANNUALISED_TURNOVER

    score, warnings, recommendations = _score(
        avg_turnover, annualised_turnover, excessive
    )
    status = "pass" if score >= 60 else ("warn" if score >= 30 else "fail")

    return AuditModuleResult(
        module="turnover_audit",
        status=status,
        score=score,
        details={
            "factor": result.factor,
            "average_turnover": round(avg_turnover, 6),
            "median_turnover": round(median_turnover, 6),
            "max_turnover": round(max_turnover, 6),
            "min_turnover": round(min_turnover, 6),
            "std_turnover": round(std_turnover, 6),
            "annualised_turnover": round(annualised_turnover, 4),
            "excessive": excessive,
            "rebalance_count": len(period_turnovers),
            "holding_period": hp,
        },
        warnings=warnings,
        recommendations=recommendations,
    )


def _score(
    avg_turnover: float,
    annualised: float,
    excessive: bool,
) -> tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    recommendations: list[str] = []

    # Lower annualised turnover is better
    # 0% → 100, 100% → 80, 300% → 50, 500% → 30, 1000% → 0
    if annualised <= 0:
        score = 100.0
    elif annualised <= 1.0:
        score = 100.0 - annualised * 20.0
    elif annualised <= 3.0:
        score = 80.0 - (annualised - 1.0) * 15.0
    elif annualised <= 5.0:
        score = 50.0 - (annualised - 3.0) * 10.0
    else:
        score = max(0.0, 30.0 - (annualised - 5.0) * 6.0)

    score = max(0.0, min(100.0, score))

    if excessive:
        warnings.append(
            f"annualised turnover {annualised*100:.0f}% exceeds 500% threshold"
        )
        recommendations.append("increase holding period or reduce signal frequency")

    if avg_turnover > 0.8:
        warnings.append("average per-rebalance turnover exceeds 80%")
        recommendations.append("portfolio changes almost entirely each period – signals may be noisy")

    return round(score, 2), warnings, recommendations
