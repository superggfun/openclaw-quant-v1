"""Research validation ranking helpers."""

from __future__ import annotations

import math
from typing import Any

from quant.research_validation.recommendations import recommendations

__all__ = [
    "coverage",
    "factor_rankings",
    "num",
    "recommendations",
    "strategy_rankings",
]


def factor_rankings(
    factors: list[str],
    evals: list[dict[str, Any]],
    backtests: list[dict[str, Any]],
    walk_forwards: list[dict[str, Any]],
    factor_rank: dict[str, Any],
) -> list[dict[str, Any]]:
    eval_by = {row.get("factor"): row for row in evals}
    bt_by = {row.get("factor"): row for row in backtests}
    wf_by = {((row.get("parameters") or {}).get("factor")): row for row in walk_forwards}
    confidence_by = {}
    for row in (factor_rank.get("top_factors") or []) + (factor_rank.get("worst_factors") or []):
        confidence_by[row.get("factor_name")] = num(row.get("confidence_score"))

    rows = []
    for factor in factors:
        ev = eval_by.get(factor, {})
        bt = bt_by.get(factor, {})
        wf = wf_by.get(factor, {})
        summary = wf.get("summary") or {}
        raw_metrics = {
            "ic": num(ev.get("ic_mean")),
            "rank_ic": num(ev.get("rank_ic_mean")),
            "icir": num(ev.get("icir")),
            "coverage": coverage(ev),
            "cumulative_forward_spread": num(bt.get("cumulative_forward_spread", bt.get("long_short_return"))),
            "spread_sharpe_like": num(bt.get("spread_sharpe_like", bt.get("long_short_sharpe", bt.get("sharpe")))),
            "spread_max_drawdown": num(bt.get("spread_max_drawdown", bt.get("max_drawdown"))),
            "walk_forward_test_sharpe": num(summary.get("average_test_sharpe")),
            "confidence": confidence_by.get(factor),
        }
        rank_score = _rank_score(raw_metrics)
        evidence_grade = _evidence_grade(raw_metrics, rank_score)
        rows.append(
            {
                "factor": factor,
                **raw_metrics,
                "raw_metrics": raw_metrics,
                "rank_score": rank_score,
                "evidence_grade": evidence_grade,
                "blocking_warnings": _blocking_warnings(raw_metrics),
                "evidence_score": rank_score,
            }
        )

    return sorted(rows, key=lambda row: (-10**9 if row["rank_score"] is None else row["rank_score"], row["factor"]), reverse=True)


def strategy_rankings(strategy_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for report in strategy_results:
        summary = report.get("trade_sim_summary") or {}
        gate = report.get("gate_summary") or {}
        rows.append(
            {
                "strategy": report.get("strategy_name"),
                "version": report.get("strategy_version"),
                "status": report.get("status"),
                "gate_status": gate.get("overall_status"),
                "final_equity": summary.get("final_equity"),
                "total_return": summary.get("total_return"),
                "max_drawdown": summary.get("max_drawdown"),
                "trade_count": summary.get("trade_count"),
                "warning_count": len(report.get("warnings") or []),
                "report_path": report.get("report_path"),
                "gate_report_path": (report.get("artifacts") or {}).get("strategy_gate_report_path"),
            }
        )
    return sorted(rows, key=lambda row: (row.get("gate_status") == "PASS", num(row.get("total_return")) or -10**9), reverse=True)


def coverage(report: dict[str, Any]) -> float | None:
    direct = num(report.get("coverage"))
    if direct is not None:
        return direct
    factor_coverage = report.get("factor_coverage") or {}
    for key in ("coverage_pct", "coverage", "symbols_with_data_pct"):
        value = num(factor_coverage.get(key))
        if value is not None:
            return value
    return num((report.get("saved_factor_history") or {}).get("coverage"))


def num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _rank_score(metrics: dict[str, float | None]) -> float | None:
    components = []
    for key in ("ic", "rank_ic", "icir", "spread_sharpe_like", "walk_forward_test_sharpe", "confidence"):
        value = metrics.get(key)
        if value is None:
            # Fall back to legacy key names
            legacy = {"spread_sharpe_like": "sharpe"}.get(key)
            if legacy:
                value = metrics.get(legacy)
        if value is None:
            continue
        components.append(_bounded_score(value))
    coverage_value = metrics.get("coverage")
    if coverage_value is not None:
        components.append(max(0.0, min(1.0, coverage_value)))
    drawdown = metrics.get("spread_max_drawdown", metrics.get("drawdown"))
    if drawdown is not None:
        components.append(max(0.0, min(1.0, 1.0 + drawdown)))
    return sum(components) / len(components) if components else None


def _bounded_score(value: float) -> float:
    return max(0.0, min(1.0, 0.5 + value / 2.0))


def _evidence_grade(metrics: dict[str, float | None], rank_score: float | None) -> str:
    warnings = _blocking_warnings(metrics)
    if warnings:
        return "blocked_by_coverage"
    if rank_score is None:
        return "insufficient_evidence"
    if rank_score >= 0.70:
        return "candidate"
    if rank_score >= 0.55:
        return "usable_but_needs_walk_forward"
    return "weak_or_inconclusive"


def _blocking_warnings(metrics: dict[str, float | None]) -> list[str]:
    warnings = []
    coverage_value = metrics.get("coverage")
    if coverage_value is not None and coverage_value < 0.30:
        warnings.append("LOW_FACTOR_COVERAGE")
    return warnings
