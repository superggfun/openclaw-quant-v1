"""Low-level SQL helpers extracted from FactorStore."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.reports.report_io import generate_report_path, write_json_report


def fetch_all(connection: sqlite3.Connection, query: str, params: list[Any]) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def table_counts(connection: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, int]:
    """Return row counts for each named table."""
    query = "\nUNION ALL\n".join(
        f"SELECT '{table}' AS table_name, COUNT(*) AS count FROM {table}"
        for table in tables
    )
    return {
        row["table_name"]: int(row["count"])
        for row in connection.execute(query).fetchall()
    }


def ensure_column(connection: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    """Add a column to a table if it does not already exist."""
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def save_factor_values(
    connection: sqlite3.Connection,
    factor: str,
    observations: list,
    coverage: float | None,
    version: str,
) -> int:
    """Insert or update factor value rows and return the number of changed rows."""
    rows = [
        (
            factor,
            observation.symbol,
            observation.signal_date,
            observation.factor_value,
            coverage,
            version,
        )
        for observation in observations
    ]
    if not rows:
        return 0
    before = connection.total_changes
    connection.executemany(
        """
        INSERT INTO factor_values (factor_name, symbol, signal_date, value, coverage, version)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(factor_name, symbol, signal_date, version) DO UPDATE SET
            value = excluded.value,
            coverage = excluded.coverage
        """,
        rows,
    )
    return connection.total_changes - before


def upsert_factor_definition_connection(
    connection: sqlite3.Connection,
    factor_name: str,
    category: str,
    description: str,
    higher_is_better: bool,
    fundamental_required: bool,
) -> None:
    """Upsert a factor definition row on an open connection."""
    connection.execute(
        """
        INSERT INTO factor_definitions (
            factor_name, category, description, higher_is_better, fundamental_required
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(factor_name) DO UPDATE SET
            category = excluded.category,
            description = excluded.description,
            higher_is_better = excluded.higher_is_better,
            fundamental_required = excluded.fundamental_required,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            factor_name,
            category,
            description,
            int(bool(higher_is_better)),
            int(bool(fundamental_required)),
        ),
    )


def upsert_factor_version_connection(
    connection: sqlite3.Connection,
    factor_name: str,
    version: str,
    description: str,
    change_reason: str,
) -> None:
    """Upsert a factor version row on an open connection."""
    connection.execute(
        """
        INSERT INTO factor_versions (factor_name, version, description, change_reason)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(factor_name, version) DO UPDATE SET
            description = excluded.description,
            change_reason = excluded.change_reason
        """,
        (factor_name, version, description, change_reason),
    )


def with_report_path(report_dir: Path, report: dict, prefix: str, write_report: bool) -> dict:
    """Optionally write a JSON report and attach its path to the returned dict."""
    if not write_report:
        return report | {"report_path": ""}
    path = generate_report_path(report_dir, prefix, unique=True)
    write_json_report(path, report, sort_keys=True)
    return report | {"report_path": str(path)}


def coverage_pct(coverage: dict | None) -> float | None:
    """Extract coverage_percentage from a coverage dict."""
    if not coverage:
        return None
    return coverage.get("coverage_percentage")


def missing_pct(coverage: dict | None) -> float | None:
    """Extract missing_percentage from a coverage dict."""
    if not coverage:
        return None
    return coverage.get("missing_percentage")


def now_iso() -> str:
    """Return the current UTC-ish datetime as an ISO-8601 string (second precision)."""
    return datetime.now().isoformat(timespec="seconds")
