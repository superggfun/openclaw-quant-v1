"""Factor report agent exporters."""

from __future__ import annotations

from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, best_decay_horizon, clean_warnings, num
from quant.reports.agent_export.models import AgentExport
from quant.reports.agent_export.specs import export_spec, metadata_type


def export_multi_factor(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    scores = report.get("scores") or []
    top_scores = sorted(
        [score for score in scores if isinstance(score, dict) and num(score.get("final_alpha_score")) is not None],
        key=lambda item: (float(item.get("final_alpha_score") or 0.0), str(item.get("symbol"))),
        reverse=True,
    )[:5]
    confidence = report.get("confidence") or {}
    coverage = report.get("coverage") or {}
    warnings = clean_warnings(report.get("warnings"))
    low_coverage = {
        factor: value
        for factor, value in coverage.items()
        if num(value) is not None and float(value) < 0.8
    }
    if low_coverage:
        warnings.append("WARN_LOW_FACTOR_COVERAGE")
    metrics = {
        "as_of_date": report.get("as_of_date"),
        "weighting_mode": report.get("weighting_mode"),
        "overall_confidence": confidence.get("overall_confidence"),
        "factor_weights": report.get("factor_weights"),
        "factor_weights_by_family": report.get("factor_weights_by_family"),
        "family_weights": report.get("family_weights"),
        "coverage": coverage,
        "top_symbols": [
            {"symbol": item.get("symbol"), "score": item.get("final_alpha_score"), "confidence": item.get("overall_confidence")}
            for item in top_scores
        ],
    }
    return ctx.base_export(
        "multi_factor",
        generated_from,
        "Multi-factor model produced a unified coverage-aware alpha score.",
        metrics,
        ["unified alpha score generated", "coverage-aware confidence generated"],
        warnings,
        ["review low-coverage factors", "run walk-forward validation", "compare family contributions"],
        [f"inspect {item.get('symbol')} factor contributions" for item in top_scores],
        [f"{factor}: coverage {float(value):.2%}" for factor, value in low_coverage.items()],
    )


def export_factor_eval(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    ic = report.get("ic_mean")
    rank_ic = report.get("rank_ic_mean")
    icir = report.get("icir")
    best_horizon = best_decay_horizon(report.get("decay") or {})
    assessment = "positive predictive quality" if num(ic) and num(ic) > 0 else "negative predictive quality"
    warnings = clean_warnings(report.get("warnings"))
    if num(ic) is not None and num(ic) < 0:
        warnings.append("WARN_FACTOR_IC_NEGATIVE")
    coverage = report.get("factor_coverage") or {}
    if coverage and num(coverage.get("missing_percentage")) and num(coverage.get("missing_percentage")) > 0:
        warnings.append("WARN_PARTIAL_FUNDAMENTAL_DATA")
    metrics = {
        "factor": report.get("factor"),
        "ic_mean": ic,
        "rank_ic_mean": rank_ic,
        "icir": icir,
        "ic_count": report.get("ic_count"),
        "best_horizon": best_horizon,
        "spread_return": report.get("spread_return"),
        "factor_coverage": coverage or None,
        "cache_enabled": report.get("cache_enabled"),
        "cache_hits": report.get("cache_hits"),
        "cache_misses": report.get("cache_misses"),
        "matrix_rows": report.get("matrix_rows"),
        "eval_seconds": report.get("eval_seconds"),
        "artifact_path": report.get("artifact_path"),
        "artifact_paths": report.get("artifact_paths"),
    }
    if report.get("cache_enabled"):
        warnings.append("CACHE_DIAGNOSTIC: factor matrix cache was enabled for this run")
    return ctx.base_export(
        "factor_eval",
        generated_from,
        f"Factor {report.get('factor')} shows {assessment}.",
        metrics,
        [assessment],
        warnings,
        ["compare factors", "run factor backtest", "expand universe"],
        [f"evaluate {report.get('factor')} over larger universe"],
        ctx.exclusion_notes(report),
    )


def export_factor_backtest(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    ret = report.get("long_short_return")
    sharpe = report.get("long_short_sharpe", report.get("sharpe"))
    drawdown = report.get("max_drawdown")
    assessment = "factor currently positive" if num(ret) and num(ret) > 0 else "factor currently weak"
    warnings = clean_warnings(report.get("warnings"))
    warnings.extend(ctx.performance_warnings(total_return=ret, sharpe=sharpe, drawdown=drawdown))
    if len(report.get("rebalance_dates") or []) < 20:
        warnings.append("WARN_LOW_OBSERVATION_COUNT")
    coverage = report.get("factor_coverage") or {}
    if coverage and num(coverage.get("missing_percentage")) and num(coverage.get("missing_percentage")) > 0:
        warnings.append("WARN_PARTIAL_FUNDAMENTAL_DATA")
    metrics = {
        "factor": report.get("factor"),
        "long_short_return": ret,
        "sharpe": sharpe,
        "max_drawdown": drawdown,
        "turnover": report.get("turnover"),
        "gross_exposure": report.get("gross_exposure"),
        "net_exposure": report.get("net_exposure"),
        "ic_mean": report.get("ic_mean"),
        "rank_ic_mean": report.get("rank_ic_mean"),
        "icir": report.get("icir"),
        "factor_coverage": coverage or None,
        "artifact_path": report.get("artifact_path"),
        "artifact_paths": report.get("artifact_paths"),
    }
    return ctx.base_export(
        "factor_backtest",
        generated_from,
        f"Long-short factor backtest assessment: {assessment}.",
        metrics,
        [assessment],
        warnings,
        ["test with larger universe", "review drawdown", "compare factors"],
        ["run strategy evaluation", "run factor evaluation"],
        ctx.exclusion_notes(report),
    )


def export_factor_store_summary(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    counts = report.get("counts") or {}
    metrics = {
        "factor_definitions": counts.get("factor_definitions"),
        "factor_values": counts.get("factor_values"),
        "factor_evaluation_history": counts.get("factor_evaluation_history"),
        "factor_backtest_history": counts.get("factor_backtest_history"),
        "factor_walk_forward_history": counts.get("factor_walk_forward_history"),
        "factor_stability_history": counts.get("factor_stability_history"),
        "factor_count": len(report.get("factors") or []),
    }
    warnings = []
    if not counts.get("factor_values"):
        warnings.append("WARN_FACTOR_STORE_EMPTY_VALUES")
    return ctx.base_export(
        "factor_store_summary",
        generated_from,
        "Factor store summary generated for persisted research history.",
        metrics,
        ["factor store is available for reproducible research"],
        warnings,
        ["save factor-eval with --save-factor-history", "review factor-rank", "compare factor history over time"],
        [],
        [],
    )


def export_factor_history(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    evaluations = report.get("evaluation_history") or []
    backtests = report.get("backtest_history") or []
    stability = report.get("stability_history") or []
    latest_eval = evaluations[0] if evaluations else {}
    latest_backtest = backtests[0] if backtests else {}
    latest_stability = stability[0] if stability else {}
    metrics = {
        "factor": report.get("factor"),
        "evaluation_rows": len(evaluations),
        "backtest_rows": len(backtests),
        "walk_forward_rows": len(report.get("walk_forward_history") or []),
        "stability_rows": len(stability),
        "latest_ic": latest_eval.get("ic"),
        "latest_rank_ic": latest_eval.get("rank_ic"),
        "latest_icir": latest_eval.get("icir"),
        "latest_coverage": latest_eval.get("coverage"),
        "latest_long_short_return": latest_backtest.get("long_short_return"),
        "latest_sharpe": latest_backtest.get("sharpe"),
        "latest_stability": latest_stability.get("stability_score"),
    }
    warnings = []
    if not evaluations and not backtests:
        warnings.append("WARN_FACTOR_HISTORY_EMPTY")
    if num(latest_eval.get("coverage")) is not None and num(latest_eval.get("coverage")) < 0.5:
        warnings.append("WARN_FACTOR_COVERAGE_LOW")
    return ctx.base_export(
        "factor_history",
        generated_from,
        f"Persisted history for factor {report.get('factor') or 'all factors'} summarized.",
        metrics,
        ["historical factor diagnostics are persisted"],
        warnings,
        ["compare IC history", "review coverage trend", "run factor-rank"],
        [],
        [],
    )


def export_factor_rank(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    top = report.get("top_factors") or []
    worst = report.get("worst_factors") or []
    stable = report.get("most_stable_factors") or []
    top_factor = top[0] if top else {}
    metrics = {
        "top_factor": top_factor.get("factor_name"),
        "top_factor_health": top_factor.get("health_score"),
        "top_factor_ic": top_factor.get("ic"),
        "top_factor_coverage": top_factor.get("coverage"),
        "top_factors": [row.get("factor_name") for row in top[:5]],
        "worst_factors": [row.get("factor_name") for row in worst[:5]],
        "most_stable_factors": [row.get("factor_name") for row in stable[:5]],
    }
    warnings = []
    if top_factor and num(top_factor.get("coverage")) is not None and num(top_factor.get("coverage")) < 0.5:
        warnings.append("WARN_TOP_FACTOR_LOW_COVERAGE")
    return ctx.base_export(
        "factor_rank",
        generated_from,
        "Factor ranking report summarized persisted factor quality diagnostics.",
        metrics,
        [f"top factor: {top_factor.get('factor_name')}" if top_factor else "no ranked factors available"],
        warnings,
        ["increase coverage before production use", "inspect worst factors", "run walk-forward validation"],
        [],
        [],
    )


EXPORT_SPECS = (
    export_spec("multi_factor", 70, lambda report: (report.get("metadata") or {}).get("report_type") == "multi_factor" or {"factor_families", "family_weights", "confidence", "scores"}.issubset(report), export_multi_factor),
    export_spec("factor_backtest", 50, lambda report: "factor" in report and "holding_period" in report and "long_short_return" in report, export_factor_backtest),
    export_spec("factor_eval", 60, lambda report: "factor" in report and ("forward_days" in report or "ic_mean" in report) and "decay" in report, export_factor_eval),
    export_spec("factor_store_summary", 20, metadata_type("factor_store_summary"), export_factor_store_summary),
    export_spec("factor_history", 20, metadata_type("factor_history"), export_factor_history),
    export_spec("factor_rank", 20, metadata_type("factor_rank"), export_factor_rank),
)
