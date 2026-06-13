"""Report helpers for Strategy Evaluation Gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant.reports.report_io import generate_report_path, write_json_report


class StrategyGateReportStore:
    """Write and retrieve Strategy Gate reports."""

    def __init__(self, report_dir: str | Path = "reports") -> None:
        self.report_dir = Path(report_dir)

    def write(self, report: dict[str, Any]) -> dict[str, Any]:
        path = generate_report_path(self.report_dir, "strategy_gate")
        payload = report | {"report_path": str(path)}
        if "generated_reports" in payload and not payload["generated_reports"]:
            payload["generated_reports"] = [str(path)]
        write_json_report(path, payload, sort_keys=True)
        return payload

    def latest(self) -> dict[str, Any]:
        reports = sorted(self.report_dir.glob("strategy_gate_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not reports:
            return {
                "metadata": {"report_type": "strategy_gate"},
                "status": "NO_REPORTS",
                "warnings": ["NO_STRATEGY_GATE_REPORTS"],
                "report_path": None,
            }
        path = reports[0]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("report_path", str(path))
        return payload
