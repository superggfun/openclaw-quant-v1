"""SQLite persistence for market regime history."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.regime_detection.market_regime import RegimeObservation


class RegimeHistoryStore:
    """Persist regime classifications and generated regime reports."""

    def __init__(self, db_path: str | Path, report_dir: str | Path = "reports") -> None:
        self.db_path = Path(db_path)
        self.report_dir = Path(report_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS regime_history (
                    date TEXT PRIMARY KEY,
                    regime TEXT NOT NULL,
                    volatility REAL,
                    trend_strength REAL,
                    drawdown REAL,
                    market_return REAL,
                    confidence REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_regime_history_regime
                ON regime_history (regime, date);
                """
            )

    def save(self, observations: list[RegimeObservation]) -> int:
        if not observations:
            return 0
        rows = [
            (
                obs.date,
                obs.regime,
                obs.volatility,
                obs.trend_strength,
                obs.drawdown,
                obs.market_return,
                obs.confidence,
            )
            for obs in observations
        ]
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO regime_history (
                    date, regime, volatility, trend_strength, drawdown, market_return, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    regime = excluded.regime,
                    volatility = excluded.volatility,
                    trend_strength = excluded.trend_strength,
                    drawdown = excluded.drawdown,
                    market_return = excluded.market_return,
                    confidence = excluded.confidence,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            return connection.total_changes - before

    def latest(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM regime_history ORDER BY date DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def history(self, limit: int = 30, regime: str | None = None) -> list[dict]:
        params: list[Any] = []
        where = ""
        if regime:
            where = "WHERE regime = ?"
            params.append(regime.upper())
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM regime_history {where} ORDER BY date DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def regime_for_date(self, date: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT regime FROM regime_history WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (date,),
            ).fetchone()
        return row["regime"] if row else None

    def counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT regime, COUNT(*) AS count FROM regime_history GROUP BY regime ORDER BY regime"
            ).fetchall()
        return {row["regime"]: row["count"] for row in rows}

    def write_report(self, report: dict, prefix: str) -> dict:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report | {"report_path": str(path)}

    @staticmethod
    def now() -> str:
        return datetime.now().isoformat(timespec="seconds")
