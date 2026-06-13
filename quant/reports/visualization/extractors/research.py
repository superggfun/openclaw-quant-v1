"""Research workflow visualization extractors."""

from __future__ import annotations

from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder
from quant.reports.visualization.extractors.common import keep
from quant.reports.visualization.specs import report_spec


def research_run_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    summary = report.get("daily_research_summary") or {}
    trade = summary.get("trade_sim_summary") or {}
    factor_stability = summary.get("factor_stability_summary") or {}
    factor_scores = {
        factor: values.get("icir")
        for factor, values in factor_stability.items()
        if isinstance(values, dict)
    }
    artifact_counts = {
        "reports": len(report.get("generated_reports") or []),
        "visualizations": len(report.get("generated_visualizations") or []),
        "agent_exports": len(report.get("agent_exports") or []),
    }
    statuses = {}
    for step in report.get("pipeline_steps") or []:
        status = str(step.get("status") or "UNKNOWN")
        statuses[status] = statuses.get(status, 0) + 1
    return keep(
        builder.bar_chart(prefix, "pipeline_status", "Pipeline Step Status", statuses),
        builder.bar_chart(
            prefix,
            "trade_simulation",
            "Trade Simulation Metrics",
            {
                "return": trade.get("total_return"),
                "drawdown": trade.get("max_drawdown"),
                "cost": trade.get("total_cost"),
            },
        ),
        builder.bar_chart(prefix, "factor_summary", "Factor ICIR Summary", factor_scores),
        builder.bar_chart(prefix, "artifact_counts", "Generated Artifact Counts", artifact_counts),
    )


def research_status_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    latest = report.get("latest_run") or {}
    return keep(
        builder.bar_chart(prefix, "latest_run", "Latest Run", {"duration": latest.get("duration"), "trade_return": latest.get("trade_sim_return")}),
    )


def research_history_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    counts = (report.get("summary") or {}).get("status_counts") or {}
    return keep(builder.bar_chart(prefix, "run_status", "Run Status Counts", counts))


REPORT_SPECS = (
    report_spec("research_run", ("pipeline_status", "trade_simulation", "factor_summary", "artifact_counts"), research_run_charts),
    report_spec("research_status", ("latest_run",), research_status_charts),
    report_spec("research_history", ("run_status",), research_history_charts),
)
