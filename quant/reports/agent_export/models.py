"""Agent export data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SUPPORTED_FORMATS = {"text", "markdown", "json"}


@dataclass(frozen=True)
class AgentExport:
    report_type: str
    generated_from: str
    summary: str
    key_metrics: dict[str, Any]
    key_findings: list[str]
    warnings: list[str]
    recommended_next_steps: list[str]
    action_candidates: list[str]
    data_quality_notes: list[str]
    visual_summary_paths: list[str]
    visualization_paths: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "generated_from": self.generated_from,
            "summary": self.summary,
            "key_metrics": self.key_metrics,
            "key_findings": self.key_findings,
            "warnings": self.warnings,
            "recommended_next_steps": self.recommended_next_steps,
            "action_candidates": self.action_candidates,
            "data_quality_notes": self.data_quality_notes,
            "visual_summary_paths": self.visual_summary_paths,
            "visualization_paths": self.visualization_paths,
        }
