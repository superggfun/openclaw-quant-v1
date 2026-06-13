"""Generate visual chart reports from existing JSON reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder
from quant.reports.visualization.registry import (
    EXPECTED_CHARTS_BY_REPORT_TYPE,
    REPORT_SPECS,
    SUPPORTED_REPORT_TYPES,
)
from quant.reports.visualization.summary import metrics_for_dashboard, write_visual_summary


@dataclass(frozen=True)
class VisualizationResult:
    report_type: str
    source_report: str
    output_dir: str
    charts: list[dict[str, str]]
    dashboard_path: str
    warnings: list[str]
    visual_summary_path: str

    def to_report(self) -> dict:
        return {
            "report_type": self.report_type,
            "source_report": self.source_report,
            "output_dir": self.output_dir,
            "charts": self.charts,
            "dashboard_path": self.dashboard_path,
            "visual_summary_path": self.visual_summary_path,
            "warnings": self.warnings,
        }


class ReportVisualizer:
    """Build deterministic SVG, PNG, HTML, and JSON summaries from report JSON."""

    def __init__(self, output_dir: str | Path = "reports/charts") -> None:
        self.output_dir = Path(output_dir)
        self.exporter = AgentExporter()

    def visualize_file(self, report_path: str | Path, output_dir: str | Path | None = None) -> VisualizationResult:
        path = Path(report_path)
        report = self._read_report(path)
        report_type = self.exporter.detect_report_type(report)
        spec = REPORT_SPECS.get(report_type)
        if spec is None:
            raise ValueError(f"unsupported report type for visualization: {report_type}")

        builder = ChartBuilder(output_dir or self.output_dir)
        prefix = self._prefix(path)
        charts = spec.build_charts(builder, prefix, report)
        metrics = metrics_for_dashboard(report_type, report)
        warnings = self._warnings(report) + self._chart_warnings(report_type, charts)
        dashboard = builder.dashboard(
            prefix=prefix,
            title=f"{report_type} visualization",
            report_type=report_type,
            metrics=metrics,
            charts=charts,
            warnings=warnings,
            notes=self._notes(report),
        )
        visual_summary = write_visual_summary(
            output_dir=builder.output_dir,
            prefix=prefix,
            report_type=report_type,
            source_report=str(path),
            metrics=metrics,
            charts=charts,
            expected_charts=spec.expected_charts,
            warnings=warnings,
            dashboard_path=str(dashboard),
        )
        return VisualizationResult(
            report_type=report_type,
            source_report=str(path),
            output_dir=str(builder.output_dir),
            charts=[chart.to_dict() for chart in charts],
            dashboard_path=str(dashboard),
            warnings=warnings,
            visual_summary_path=str(visual_summary),
        )

    @staticmethod
    def _read_report(path: Path) -> dict[str, Any]:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"report file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"report file is not valid JSON: {path}") from exc
        if not isinstance(report, dict):
            raise ValueError("report must contain a JSON object")
        return report

    @staticmethod
    def _warnings(report: dict[str, Any]) -> list[str]:
        warnings = report.get("warnings") or []
        if isinstance(warnings, list):
            return [str(warning.get("code") if isinstance(warning, dict) else warning) for warning in warnings]
        return [str(warnings)]

    @staticmethod
    def _chart_warnings(report_type: str, charts: list[ChartArtifact]) -> list[str]:
        expected = EXPECTED_CHARTS_BY_REPORT_TYPE.get(report_type, frozenset())
        generated = {chart.chart_id for chart in charts}
        return [
            f"VISUALIZATION_SKIPPED_CHART: {chart_id} missing required report fields"
            for chart_id in sorted(expected - generated)
        ]

    @staticmethod
    def _notes(report: dict[str, Any]) -> list[str]:
        notes = report.get("interpretation_notes") or []
        return [str(note) for note in notes] if isinstance(notes, list) else [str(notes)]

    @staticmethod
    def _prefix(path: Path) -> str:
        return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in path.stem)


__all__ = [
    "EXPECTED_CHARTS_BY_REPORT_TYPE",
    "SUPPORTED_REPORT_TYPES",
    "ReportVisualizer",
    "VisualizationResult",
]
