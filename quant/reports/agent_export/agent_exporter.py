"""Compact report exports for LLM and agent consumers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, estimate_tokens, stringify
from quant.reports.agent_export.models import SUPPORTED_FORMATS, AgentExport
from quant.reports.agent_export.registry import EXPORT_SPECS


class AgentExporter:
    """Convert rich reports into deterministic compact agent summaries."""

    def __init__(self) -> None:
        self.context = AgentExportContext()

    def export_file(
        self,
        report_path: str | Path,
        output_format: str = "text",
        max_tokens: int = 800,
        output_path: str | Path | None = None,
    ) -> str:
        path = Path(report_path)
        report = self._read_report(path)
        export = self.export_report(report, generated_from=str(path))
        rendered = self.render(export, output_format=output_format, max_tokens=max_tokens)
        if output_path:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
        return rendered

    def export_report(self, report: dict[str, Any], generated_from: str = "<memory>") -> AgentExport:
        report_type = self.detect_report_type(report)
        spec = next((candidate for candidate in EXPORT_SPECS if candidate.report_type == report_type and candidate.matches(report)), None)
        if spec is None:
            return self.context.base_export(
                report_type=report_type,
                generated_from=generated_from,
                summary=f"Detected {report_type} report.",
            )
        return spec.export(self.context, report, generated_from)

    def export_protocol(self, protocol_object: Any, generated_from: str = "<protocol>") -> AgentExport:
        to_dict = getattr(protocol_object, "to_dict", None)
        if not callable(to_dict):
            raise ValueError("protocol object must expose to_dict()")
        payload = to_dict()
        protocol_type = protocol_object.__class__.__name__
        warnings = []
        validate = getattr(protocol_object, "validate", None)
        if callable(validate):
            warnings = [f"PROTOCOL_VALIDATION: {error}" for error in validate()]
        metrics = {
            key: payload.get(key)
            for key in ("account_id", "cash", "equity", "market_value", "symbol", "side", "quantity", "status", "target_weight")
            if key in payload
        }
        return self.context.base_export(
            report_type=f"protocol_{protocol_type}",
            generated_from=generated_from,
            summary=f"{protocol_type} protocol object exported for agent context.",
            key_metrics=metrics,
            key_findings=["protocol object is JSON serializable"],
            warnings=warnings,
            recommended_next_steps=["use stable protocol fields for MCP/OpenClaw integration"],
            action_candidates=[],
            data_quality_notes=[],
        )

    def detect_report_type(self, report: dict[str, Any]) -> str:
        for spec in EXPORT_SPECS:
            if spec.matches(report):
                return spec.report_type
        return "unknown"

    def render(self, export: AgentExport, output_format: str = "text", max_tokens: int = 800) -> str:
        normalized_format = output_format.lower().strip()
        if normalized_format not in SUPPORTED_FORMATS:
            raise ValueError("format must be one of: text, markdown, json")
        compact = self._trim_export(export.to_dict(), max_tokens=max_tokens)
        if normalized_format == "json":
            return json.dumps(compact, indent=2, sort_keys=True)
        if normalized_format == "markdown":
            return self._render_markdown(compact)
        return self._render_text(compact)

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
    def _trim_export(export: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        trimmed = json.loads(json.dumps(export, default=str))
        priority_order = ["data_quality_notes", "visualization_paths", "visual_summary_paths", "action_candidates", "key_findings", "recommended_next_steps", "warnings", "key_metrics"]
        for key in priority_order:
            if estimate_tokens(trimmed) <= max_tokens:
                break
            value = trimmed.get(key)
            if isinstance(value, list) and len(value) > 3:
                trimmed[key] = value[:3]
            elif isinstance(value, dict) and len(value) > 6:
                trimmed[key] = {item_key: value[item_key] for item_key in list(value)[:6]}
        if estimate_tokens(trimmed) > max_tokens:
            trimmed["summary"] = str(trimmed.get("summary", ""))[: max(80, max_tokens * 3)]
        return trimmed

    @staticmethod
    def _render_text(export: dict[str, Any]) -> str:
        lines = [
            f"report_type: {export['report_type']}",
            f"generated_from: {export['generated_from']}",
            f"summary: {export['summary']}",
            "key_metrics:",
        ]
        lines.extend(f"- {key}: {stringify(value)}" for key, value in export["key_metrics"].items())
        for section in ("key_findings", "warnings", "recommended_next_steps", "action_candidates", "data_quality_notes", "visual_summary_paths", "visualization_paths"):
            lines.append(f"{section}:")
            lines.extend(f"- {item}" for item in export.get(section, []))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_markdown(export: dict[str, Any]) -> str:
        lines = [
            f"# Agent Export: {export['report_type']}",
            "",
            f"**Generated from:** `{export['generated_from']}`",
            "",
            f"## Summary\n{export['summary']}",
            "",
            "## Key Metrics",
        ]
        lines.extend(f"- `{key}`: {stringify(value)}" for key, value in export["key_metrics"].items())
        for title, key in (
            ("Key Findings", "key_findings"),
            ("Warnings", "warnings"),
            ("Recommended Next Steps", "recommended_next_steps"),
            ("Action Candidates", "action_candidates"),
            ("Data Quality Notes", "data_quality_notes"),
            ("Visual Summary Paths", "visual_summary_paths"),
            ("Visualization Paths", "visualization_paths"),
        ):
            lines.extend(["", f"## {title}"])
            values = export.get(key, [])
            lines.extend(f"- {value}" for value in values)
            if not values:
                lines.append("- None")
        return "\n".join(lines) + "\n"


__all__ = ["AgentExport", "AgentExporter", "SUPPORTED_FORMATS"]
