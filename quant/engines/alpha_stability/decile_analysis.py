"""Decile Analysis – Module 4.

Sorts securities into 10 deciles by factor value and checks return monotonicity.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant.engines.factor_backtest.factor_backtest import (
    FactorBacktest,
    FactorBacktestResult,
)
from quant.engines.alpha_stability.models import AuditModuleResult
from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore


@dataclass(frozen=True)
class DecileReturn:
    decile: int
    avg_return: float | None
    cumulative_return: float | None
    observation_count: int


def run_decile_analysis(
    factor: str,
    price_store: SQLitePriceStore,
    fundamental_store: FundamentalStore | None = None,
    *,
    universe: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    holding_period: int = 20,
    backtest_result: FactorBacktestResult | None = None,
    bulk_matrix: bool = True,
) -> AuditModuleResult:
    """Run 10-quantile backtest and measure return monotonicity."""

    if backtest_result is not None and backtest_result.quantiles == 10:
        result = backtest_result
    else:
        engine = FactorBacktest(price_store, fundamental_store)
        try:
            result = engine.run(
                factor=factor,
                start=start,
                end=end,
                holding_period=holding_period,
                quantiles=10,
                universe=universe,
                bulk_matrix=bulk_matrix,
                write_report=False,
            )
        except (ValueError, Exception) as exc:
            return AuditModuleResult(
                module="decile_analysis",
                status="fail",
                score=0.0,
                details={"factor": factor, "error": str(exc)},
                warnings=[f"decile backtest failed: {exc}"],
                recommendations=["fix factor backtest first"],
            )

    # Extract decile returns from quantile_returns
    decile_returns: list[DecileReturn] = []
    for decile in range(1, 11):
        key = f"q{decile}"
        avg_ret = result.quantile_returns.get(key)
        # Cumulative: same as avg for a single snapshot
        decile_returns.append(
            DecileReturn(
                decile=decile,
                avg_return=avg_ret,
                cumulative_return=avg_ret,
                observation_count=0,  # detailed count not available from summary
            )
        )

    # Monotonicity: Spearman correlation between decile rank and return
    valid_pairs = [
        (d.decile, d.avg_return)
        for d in decile_returns
        if d.avg_return is not None
    ]

    mono_corr = _monotonicity_correlation(valid_pairs)
    spread = _spread(decile_returns)

    score, warnings, recommendations = _score(mono_corr, spread, valid_pairs)
    direction = "normal" if (mono_corr or 0) >= 0 else "inverse"
    status = "pass" if score >= 60 else ("warn" if score >= 30 else "fail")

    return AuditModuleResult(
        module="decile_analysis",
        status=status,
        score=score,
        details={
            "factor": factor,
            "decile_returns": [
                {
                    "decile": d.decile,
                    "avg_return": d.avg_return,
                    "cumulative_return": d.cumulative_return,
                }
                for d in decile_returns
            ],
            "monotonicity_correlation": mono_corr,
            "direction": direction,
            "d10_d1_spread": spread,
        },
        warnings=warnings,
        recommendations=recommendations,
    )


def _monotonicity_correlation(pairs: list[tuple[int, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    ranks = [p[0] for p in pairs]
    returns = [p[1] for p in pairs]
    df = pd.DataFrame({"rank": ranks, "ret": returns})
    corr = df["rank"].corr(df["ret"], method="spearman")
    if pd.isna(corr):
        return None
    return float(corr)


def _spread(decile_returns: list[DecileReturn]) -> float | None:
    d1 = next((d.avg_return for d in decile_returns if d.decile == 1), None)
    d10 = next((d.avg_return for d in decile_returns if d.decile == 10), None)
    if d1 is None or d10 is None:
        return None
    return d10 - d1


def _score(
    mono_corr: float | None,
    spread: float | None,
    valid_pairs: list[tuple[int, float]],
) -> tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    recommendations: list[str] = []

    if mono_corr is None or len(valid_pairs) < 5:
        return 50.0, ["insufficient decile data"], []

    # Absolute monotonicity: |corr| close to 1 is ideal — but negative corr
    # is capped because the system does NOT auto-reverse factor direction.
    # A factor with perfect inverse monotonicity (Spearman = -1.0) is NOT
    # equivalent to one with perfect positive monotonicity.
    abs_corr = abs(mono_corr)
    mono_score = abs_corr * 100.0

    # Spread direction: positive spread with positive corr, or negative with negative
    spread_bonus = 0.0
    if spread is not None and abs(spread) > 0.001:
        if (spread > 0 and mono_corr > 0) or (spread < 0 and mono_corr < 0):
            spread_bonus = 10.0

    score = min(100.0, mono_score + spread_bonus)

    # Inverse monotonicity is NOT equivalent to positive monotonicity.
    # The system does not auto-reverse factors — cap the final score.
    if mono_corr < 0:
        score = min(score, 40.0)
        warnings.append(f"factor direction is inverse (corr={mono_corr:.2f}); score capped at 40")
        recommendations.append(
            "factor return monotonicity is inverse — consider reversing the factor "
            "or using long bottom-decile / short top-decile"
        )

    if abs_corr < 0.3:
        warnings.append(f"weak monotonicity (correlation={mono_corr:.2f})")
        recommendations.append("factor does not produce ordered decile performance")
    elif abs_corr < 0.6:
        warnings.append(f"moderate monotonicity (correlation={mono_corr:.2f})")

    if spread is not None and abs(spread) < 0.005:
        warnings.append("negligible D10-D1 spread")
        recommendations.append("top and bottom deciles have similar returns")

    return round(score, 2), warnings, recommendations
