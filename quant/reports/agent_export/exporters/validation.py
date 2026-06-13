"""Validation and performance agent exporters."""

from __future__ import annotations

from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, clean_warnings, num
from quant.reports.agent_export.models import AgentExport
from quant.reports.agent_export.specs import export_spec, metadata_type


def export_strategy_eval(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    summary_metrics = report.get("summary_metrics") or {}
    attribution = report.get("attribution") or {}
    assessment = "positive historical performance" if num(summary_metrics.get("total_return")) and num(summary_metrics.get("total_return")) > 0 else "weak or negative historical performance"
    warnings = clean_warnings(report.get("warnings"))
    warnings.extend(
        ctx.performance_warnings(
            total_return=summary_metrics.get("total_return"),
            sharpe=summary_metrics.get("sharpe_ratio"),
            drawdown=summary_metrics.get("max_drawdown"),
        )
    )
    metrics = {
        "total_return": summary_metrics.get("total_return"),
        "annual_return": summary_metrics.get("annual_return"),
        "sharpe": summary_metrics.get("sharpe_ratio"),
        "max_drawdown": summary_metrics.get("max_drawdown"),
        "total_cost": summary_metrics.get("total_cost"),
        "turnover": summary_metrics.get("turnover"),
        "cost_to_return_ratio": summary_metrics.get("cost_to_return_ratio"),
        "top_contributors": attribution.get("top_positive_contributors", [])[:3],
        "top_detractors": attribution.get("top_negative_contributors", [])[:3],
    }
    return ctx.base_export(
        "strategy_eval",
        generated_from,
        f"Strategy evaluation indicates {assessment}.",
        metrics,
        [assessment],
        warnings,
        ["run walk-forward validation", "inspect cost drag", "review drawdown"],
        ["compare against benchmark", "export backtest summary"],
        [],
    )


def export_walk_forward(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    summary = report.get("summary") or {}
    warnings = clean_warnings(report.get("warnings"))
    stability = (report.get("stability_analysis") or {}).get("factor_stability_ranking") or []
    top_stable = stability[0] if stability else {}
    metrics = {
        "strategy": report.get("strategy"),
        "fold_count": summary.get("fold_count"),
        "average_train_return": summary.get("average_train_return"),
        "average_test_return": summary.get("average_test_return"),
        "average_train_sharpe": summary.get("average_train_sharpe"),
        "average_test_sharpe": summary.get("average_test_sharpe"),
        "average_ic": summary.get("average_ic"),
        "average_rank_ic": summary.get("average_rank_ic"),
        "top_stable_factor": top_stable.get("factor"),
        "top_stable_factor_classification": top_stable.get("classification"),
    }
    findings = []
    if top_stable:
        findings.append(f"{top_stable.get('factor')} classified as {top_stable.get('classification')}")
    if any("WARN_OVERFIT" in warning for warning in warnings):
        findings.append("overfitting detected")
    if any("WARN_FACTOR_DECAY" in warning for warning in warnings):
        findings.append("factor decay detected")
    assessment = "walk-forward validation completed"
    return ctx.base_export(
        "walk_forward",
        generated_from,
        assessment,
        metrics,
        findings or [assessment],
        warnings,
        ["compare folds", "review factor stability", "inspect out-of-sample drawdowns"],
        [],
        [],
    )


def export_performance_profile(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    slowest = report.get("slowest_modules") or []
    queries = report.get("slowest_queries") or []
    top = slowest[0] if slowest else {}
    metrics = {
        "total_runtime_seconds": (report.get("summary") or {}).get("total_runtime_seconds"),
        "event_count": (report.get("summary") or {}).get("event_count"),
        "slowest_module": top.get("module"),
        "slowest_module_runtime": top.get("runtime_seconds"),
        "database_runtime_seconds": (report.get("database_profile") or {}).get("runtime_seconds"),
        "query_count": (report.get("database_profile") or {}).get("query_count"),
        "slowest_query": (queries[0] or {}).get("name") if queries else None,
    }
    findings = [
        f"slowest module: {top.get('module')}" if top else "no slow module recorded",
        "profiling is measurement-only",
    ]
    return ctx.base_export(
        "performance_profile",
        generated_from,
        "Performance profile summarizes runtime bottlenecks without changing quant semantics.",
        metrics,
        findings,
        clean_warnings(report.get("warnings")),
        report.get("recommendations") or ["profile more targets before optimizing"],
        [],
        ["Performance recommendations are candidates for future optimization, not implemented changes."],
    )


EXPORT_SPECS = (
    export_spec("walk_forward", 30, lambda report: {"strategy", "folds", "stability_analysis", "summary"}.issubset(report), export_walk_forward),
    export_spec("strategy_eval", 40, lambda report: {"summary_metrics", "attribution", "robustness_diagnostics"}.issubset(report), export_strategy_eval),
    export_spec("performance_profile", 20, metadata_type("performance_profile"), export_performance_profile),
)
