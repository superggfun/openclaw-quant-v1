"""Performance profile visualization extractors."""

from __future__ import annotations

from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder
from quant.reports.visualization.extractors.common import keep
from quant.reports.visualization.specs import report_spec


def performance_profile_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    runtime = {
        category: values.get("runtime_seconds")
        for category, values in ((report.get("runtime_breakdown") or {}).get("by_category") or {}).items()
        if isinstance(values, dict)
    }
    modules = {
        row.get("module", f"module_{index + 1}"): row.get("runtime_seconds")
        for index, row in enumerate(report.get("slowest_modules") or [])
        if isinstance(row, dict)
    }
    queries = {
        row.get("name", f"query_{index + 1}"): row.get("runtime_seconds")
        for index, row in enumerate(report.get("slowest_queries") or [])
        if isinstance(row, dict)
    }
    call_counts = {
        category: values.get("count")
        for category, values in ((report.get("runtime_breakdown") or {}).get("by_category") or {}).items()
        if isinstance(values, dict)
    }
    return keep(
        builder.bar_chart(prefix, "runtime_breakdown", "Runtime Breakdown", runtime),
        builder.bar_chart(prefix, "slowest_modules", "Slowest Modules", modules),
        builder.bar_chart(prefix, "slowest_queries", "Slowest Queries", queries),
        builder.bar_chart(prefix, "call_counts", "Call Counts", call_counts),
    )


REPORT_SPECS = (
    report_spec("performance_profile", ("runtime_breakdown", "slowest_modules", "slowest_queries", "call_counts"), performance_profile_charts),
)
