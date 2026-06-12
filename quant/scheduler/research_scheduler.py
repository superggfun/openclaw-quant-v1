"""Facade for running and querying daily research scheduler state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant.scheduler.daily_research_run import DailyResearchRun
from quant.scheduler.scheduler_config import SchedulerConfig
from quant.scheduler.scheduler_history import SchedulerHistoryStore


class ResearchScheduler:
    """Run daily research workflows and persist their history."""

    def __init__(self, context, db_path: str | Path, report_dir: str | Path = "reports") -> None:
        self.context = context
        self.report_dir = Path(report_dir)
        self.history_store = SchedulerHistoryStore(db_path)
        self.runner = DailyResearchRun(context, report_dir=report_dir)

    def run(self, config_path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        source_path = str(config_path) if config_path else None
        config_source = "config_file" if config_path and Path(config_path).exists() else "defaults"
        config = SchedulerConfig.from_file(config_path)
        if overrides:
            config = SchedulerConfig.from_mapping(config.to_dict() | overrides)
            config_source = "config_file_with_cli_overrides" if config_source == "config_file" else "defaults_with_cli_overrides"
        report = self.runner.run(config, config_source=config_source, config_path=source_path)
        self.history_store.save(report)
        return report

    def status(self) -> dict[str, Any]:
        latest = self.history_store.latest()
        return {
            "metadata": {"report_type": "research_status"},
            "latest_run": latest,
            "status": latest.get("status") if latest else "NO_RUNS",
        }

    def history(self, limit: int = 20) -> dict[str, Any]:
        rows = self.history_store.history(limit)
        return {
            "metadata": {"report_type": "research_history"},
            "limit": limit,
            "runs": rows,
            "summary": self.history_store.summary(),
        }

    def latest_report(self, run_id: str | None = None) -> dict[str, Any]:
        row = self.history_store.get(run_id) if run_id else self.history_store.latest()
        if not row:
            return {"metadata": {"report_type": "research_run"}, "status": "NO_RUNS"}
        paths = row.get("generated_reports") or []
        research_reports = [path for path in paths if Path(path).name.startswith("research_run_")]
        if research_reports:
            path = Path(research_reports[-1])
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return {
            "metadata": {"report_type": "research_run"},
            "status": row.get("status"),
            "run_id": row.get("run_id"),
            "warnings": row.get("warnings") or [],
        }
