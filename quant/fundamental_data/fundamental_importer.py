"""CSV importer for fundamental statements and metrics."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from quant.fundamental_data.fundamental_models import (
    COMMON_FIELDS,
    DATE_FIELDS,
    NUMERIC_FIELDS,
    STATEMENT_FIELDS,
    normalize_statement,
)
from quant.fundamental_data.fundamental_store import FundamentalStore


class FundamentalCSVImporter:
    """Import wide or statement-specific CSV files into fundamental tables."""

    def __init__(self, store: FundamentalStore) -> None:
        self.store = store

    def import_file(self, path: str | Path, statement: str | None = None, force: bool = False) -> dict:
        csv_path = Path(path)
        if not csv_path.exists():
            raise ValueError(f"fundamental CSV file not found: {csv_path}")
        fixed_statement = normalize_statement(statement)
        if statement and not fixed_statement:
            raise ValueError(f"unsupported statement: {statement}")
        try:
            frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        except Exception as exc:
            raise ValueError(f"fundamental CSV is malformed: {csv_path}") from exc
        if frame.empty:
            raise ValueError("fundamental CSV must contain at least one row")
        frame.columns = [self._normalize_column(column) for column in frame.columns]
        self._validate_columns(frame, fixed_statement)

        summary = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        warnings: list[str] = []

        for index, record in enumerate(frame.to_dict("records"), start=1):
            statement_type = fixed_statement or normalize_statement(record.get("statement_type"))
            if not statement_type:
                raise ValueError(f"row {index} has unsupported or missing statement_type")
            try:
                row = self._normalize_row(record, statement_type)
            except ValueError as exc:
                raise ValueError(f"row {index}: {exc}") from exc
            status = self.store.upsert(statement_type, row, force=force)
            summary[status] += 1

        self.store.log_import(str(csv_path), fixed_statement, force, summary, warnings)
        return {
            "metadata": {"report_type": "fundamental_import", "created_at": datetime.now().isoformat(timespec="seconds")},
            "parameters": {"file": str(csv_path), "statement": fixed_statement, "force": force},
            "summary": summary,
            "coverage": {},
            "quality_checks": {},
            "warnings": warnings,
            "no_lookahead_notes": ["Fundamental data stores report_date separately from fiscal_period_end; callers must use report_date for no-lookahead filtering."],
            "interpretation_notes": ["CSV import only; no fundamental factors or trading signals are generated in v0.25."],
        }

    @staticmethod
    def _normalize_column(column: str) -> str:
        return column.strip().lower().replace(" ", "_").replace("-", "_")

    @staticmethod
    def _validate_columns(frame: pd.DataFrame, fixed_statement: str | None) -> None:
        required = set(COMMON_FIELDS)
        if fixed_statement:
            required.update(COMMON_FIELDS)
        else:
            required.add("statement_type")
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"fundamental CSV missing required columns: {', '.join(missing)}")

    def _normalize_row(self, record: dict[str, Any], statement: str) -> dict:
        fields = STATEMENT_FIELDS[statement]
        output: dict[str, Any] = {}
        for field in fields:
            raw = record.get(field, "")
            if field == "symbol":
                value = str(raw).upper().strip()
                if not value:
                    raise ValueError("symbol is required")
                output[field] = value
            elif field in DATE_FIELDS:
                value = self._parse_date(raw)
                if not value:
                    raise ValueError(f"{field} is required")
                output[field] = value
            elif field == "fiscal_quarter":
                value = str(raw).upper().strip()
                if not value:
                    raise ValueError("fiscal_quarter is required")
                output[field] = value
            elif field == "currency":
                output[field] = str(raw).upper().strip() or None
            elif field in NUMERIC_FIELDS:
                output[field] = self._parse_number(raw)
            else:
                output[field] = raw
        return output

    @staticmethod
    def _parse_date(value: Any) -> str | None:
        text = str(value).strip()
        if not text:
            return None
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            raise ValueError(f"invalid date: {text}")
        return parsed.strftime("%Y-%m-%d")

    @staticmethod
    def _parse_number(value: Any) -> float | int | None:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"invalid numeric value: {value}") from exc
        if not math.isfinite(number):
            raise ValueError(f"invalid numeric value: {value}")
        if number.is_integer():
            return int(number)
        return number
