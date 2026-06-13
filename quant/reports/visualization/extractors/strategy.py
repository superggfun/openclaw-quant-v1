"""Strategy DSL and gate visualization extractors."""

from __future__ import annotations

from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder
from quant.reports.visualization.extractors.common import finite, keep
from quant.reports.visualization.specs import report_spec


def strategy_list_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    valid = sum(1 for row in report.get("strategies") or [] if row.get("valid"))
    total = len(report.get("strategies") or [])
    return keep(builder.bar_chart(prefix, "strategy_validity", "Strategy Validity", {"valid": valid, "invalid": total - valid}))


def strategy_definition_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    strategy = report.get("strategy") or {}
    portfolio = strategy.get("portfolio") or {}
    return keep(
        builder.bar_chart(prefix, "factor_allocation", "Factor Allocation", _factor_weights(strategy)),
        builder.bar_chart(
            prefix,
            "portfolio_constraints",
            "Portfolio Constraints",
            {
                "max_position_weight": portfolio.get("max_position_weight"),
                "cash_buffer": portfolio.get("cash_buffer"),
            },
        ),
    )


def strategy_validation_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return keep(
        builder.bar_chart(
            prefix,
            "validation_status",
            "Validation Status",
            {"errors": len(report.get("errors") or []), "warnings": len(report.get("warnings") or []), "valid": 1 if report.get("valid") else 0},
        )
    )


def strategy_run_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    summary = report.get("trade_sim_summary") or {}
    strategy = report.get("strategy") or {}
    return keep(
        builder.bar_chart(
            prefix,
            "strategy_summary",
            "Strategy Summary",
            {
                "total_return": summary.get("total_return"),
                "max_drawdown": summary.get("max_drawdown"),
                "total_cost": summary.get("total_cost"),
            },
        ),
        builder.bar_chart(prefix, "factor_allocation", "Factor Allocation", _factor_weights(strategy)),
    )


def strategy_gate_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    gates = report.get("gate_results") or []
    status_order = {"PASS": 1, "WARNING": 2, "FAIL": 3, "REJECTED": 4}
    status_values = {gate.get("gate_name", f"gate_{index + 1}"): status_order.get(gate.get("status"), 0) for index, gate in enumerate(gates)}
    warning_counts = {
        gate.get("gate_name", f"gate_{index + 1}"): len(gate.get("warnings") or []) + len(gate.get("rejection_reasons") or [])
        for index, gate in enumerate(gates)
    }
    metrics = {}
    for gate in gates:
        name = str(gate.get("gate_name", "gate"))
        for key, value in (gate.get("evidence") or {}).items():
            if finite(value):
                metrics[f"{name}:{key}"] = value
    return keep(
        builder.bar_chart(prefix, "gate_status_summary", "Gate Status Summary", status_values),
        builder.bar_chart(prefix, "warning_count_by_gate", "Warning Count By Gate", warning_counts),
        builder.bar_chart(prefix, "evidence_metric", "Evidence Metrics", metrics),
    )


def _factor_weights(strategy: dict[str, Any]) -> dict[str, Any]:
    return {
        item.get("name", f"factor_{index + 1}"): item.get("weight", 0.0)
        for index, item in enumerate(strategy.get("factors") or [])
        if isinstance(item, dict)
    }


REPORT_SPECS = (
    report_spec("strategy_list", ("strategy_validity",), strategy_list_charts),
    report_spec("strategy_definition", ("factor_allocation", "portfolio_constraints"), strategy_definition_charts),
    report_spec("strategy_validation", ("validation_status",), strategy_validation_charts),
    report_spec("strategy_run", ("strategy_summary", "factor_allocation"), strategy_run_charts),
    report_spec("strategy_gate", ("gate_status_summary", "warning_count_by_gate", "evidence_metric"), strategy_gate_charts),
)
