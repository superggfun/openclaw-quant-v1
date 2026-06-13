"""Fundamental data report agent exporters."""

from __future__ import annotations

from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, clean_warnings
from quant.reports.agent_export.models import AgentExport
from quant.reports.agent_export.specs import export_spec, metadata_type


def export_fundamental_import(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    summary = report.get("summary") or {}
    metrics = {
        "inserted": summary.get("inserted"),
        "updated": summary.get("updated"),
        "skipped": summary.get("skipped"),
        "errors": summary.get("errors"),
        "file": (report.get("parameters") or {}).get("file"),
        "statement": (report.get("parameters") or {}).get("statement"),
    }
    return ctx.base_export(
        "fundamental_import",
        generated_from,
        "Fundamental CSV import completed.",
        metrics,
        ["fundamental data imported into SQLite"],
        clean_warnings(report.get("warnings")),
        ["run fundamental coverage", "run fundamental quality", "review report_date alignment"],
        [],
        report.get("no_lookahead_notes") or [],
    )


def export_fundamental_coverage(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    coverage = report.get("coverage") or {}
    warnings = clean_warnings(report.get("warnings"))
    if coverage.get("symbols_missing_fundamental_data", 0):
        warnings.append("WARN_FUNDAMENTAL_COVERAGE_GAP")
    metrics = {
        "readiness_score": coverage.get("readiness_score"),
        "total_symbols": coverage.get("total_symbols"),
        "symbols_covered": coverage.get("symbols_with_any_fundamental_data"),
        "symbols_missing": coverage.get("symbols_missing_fundamental_data"),
        "missing_symbols": (coverage.get("missing_symbols") or [])[:10],
        "statement_coverage": coverage.get("statement_coverage"),
        "latest_report_date": coverage.get("latest_report_date"),
    }
    return ctx.base_export(
        "fundamental_coverage",
        generated_from,
        f"Fundamental coverage readiness score is {coverage.get('readiness_score')}.",
        metrics,
        ["fundamental coverage report generated"],
        warnings,
        ["import missing symbols", "run fundamental quality", "validate report_date freshness"],
        [],
        report.get("no_lookahead_notes") or [],
    )


def export_fundamental_quality(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    summary = report.get("summary") or {}
    warnings = clean_warnings(report.get("warnings"))
    metrics = {
        "status": summary.get("status"),
        "symbols_checked": summary.get("symbols_checked"),
        "warnings": summary.get("warnings"),
        "checks": summary.get("checks"),
        "top_warnings": warnings[:10],
    }
    return ctx.base_export(
        "fundamental_quality",
        generated_from,
        f"Fundamental quality status is {summary.get('status')}.",
        metrics,
        ["fundamental quality checks completed"],
        warnings,
        ["fix stale reports", "review missing fields", "check currency consistency"],
        [],
        report.get("no_lookahead_notes") or [],
    )


EXPORT_SPECS = (
    export_spec("fundamental_import", 140, metadata_type("fundamental_import"), export_fundamental_import),
    export_spec("fundamental_coverage", 140, metadata_type("fundamental_coverage"), export_fundamental_coverage),
    export_spec("fundamental_quality", 140, metadata_type("fundamental_quality"), export_fundamental_quality),
)
