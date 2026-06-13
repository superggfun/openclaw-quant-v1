"""Visualization report spec types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder


ChartFactory = Callable[[ChartBuilder, str, dict[str, Any]], list[ChartArtifact]]


@dataclass(frozen=True)
class ReportSpec:
    report_type: str
    expected_charts: frozenset[str]
    build_charts: ChartFactory


def report_spec(report_type: str, chart_ids: tuple[str, ...], build_charts: ChartFactory) -> ReportSpec:
    return ReportSpec(report_type=report_type, expected_charts=frozenset(chart_ids), build_charts=build_charts)
