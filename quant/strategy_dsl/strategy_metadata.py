"""SQLite metadata store for strategy definitions and runs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.storage.sqlite_connection import connect_sqlite
from quant.strategy_dsl.strategy_definition import StrategyDefinition


class StrategyMetadataStore:
    """Persist strategy registry rows, versions, and run summaries."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS strategy_registry (
                    strategy_name TEXT PRIMARY KEY,
                    description TEXT,
                    latest_version TEXT,
                    tags TEXT,
                    source_path TEXT,
                    created_at TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS strategy_versions (
                    strategy_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    factor_set TEXT,
                    validation_result TEXT,
                    source_path TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (strategy_name, version)
                );

                CREATE TABLE IF NOT EXISTS strategy_runs (
                    run_id TEXT PRIMARY KEY,
                    strategy_name TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    validation_result TEXT,
                    report_path TEXT,
                    trade_sim_report_path TEXT,
                    final_equity REAL,
                    total_return REAL,
                    warnings TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_strategy(
        self,
        definition: StrategyDefinition,
        validation: dict[str, Any],
        source_path: str = "",
    ) -> None:
        payload = definition.to_dict()
        factor_set = [factor.get("name") for factor in definition.factors]
        now = self._now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_registry (
                    strategy_name, description, latest_version, tags, source_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_name) DO UPDATE SET
                    description = excluded.description,
                    latest_version = excluded.latest_version,
                    tags = excluded.tags,
                    source_path = excluded.source_path,
                    updated_at = excluded.updated_at
                """,
                (
                    definition.name,
                    definition.description,
                    definition.version,
                    json.dumps(definition.tags, sort_keys=True),
                    source_path,
                    definition.created_at or now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO strategy_versions (
                    strategy_name, version, definition_json, factor_set, validation_result, source_path
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_name, version) DO UPDATE SET
                    definition_json = excluded.definition_json,
                    factor_set = excluded.factor_set,
                    validation_result = excluded.validation_result,
                    source_path = excluded.source_path
                """,
                (
                    definition.name,
                    definition.version,
                    json.dumps(payload, sort_keys=True),
                    json.dumps(factor_set, sort_keys=True),
                    json.dumps(validation, sort_keys=True),
                    source_path,
                ),
            )

    def save_run(self, report: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_runs (
                    run_id, strategy_name, strategy_version, status, validation_result,
                    report_path, trade_sim_report_path, final_equity, total_return, warnings, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.get("run_id"),
                    report.get("strategy_name"),
                    report.get("strategy_version"),
                    report.get("status"),
                    json.dumps(report.get("validation") or {}, sort_keys=True),
                    report.get("report_path"),
                    (report.get("artifacts") or {}).get("trade_sim_report_path"),
                    (report.get("trade_sim_summary") or {}).get("final_equity"),
                    (report.get("trade_sim_summary") or {}).get("total_return"),
                    json.dumps(report.get("warnings") or [], sort_keys=True),
                    report.get("generated_at") or self._now(),
                ),
            )

    def list_registry(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM strategy_registry ORDER BY strategy_name"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")
