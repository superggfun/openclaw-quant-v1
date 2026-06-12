"""SQLite storage for fundamental statements and metrics."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.fundamental_data.fundamental_models import COMMON_FIELDS, STATEMENT_FIELDS


class FundamentalStore:
    """Persist fundamental data with report-date aware idempotent upserts."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            for table, fields in STATEMENT_FIELDS.items():
                columns = [
                    "id INTEGER PRIMARY KEY AUTOINCREMENT",
                    "symbol TEXT NOT NULL",
                    "fiscal_period_end TEXT NOT NULL",
                    "report_date TEXT",
                    "fiscal_year INTEGER",
                    "fiscal_quarter TEXT NOT NULL",
                    "currency TEXT",
                ]
                for field in fields:
                    if field in COMMON_FIELDS:
                        continue
                    columns.append(f"{field} REAL")
                columns.extend(
                    [
                        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
                        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
                        "UNIQUE(symbol, fiscal_period_end, fiscal_quarter)",
                    ]
                )
                connection.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns)})")
                connection.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_symbol_report_date ON {table} (symbol, report_date)"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fundamental_import_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    file_path TEXT,
                    statement TEXT,
                    force INTEGER NOT NULL DEFAULT 0,
                    inserted INTEGER NOT NULL,
                    updated INTEGER NOT NULL,
                    skipped INTEGER NOT NULL,
                    errors INTEGER NOT NULL,
                    warnings TEXT
                )
                """
            )

    def upsert(self, statement: str, row: dict[str, Any], force: bool = False) -> str:
        symbol = str(row["symbol"]).upper().strip()
        fiscal_period_end = str(row["fiscal_period_end"])
        fiscal_quarter = str(row["fiscal_quarter"]).upper().strip()
        report_date = row.get("report_date")

        existing = self.get_one(statement, symbol, fiscal_period_end, fiscal_quarter)
        if existing:
            existing_report_date = existing.get("report_date")
            if existing_report_date and report_date and str(report_date) < str(existing_report_date) and not force:
                return "skipped"
            self._update(statement, row, symbol, fiscal_period_end, fiscal_quarter)
            return "updated"
        self._insert(statement, row)
        return "inserted"

    def get_one(self, statement: str, symbol: str, fiscal_period_end: str, fiscal_quarter: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT *
                FROM {statement}
                WHERE symbol = ? AND fiscal_period_end = ? AND fiscal_quarter = ?
                """,
                (symbol.upper(), fiscal_period_end, fiscal_quarter.upper()),
            ).fetchone()
        return dict(row) if row else None

    def latest(self, symbol: str, statement: str | None = None) -> list[dict]:
        statements = [statement] if statement else list(STATEMENT_FIELDS)
        rows = []
        for table in statements:
            with self.connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT *, ? AS statement_type
                    FROM {table}
                    WHERE symbol = ?
                    ORDER BY report_date DESC, fiscal_period_end DESC
                    LIMIT 1
                    """,
                    (table, symbol.upper()),
                ).fetchone()
            if row:
                rows.append(dict(row))
        return rows

    def latest_as_of(self, symbol: str, statement: str, as_of_date: str) -> dict | None:
        """Return the newest row whose report_date was available on as_of_date."""

        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT *, ? AS statement_type
                FROM {statement}
                WHERE symbol = ?
                  AND report_date IS NOT NULL
                  AND report_date <= ?
                ORDER BY report_date DESC, fiscal_period_end DESC
                LIMIT 1
                """,
                (statement, symbol.upper(), as_of_date),
            ).fetchone()
        return dict(row) if row else None

    def query(self, symbol: str, statement: str | None = None, limit: int = 10) -> list[dict]:
        statements = [statement] if statement else list(STATEMENT_FIELDS)
        rows = []
        for table in statements:
            with self.connect() as connection:
                result = connection.execute(
                    f"""
                    SELECT *, ? AS statement_type
                    FROM {table}
                    WHERE symbol = ?
                    ORDER BY fiscal_period_end DESC, report_date DESC
                    LIMIT ?
                    """,
                    (table, symbol.upper(), limit),
                ).fetchall()
            rows.extend(dict(row) for row in result)
        return sorted(rows, key=lambda item: (item.get("fiscal_period_end") or "", item.get("statement_type") or ""), reverse=True)[:limit]

    def symbols_with_data(self) -> list[str]:
        symbols = set()
        with self.connect() as connection:
            for table in STATEMENT_FIELDS:
                rows = connection.execute(f"SELECT DISTINCT symbol FROM {table}").fetchall()
                symbols.update(row["symbol"] for row in rows)
        return sorted(symbols)

    def statement_counts(self, symbols: list[str] | None = None) -> dict[str, int]:
        counts = {}
        params: list[str] = []
        where = ""
        if symbols:
            placeholders = ", ".join("?" for _ in symbols)
            where = f"WHERE symbol IN ({placeholders})"
            params = [symbol.upper() for symbol in symbols]
        with self.connect() as connection:
            for table in STATEMENT_FIELDS:
                row = connection.execute(f"SELECT COUNT(*) AS count FROM {table} {where}", params).fetchone()
                counts[table] = int(row["count"])
        return counts

    def date_range(self, symbols: list[str] | None = None) -> dict[str, str | None]:
        params: list[str] = []
        where = ""
        if symbols:
            placeholders = ", ".join("?" for _ in symbols)
            where = f"WHERE symbol IN ({placeholders})"
            params = [symbol.upper() for symbol in symbols]
        oldest = []
        newest = []
        latest_report = []
        with self.connect() as connection:
            for table in STATEMENT_FIELDS:
                row = connection.execute(
                    f"""
                    SELECT MIN(fiscal_period_end) AS oldest,
                           MAX(fiscal_period_end) AS newest,
                           MAX(report_date) AS latest_report
                    FROM {table}
                    {where}
                    """,
                    params,
                ).fetchone()
                if row["oldest"]:
                    oldest.append(row["oldest"])
                if row["newest"]:
                    newest.append(row["newest"])
                if row["latest_report"]:
                    latest_report.append(row["latest_report"])
        return {
            "oldest_fiscal_period_end": min(oldest) if oldest else None,
            "newest_fiscal_period_end": max(newest) if newest else None,
            "latest_report_date": max(latest_report) if latest_report else None,
        }

    def missing_required_count(self, symbols: list[str] | None = None) -> int:
        total = 0
        params: list[str] = []
        where = ""
        if symbols:
            placeholders = ", ".join("?" for _ in symbols)
            where = f"WHERE symbol IN ({placeholders})"
            params = [symbol.upper() for symbol in symbols]
        with self.connect() as connection:
            for table in STATEMENT_FIELDS:
                row = connection.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM {table}
                    {where}
                    {"AND" if where else "WHERE"} (
                        fiscal_period_end IS NULL OR fiscal_period_end = ''
                        OR report_date IS NULL OR report_date = ''
                        OR fiscal_quarter IS NULL OR fiscal_quarter = ''
                        OR currency IS NULL OR currency = ''
                    )
                    """,
                    params,
                ).fetchone()
                total += int(row["count"])
        return total

    def rows(self, statement: str, symbols: list[str] | None = None) -> list[dict]:
        params: list[str] = []
        where = ""
        if symbols:
            placeholders = ", ".join("?" for _ in symbols)
            where = f"WHERE symbol IN ({placeholders})"
            params = [symbol.upper() for symbol in symbols]
        with self.connect() as connection:
            rows = connection.execute(f"SELECT *, ? AS statement_type FROM {statement} {where}", (statement, *params)).fetchall()
        return [dict(row) for row in rows]

    def duplicate_count(self, statement: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS duplicate_count
                FROM (
                    SELECT symbol, fiscal_period_end, fiscal_quarter, COUNT(*) AS row_count
                    FROM {statement}
                    GROUP BY symbol, fiscal_period_end, fiscal_quarter
                    HAVING row_count > 1
                )
                """
            ).fetchone()
        return int(row["duplicate_count"] if row else 0)

    def log_import(self, file_path: str, statement: str | None, force: bool, summary: dict, warnings: list[str]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO fundamental_import_log (
                    file_path, statement, force, inserted, updated, skipped, errors, warnings
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_path,
                    statement,
                    int(force),
                    summary["inserted"],
                    summary["updated"],
                    summary["skipped"],
                    summary["errors"],
                    json.dumps(warnings, sort_keys=True),
                ),
            )

    def _insert(self, statement: str, row: dict[str, Any]) -> None:
        fields = STATEMENT_FIELDS[statement]
        payload = {field: row.get(field) for field in fields}
        payload["symbol"] = str(payload["symbol"]).upper().strip()
        payload["fiscal_quarter"] = str(payload["fiscal_quarter"]).upper().strip()
        columns = ", ".join(payload)
        placeholders = ", ".join("?" for _ in payload)
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO {statement} ({columns}) VALUES ({placeholders})",
                list(payload.values()),
            )

    def _update(self, statement: str, row: dict[str, Any], symbol: str, fiscal_period_end: str, fiscal_quarter: str) -> None:
        fields = STATEMENT_FIELDS[statement]
        payload = {field: row.get(field) for field in fields}
        payload["symbol"] = str(payload["symbol"]).upper().strip()
        payload["fiscal_quarter"] = str(payload["fiscal_quarter"]).upper().strip()
        assignments = ", ".join(f"{field} = ?" for field in payload)
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE {statement}
                SET {assignments}, updated_at = ?
                WHERE symbol = ? AND fiscal_period_end = ? AND fiscal_quarter = ?
                """,
                [*payload.values(), datetime.now().isoformat(timespec="seconds"), symbol, fiscal_period_end, fiscal_quarter],
            )
