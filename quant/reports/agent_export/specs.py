"""Agent export spec types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext
from quant.reports.agent_export.models import AgentExport

Detector = Callable[[dict[str, Any]], bool]
Exporter = Callable[[AgentExportContext, dict[str, Any], str], AgentExport]


@dataclass(frozen=True)
class ExportSpec:
    report_type: str
    priority: int
    matches: Detector
    export: Exporter


def export_spec(report_type: str, priority: int, matches: Detector, export: Exporter) -> ExportSpec:
    return ExportSpec(report_type=report_type, priority=priority, matches=matches, export=export)


def metadata_type(*report_types: str) -> Detector:
    allowed = set(report_types)

    def matches(report: dict[str, Any]) -> bool:
        return (report.get("metadata") or {}).get("report_type") in allowed

    return matches


def has_keys(*keys: str) -> Detector:
    required = set(keys)

    def matches(report: dict[str, Any]) -> bool:
        return required.issubset(report)

    return matches
