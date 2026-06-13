"""Report MCP runner methods."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReportMCPRunner:
    def export_for_agent(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        report = arguments["report"]
        output_format = arguments.get("format", "json")
        rendered = context.agent_exporter.export_file(report, output_format=output_format, max_tokens=int(arguments.get("max_tokens", 800)))
        if output_format == "json":
            return json.loads(rendered)
        return {"summary": rendered, "report_path": str(report)}

    def get_latest_reports(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        limit = int(arguments.get("limit", 10))
        report_type = arguments.get("report_type")
        pattern = f"{report_type}_*.json" if report_type else "*.json"
        reports = sorted(Path("reports").glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]
        return {"reports": [str(path) for path in reports], "count": len(reports)}

    def get_report_summary(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        rendered = context.agent_exporter.export_file(arguments["report"], output_format="json", max_tokens=int(arguments.get("max_tokens", 800)))
        return json.loads(rendered)
