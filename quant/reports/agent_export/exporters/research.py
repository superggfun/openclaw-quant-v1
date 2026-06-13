"""Research workflow agent exporters."""

from __future__ import annotations

from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, clean_warnings
from quant.reports.agent_export.models import AgentExport
from quant.reports.agent_export.specs import export_spec, metadata_type


def export_research_run(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    summary = report.get("daily_research_summary") or {}
    trade = summary.get("trade_sim_summary") or {}
    metrics = {
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "current_regime": summary.get("current_regime"),
        "best_factors": summary.get("best_factors"),
        "weak_factors": summary.get("weak_factors"),
        "trade_sim_return": trade.get("total_return"),
        "trade_sim_final_equity": trade.get("final_equity"),
        "trade_sim_max_drawdown": trade.get("max_drawdown"),
        "generated_reports": len(report.get("generated_reports") or []),
        "generated_visualizations": len(report.get("generated_visualizations") or []),
    }
    findings = []
    if summary.get("current_regime"):
        findings.append(f"current regime: {summary['current_regime']}")
    if summary.get("best_factors"):
        findings.append(f"top factor: {summary['best_factors'][0]}")
    if trade.get("total_return") is not None:
        findings.append(f"trade simulation return: {trade['total_return']}")
    return ctx.base_export(
        "research_run",
        generated_from,
        "Daily research pipeline completed as an offline diagnostics workflow.",
        metrics,
        findings,
        clean_warnings(report.get("warnings")),
        report.get("recommended_next_checks") or ["review generated artifacts", "inspect warnings"],
        [],
        ["scheduler output is research automation, not investment advice or live trading"],
    )


def export_research_status(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    latest = report.get("latest_run") or {}
    return ctx.base_export(
        "research_status",
        generated_from,
        f"Latest research scheduler status is {report.get('status', 'NO_RUNS')}.",
        {"status": report.get("status"), "latest_run_id": latest.get("run_id"), "latest_regime": latest.get("regime")},
        [],
        clean_warnings(latest.get("warnings")),
        ["run research-run", "review research-history"],
        [],
        ["research status is operational metadata only"],
    )


def export_research_validation(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    cache = report.get("cache_summary") or {}
    coverage = report.get("coverage_statistics") or {}
    metrics = {
        "mode": report.get("mode"),
        "status": report.get("status"),
        "runtime_seconds": report.get("runtime_seconds"),
        "evaluated_symbols": coverage.get("evaluated_symbols"),
        "price_coverage": coverage.get("price_coverage"),
        "fundamental_coverage": coverage.get("fundamental_coverage"),
        "cache_enabled": cache.get("cache_enabled"),
        "matrix_hits": cache.get("matrix_hits"),
        "matrix_misses": cache.get("matrix_misses"),
        "factor_value_hits": cache.get("factor_value_hits"),
        "factor_value_misses": cache.get("factor_value_misses"),
        "top_factor": (report.get("top_10_factors") or [{}])[0].get("factor"),
    }
    warnings = [row.get("code") for row in report.get("warning_statistics", []) if row.get("code")]
    findings = [
        "bounded validation completed with partial-result safeguards",
        "factor matrix cache was enabled" if cache.get("cache_enabled") else "factor matrix cache was disabled",
    ]
    return ctx.base_export(
        "research_validation",
        generated_from,
        "Research validation summarized bounded evidence collection and runtime diagnostics.",
        metrics,
        findings,
        warnings,
        report.get("recommendations") or ["review slowest steps", "expand validation only when runtime budget allows"],
        [],
        ["Research validation is offline evidence collection, not parameter tuning or trading authorization."],
    )


def export_research_history(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    runs = report.get("runs") or []
    return ctx.base_export(
        "research_history",
        generated_from,
        "Research scheduler history summarized.",
        {"run_count": len(runs), "status_counts": (report.get("summary") or {}).get("status_counts")},
        [f"latest run: {runs[0].get('run_id')}" if runs else "no scheduler runs found"],
        [],
        ["review repeated failures", "compare daily regime and factor summaries"],
        [],
        ["research history is offline workflow telemetry"],
    )


EXPORT_SPECS = (
    export_spec("research_run", 20, metadata_type("research_run"), export_research_run),
    export_spec("research_status", 20, metadata_type("research_status"), export_research_status),
    export_spec("research_validation", 20, metadata_type("research_validation"), export_research_validation),
    export_spec("research_history", 20, metadata_type("research_history"), export_research_history),
)
