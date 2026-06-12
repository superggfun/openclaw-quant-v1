"""Report helpers for Strategy Evaluation Gates."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class StrategyGateReportStore:
    """Write and retrieve Strategy Gate reports."""

    def __init__(self, report_dir: str | Path = "reports") -> None:
        self.report_dir = Path(report_dir)

    def write(self, report: dict[str, Any]) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"strategy_gate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        payload = report | {"report_path": str(path)}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
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
