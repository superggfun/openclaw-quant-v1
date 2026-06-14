"""Transaction Cost Sensitivity – Module 2.

Evaluates how factor alpha degrades under increasing transaction costs.
"""

from __future__ import annotations

from quant.engines.factor_backtest.factor_backtest import FactorBacktest, FactorBacktestResult
from quant.engines.alpha_stability.models import AuditModuleResult
from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore

DEFAULT_COST_LEVELS_BPS = [0, 5, 10, 20, 50]


def run_cost_sensitivity(
    factor: str,
    price_store: SQLitePriceStore,
    fundamental_store: FundamentalStore | None = None,
    *,
    cost_levels_bps: list[int] | None = None,
    universe: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    holding_period: int = 20,
    quantiles: int = 5,
    bulk_matrix: bool = True,
) -> AuditModuleResult:
    """Evaluate *factor* at multiple cost levels and measure alpha erosion."""

    levels = cost_levels_bps or DEFAULT_COST_LEVELS_BPS
    engine = FactorBacktest(price_store, fundamental_store)

    # Run zero-cost baseline first
    try:
        baseline: FactorBacktestResult = engine.run(
            factor=factor,
            start=start,
            end=end,
            holding_period=holding_period,
            quantiles=quantiles,
            universe=universe,
            bulk_matrix=bulk_matrix,
            write_report=False,
        )
    except (ValueError, Exception) as exc:
        return AuditModuleResult(
            module="cost_sensitivity",
            status="fail",
            score=0.0,
            details={"factor": factor, "error": str(exc)},
            warnings=[f"baseline backtest failed: {exc}"],
            recommendations=["fix factor backtest before assessing cost sensitivity"],
        )

    baseline_return = baseline.long_short_return
    baseline_sharpe = baseline.sharpe
    baseline_turnover = baseline.turnover or 0.0

    cost_results: list[dict] = []
    for bps in levels:
        cost_fraction = bps / 10_000.0
        # Net return = gross return - (turnover * cost per unit)
        # Each period, turnover is fraction of portfolio traded; cost = turnover * bps
        # Simple model: for each period, subtract cost_fraction * period_turnover
        periods = baseline.periods
        net_period_returns: list[float] = []
        for period in periods:
            gross = period.long_short_return
            if gross is None:
                continue
            period_turnover = period.turnover if period.turnover is not None else 0.0
            net = gross - (period_turnover * cost_fraction * 2.0)  # 2x for round-trip
            net_period_returns.append(net)

        from quant.engines.factor_common.stats import compound_return, sharpe as calc_sharpe, annual_return as calc_annual_return

        net_return = compound_return(net_period_returns)
        net_sharpe = calc_sharpe(net_period_returns)
        net_cagr = calc_annual_return(net_period_returns)

        cost_results.append({
            "cost_bps": bps,
            "net_return": net_return,
            "net_sharpe": net_sharpe,
            "net_cagr": net_cagr,
            "gross_return": baseline_return,
            "gross_sharpe": baseline_sharpe,
        })

    score, warnings, recommendations = _score(cost_results, baseline_return, baseline_sharpe)
    status = "pass" if score >= 60 else ("warn" if score >= 30 else "fail")

    return AuditModuleResult(
        module="cost_sensitivity",
        status=status,
        score=score,
        details={
            "factor": factor,
            "cost_levels_bps": levels,
            "baseline_turnover": baseline_turnover,
            "results": cost_results,
        },
        warnings=warnings,
        recommendations=recommendations,
    )


def _score(
    cost_results: list[dict],
    baseline_return: float | None,
    baseline_sharpe: float | None,
) -> tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    recommendations: list[str] = []

    if not cost_results or baseline_return is None:
        return 50.0, ["insufficient data"], []

    # Find the 10bps result as "realistic cost" benchmark
    realistic = None
    for r in cost_results:
        if r["cost_bps"] == 10:
            realistic = r
            break
    if realistic is None:
        realistic = cost_results[-1]  # use highest cost

    net_sharpe_at_realistic = realistic.get("net_sharpe")
    net_return_at_realistic = realistic.get("net_return")

    # Positive sharpe at realistic costs => strong
    if net_sharpe_at_realistic is not None and net_sharpe_at_realistic > 0:
        sharpe_score = min(100.0, net_sharpe_at_realistic / max(abs(baseline_sharpe or 1.0), 0.01) * 100.0)
    else:
        sharpe_score = 0.0

    # Return survival: what % of gross return survives?
    if baseline_return is not None and abs(baseline_return) > 1e-9 and net_return_at_realistic is not None:
        survival = net_return_at_realistic / baseline_return if baseline_return > 0 else 0.0
        survival = max(0.0, min(1.0, survival))
    else:
        survival = 0.0

    score = sharpe_score * 0.6 + survival * 100.0 * 0.4
    score = max(0.0, min(100.0, score))

    if net_sharpe_at_realistic is not None and net_sharpe_at_realistic <= 0:
        warnings.append("alpha does not survive at 10 bps transaction cost")
        recommendations.append("reduce turnover or find more persistent signal")
    elif baseline_sharpe is not None and net_sharpe_at_realistic is not None:
        degradation = 1.0 - (net_sharpe_at_realistic / baseline_sharpe) if baseline_sharpe != 0 else 0.0
        if degradation > 0.5:
            warnings.append(f"sharpe degrades {degradation*100:.0f}% at realistic costs")
            recommendations.append("consider holding period extension to reduce turnover")

    return round(score, 2), warnings, recommendations
