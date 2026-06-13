"""Regime report agent exporters."""

from __future__ import annotations

from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, clean_warnings
from quant.reports.agent_export.models import AgentExport
from quant.reports.agent_export.specs import export_spec, metadata_type


def export_regime_detection(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    current = report.get("current_regime") or {}
    metrics = {
        "benchmark": report.get("benchmark"),
        "current_regime": current.get("regime"),
        "date": current.get("date"),
        "volatility": current.get("volatility"),
        "trend_strength": current.get("trend_strength"),
        "drawdown": current.get("drawdown"),
        "confidence": current.get("confidence"),
        "regime_counts": report.get("regime_counts"),
    }
    return ctx.base_export(
        "regime_detection",
        generated_from,
        f"Current market regime is {current.get('regime', 'UNKNOWN')} based on deterministic historical diagnostics.",
        metrics,
        [f"current regime: {current.get('regime', 'UNKNOWN')}"],
        clean_warnings(report.get("warnings")),
        ["review factor performance by regime", "run regime-rank", "compare current exposures with regime diagnostics"],
        [],
        ["regime detection is observational research evidence, not a forecast or trading recommendation"],
    )


def export_regime_history(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    current = report.get("current_regime") or {}
    return ctx.base_export(
        "regime_history",
        generated_from,
        "Persisted market regime history summarized.",
        {
            "current_regime": current.get("regime"),
            "history_rows": len(report.get("history") or []),
            "regime_counts": report.get("regime_counts"),
        },
        [f"current regime: {current.get('regime', 'UNKNOWN')}"],
        clean_warnings(report.get("warnings")),
        ["run regime-report", "review regime transitions"],
        [],
        ["regime history is not a timing signal or trading recommendation"],
    )


def export_regime_report(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    current = report.get("current_regime") or {}
    performance = report.get("factor_performance_by_regime") or {}
    return ctx.base_export(
        "regime_report",
        generated_from,
        f"Regime diagnostics report for current regime {current.get('regime', 'UNKNOWN')}.",
        {
            "current_regime": current.get("regime"),
            "regime_counts": report.get("regime_counts"),
            "regimes_with_factor_history": sorted(performance),
        },
        ["factor performance by regime available" if performance else "no factor regime history available"],
        clean_warnings(report.get("warnings")),
        ["save factor-eval with --save-regime-history", "run regime-rank"],
        [],
        ["factor-by-regime diagnostics are observational research summaries, not predictions"],
    )


def export_regime_rank(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    current = report.get("current_regime") or {}
    best = report.get("best_by_regime") or {}
    current_rows = best.get(current.get("regime")) or []
    top = current_rows[0] if current_rows else {}
    return ctx.base_export(
        "regime_rank",
        generated_from,
        "Regime-aware factor ranking summarized as observational research evidence.",
        {
            "current_regime": current.get("regime"),
            "top_factor_current_regime": top.get("factor_name"),
            "top_factor_health": top.get("health_score"),
            "regimes_ranked": sorted(best),
            "most_stable_factors": [
                row.get("factor_name")
                for row in (report.get("most_stable_across_regimes") or [])[:5]
            ],
        },
        [f"top current-regime factor: {top.get('factor_name')}" if top else "no current-regime factor ranking available"],
        clean_warnings(report.get("warnings")),
        ["review momentum exposure", "compare factor stability across regimes", "increase factor regime history"],
        [],
        ["regime rankings are diagnostics only, not forecasts, timing signals, or investment advice"],
    )


EXPORT_SPECS = (
    export_spec("regime_detection", 20, metadata_type("regime_detection"), export_regime_detection),
    export_spec("regime_history", 20, metadata_type("regime_history"), export_regime_history),
    export_spec("regime_report", 20, metadata_type("regime_report"), export_regime_report),
    export_spec("regime_rank", 20, metadata_type("regime_rank"), export_regime_rank),
)
