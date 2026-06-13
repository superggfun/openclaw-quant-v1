"""SQLite persistence for daily research scheduler runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from quant.storage.sqlite_connection import connect_sqlite


class SchedulerHistoryStore:
    """Persist scheduler run summaries without storing generated reports in git."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    def save(self, report: dict[str, Any]) -> None:
        summary = report.get("daily_research_summary") or {}
        generated_reports = report.get("generated_reports") or []
        warnings = report.get("warnings") or []
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO research_run_history (
                    run_id, timestamp, status, duration, warnings, factor_count,
                    regime, trade_sim_return, generated_reports
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report["run_id"],
                    report["start_time"],
                    report["status"],
                    report.get("duration_seconds"),
                    json.dumps(warnings, sort_keys=True),
                    len(summary.get("best_factors") or []),
                    summary.get("current_regime"),
                    summary.get("trade_sim_return"),
                    json.dumps(generated_reports, sort_keys=True),
                ),
            )

    def latest(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_run_history ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_run_history WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM research_run_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        latest = self.latest()
        history = self.history(100)
        counts: dict[str, int] = {}
        for row in history:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {
            "total_runs": len(history),
            "status_counts": counts,
            "latest_run": latest,
        }

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_run_history (
                    run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration REAL,
                    warnings TEXT,
                    factor_count INTEGER,
                    regime TEXT,
                    trade_sim_return REAL,
                    generated_reports TEXT
                )
                """
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("warnings", "generated_reports"):
            try:
                item[key] = json.loads(item.get(key) or "[]")
            except json.JSONDecodeError:
                item[key] = []
        return item
