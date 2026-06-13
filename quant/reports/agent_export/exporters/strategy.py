"""Strategy report agent exporters."""

from __future__ import annotations

from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, clean_warnings
from quant.reports.agent_export.models import AgentExport
from quant.reports.agent_export.specs import export_spec, metadata_type


def export_strategy_list(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    strategies = report.get("strategies") or []
    return ctx.base_export(
        "strategy_list",
        generated_from,
        f"Strategy registry contains {len(strategies)} offline research definitions.",
        {
            "strategy_count": len(strategies),
            "strategies": [row.get("name") for row in strategies[:10]],
        },
        ["strategy definitions are versioned research objects"],
        clean_warnings(report.get("warnings")),
        ["validate a strategy before running", "run strategy-run for offline simulation"],
        [],
        ["Strategy DSL does not enable broker execution or live trading."],
    )


def export_strategy_definition(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    strategy = report.get("strategy") or {}
    validation = report.get("validation") or {}
    return ctx.base_export(
        "strategy_definition",
        generated_from,
        f"Strategy {strategy.get('name')} version {strategy.get('version')} summarized.",
        {
            "name": strategy.get("name"),
            "version": strategy.get("version"),
            "factor_count": len(strategy.get("factors") or []),
            "portfolio_method": (strategy.get("portfolio") or {}).get("method"),
            "valid": validation.get("valid"),
        },
        ["strategy DSL definition loaded"],
        clean_warnings(validation.get("warnings")),
        ["run strategy-validate", "run strategy-run offline"],
        [],
        ["Strategy definitions are reproducibility metadata, not investment advice."],
    )


def export_strategy_validation(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    return ctx.base_export(
        "strategy_validation",
        generated_from,
        f"Strategy validation {'passed' if report.get('valid') else 'failed'} for {report.get('strategy_name')}.",
        {
            "strategy_name": report.get("strategy_name"),
            "strategy_version": report.get("strategy_version"),
            "valid": report.get("valid"),
            "errors": report.get("errors"),
            "gates": report.get("gates"),
        },
        ["validation gates checked"],
        clean_warnings(report.get("warnings")) + [f"ERROR: {error}" for error in report.get("errors", [])],
        ["fix validation errors before research runs", "run walk-forward if required"],
        [],
        ["Validation gates are deterministic checks, not return guarantees."],
    )


def export_strategy_run(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    summary = report.get("trade_sim_summary") or {}
    return ctx.base_export(
        "strategy_run",
        generated_from,
        f"Strategy {report.get('strategy_name')} ran through offline historical simulation.",
        {
            "strategy_name": report.get("strategy_name"),
            "strategy_version": report.get("strategy_version"),
            "status": report.get("status"),
            "final_equity": summary.get("final_equity"),
            "total_return": summary.get("total_return"),
            "max_drawdown": summary.get("max_drawdown"),
            "trade_count": summary.get("trade_count"),
            "trade_sim_report_path": (report.get("artifacts") or {}).get("trade_sim_report_path"),
        },
        ["strategy DSL orchestrated existing engines"],
        clean_warnings(report.get("warnings")),
        ["review trade simulation report", "run walk-forward validation", "inspect strategy validation gates"],
        [],
        ["Strategy runs are offline research simulation only, not live trading."],
    )


def export_strategy_gate(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    gates = report.get("gate_results") or []
    by_status = (report.get("evidence_summary") or {}).get("by_status") or {}
    failed = [gate.get("gate_name") for gate in gates if gate.get("status") in {"FAIL", "REJECTED"}]
    warning_gates = [gate.get("gate_name") for gate in gates if gate.get("status") == "WARNING"]
    return ctx.base_export(
        "strategy_gate",
        generated_from,
        f"Strategy gates completed with overall status {report.get('overall_status')}.",
        {
            "strategy_name": report.get("strategy_name"),
            "strategy_version": report.get("strategy_version"),
            "overall_status": report.get("overall_status"),
            "gate_count": len(gates),
            "by_status": by_status,
            "warning_gates": warning_gates,
            "rejection_reasons": report.get("rejection_reasons") or [],
        },
        [
            "strategy gate report is quality control for offline research readiness",
            f"{len(failed)} gates failed or rejected" if failed else "no failed or rejected gates",
        ],
        clean_warnings(report.get("warnings")) + [f"REJECTION: {reason}" for reason in report.get("rejection_reasons", [])],
        report.get("recommended_next_checks") or ["review weak gates before relying on the strategy research"],
        [],
        [
            "Gates are deterministic diagnostics, not investment advice.",
            "Gate reports do not submit orders or mutate live accounts.",
        ],
    )


EXPORT_SPECS = (
    export_spec("strategy_list", 20, metadata_type("strategy_list"), export_strategy_list),
    export_spec("strategy_definition", 20, metadata_type("strategy_definition"), export_strategy_definition),
    export_spec("strategy_validation", 20, metadata_type("strategy_validation"), export_strategy_validation),
    export_spec("strategy_run", 20, metadata_type("strategy_run"), export_strategy_run),
    export_spec("strategy_gate", 20, metadata_type("strategy_gate"), export_strategy_gate),
)
