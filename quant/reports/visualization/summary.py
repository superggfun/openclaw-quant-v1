"""Dashboard and machine-readable visualization summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quant.reports.report_io import write_json_report
from quant.reports.visualization.chart_builder import ChartArtifact


LOW_LLM_VALUE_CHARTS = {
    "artifact_counts",
    "latest_run",
    "run_status",
    "strategy_validity",
    "validation_status",
    "factor_store_counts",
}

DECISION_RELEVANT_CHARTS = {
    "equity_curve",
    "drawdown_curve",
    "monthly_returns",
    "cost_breakdown",
    "liquidity_usage",
    "rejected_trades",
    "slippage",
    "return_attribution",
    "top_contributors",
    "top_detractors",
    "ic_history",
    "rank_ic_history",
    "quintile_returns",
    "factor_decay",
    "long_short_return",
    "turnover",
    "target_weights",
    "risk_contribution",
    "correlation_matrix",
    "fold_returns",
    "train_vs_test_return",
    "train_vs_test_sharpe",
    "factor_stability_ranking",
    "risk_summary",
    "top_holdings",
    "family_contribution",
    "factor_contribution",
    "confidence",
    "stability_ranking",
    "coverage_ranking",
    "regime_frequency",
    "regime_confidence",
    "factor_performance_by_regime",
    "trade_simulation",
    "factor_summary",
    "strategy_summary",
    "gate_status_summary",
    "warning_count_by_gate",
    "evidence_metric",
    "runtime_breakdown",
    "slowest_modules",
    "slowest_queries",
}


def metrics_for_dashboard(report_type: str, report: dict[str, Any]) -> dict[str, Any]:
    if report_type == "strategy_eval":
        return report.get("summary_metrics") or {}
    if report_type == "walk_forward":
        return report.get("summary") or {}
    if report_type == "backtest":
        return report.get("metrics") or {}
    keys = ("strategy", "portfolio_method", "final_equity", "total_return", "max_drawdown", "total_cost", "trade_count", "risk_score", "factor", "ic_mean", "rank_ic_mean", "icir", "method")
    if report_type in {"fundamental_coverage", "fundamental_quality"}:
        return report.get("summary") or {}
    if report_type == "multi_factor":
        confidence = report.get("confidence") or {}
        return {
            "as_of_date": report.get("as_of_date"),
            "weighting_mode": report.get("weighting_mode"),
            "overall_confidence": confidence.get("overall_confidence"),
            "factor_count": len(report.get("factors") or []),
        }
    if report_type == "factor_store_summary":
        return report.get("counts") or {}
    if report_type == "factor_history":
        return {
            "factor": report.get("factor"),
            "evaluation_rows": len(report.get("evaluation_history") or []),
            "backtest_rows": len(report.get("backtest_history") or []),
            "stability_rows": len(report.get("stability_history") or []),
        }
    if report_type == "factor_rank":
        top = (report.get("top_factors") or [{}])[0]
        return {
            "top_factor": top.get("factor_name"),
            "top_factor_health": top.get("health_score"),
            "ranked_count": len(report.get("top_factors") or []),
        }
    if report_type in {"regime_detection", "regime_history", "regime_report", "regime_rank"}:
        current = report.get("current_regime") or {}
        return {
            "current_regime": current.get("regime"),
            "date": current.get("date"),
            "confidence": current.get("confidence"),
            "regime_count": len(report.get("regime_counts") or {}),
        }
    if report_type == "research_run":
        summary = report.get("daily_research_summary") or {}
        trade = summary.get("trade_sim_summary") or {}
        return {
            "status": report.get("status"),
            "current_regime": summary.get("current_regime"),
            "trade_sim_return": trade.get("total_return"),
            "generated_reports": len(report.get("generated_reports") or []),
        }
    if report_type == "research_status":
        latest = report.get("latest_run") or {}
        return {"status": report.get("status"), "latest_run": latest.get("run_id")}
    if report_type == "research_history":
        return (report.get("summary") or {}).get("status_counts") or {}
    if report_type in {"strategy_definition", "strategy_validation", "strategy_run", "strategy_gate"}:
        strategy = report.get("strategy") or {}
        summary = report.get("trade_sim_summary") or {}
        return {
            "strategy_name": report.get("strategy_name") or strategy.get("name"),
            "strategy_version": report.get("strategy_version") or strategy.get("version"),
            "status": report.get("status") or report.get("overall_status"),
            "valid": (report.get("validation") or report).get("valid"),
            "total_return": summary.get("total_return"),
            "gate_count": len(report.get("gate_results") or []),
        }
    if report_type == "performance_profile":
        summary = report.get("summary") or {}
        database = report.get("database_profile") or {}
        slowest = (report.get("slowest_modules") or [{}])[0]
        return {
            "total_runtime_seconds": summary.get("total_runtime_seconds"),
            "event_count": summary.get("event_count"),
            "slowest_module": slowest.get("module"),
            "slowest_module_runtime": slowest.get("runtime_seconds"),
            "query_count": database.get("query_count"),
            "database_runtime_seconds": database.get("runtime_seconds"),
        }
    if report_type == "strategy_list":
        return {"strategy_count": report.get("strategy_count")}
    return {key: report.get(key) for key in keys if key in report}


def write_visual_summary(
    output_dir: Path,
    prefix: str,
    report_type: str,
    source_report: str,
    metrics: dict[str, Any],
    charts: list[ChartArtifact],
    expected_charts: set[str] | frozenset[str],
    warnings: list[str],
    dashboard_path: str,
) -> Path:
    generated = [chart.chart_id for chart in charts]
    missing = sorted(set(expected_charts) - set(generated))
    payload = {
        "report_type": report_type,
        "source_report": source_report,
        "dashboard_path": dashboard_path,
        "metrics": metrics,
        "chart_count": len(charts),
        "generated_chart_ids": generated,
        "missing_chart_ids": missing,
        "decision_relevant_chart_ids": [chart_id for chart_id in generated if chart_id in DECISION_RELEVANT_CHARTS],
        "display_only_chart_ids": [chart_id for chart_id in generated if chart_id in LOW_LLM_VALUE_CHARTS],
        "warnings": warnings,
        "llm_guidance": {
            "prefer_metrics": True,
            "image_paths_are_display_artifacts": True,
            "use_decision_relevant_chart_ids_before_display_only_chart_ids": True,
        },
    }
    path = output_dir / f"{prefix}_visual_summary.json"
    return write_json_report(path, payload, sort_keys=True)
