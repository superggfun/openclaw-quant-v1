"""Coverage and quality checks for fundamental data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from quant.core.symbols import normalize_symbols
from quant.data.fundamental.fundamental_models import STATEMENT_FIELDS
from quant.data.fundamental.fundamental_store import FundamentalStore


class FundamentalQualityAnalyzer:
    """Compute fundamental coverage and deterministic quality warnings."""

    def __init__(self, store: FundamentalStore) -> None:
        self.store = store

    def coverage(self, symbols: list[str]) -> dict:
        normalized = self._normalize_symbols(symbols)
        covered = set(self.store.symbols_with_data())
        statement_counts = self.store.statement_counts(normalized)
        date_range = self.store.date_range(normalized)
        rows = []
        for symbol in normalized:
            symbol_statements = {
                statement: bool(self.store.rows(statement, [symbol]))
                for statement in STATEMENT_FIELDS
            }
            rows.append(
                {
                    "symbol": symbol,
                    "has_fundamental_data": any(symbol_statements.values()),
                    "statements": symbol_statements,
                }
            )
        symbols_with = [row["symbol"] for row in rows if row["has_fundamental_data"]]
        missing = [row["symbol"] for row in rows if not row["has_fundamental_data"]]
        required_missing = self.store.missing_required_count(normalized)
        score = self._readiness_score(len(normalized), len(symbols_with), statement_counts, required_missing)
        return {
            "total_symbols": len(normalized),
            "symbols_with_any_fundamental_data": len(symbols_with),
            "symbols_missing_fundamental_data": len(missing),
            "covered_symbols": symbols_with,
            "missing_symbols": missing,
            "statement_coverage": statement_counts,
            "oldest_fiscal_period_end": date_range["oldest_fiscal_period_end"],
            "newest_fiscal_period_end": date_range["newest_fiscal_period_end"],
            "latest_report_date": date_range["latest_report_date"],
            "missing_required_fields_count": required_missing,
            "readiness_score": score,
            "symbols": rows,
        }

    def quality(self, symbols: list[str]) -> dict:
        normalized = self._normalize_symbols(symbols)
        checks: list[dict[str, Any]] = []
        for statement in STATEMENT_FIELDS:
            duplicate_count = self.store.duplicate_count(statement)
            if duplicate_count:
                checks.append(self._warning("DUPLICATE_ROWS", statement, None, f"{duplicate_count} duplicate keys"))
            rows = self.store.rows(statement, normalized)
            for row in rows:
                checks.extend(self._row_checks(statement, row))
            checks.extend(self._sequence_checks(statement, rows))
        warnings = [check for check in checks if check["status"] == "WARNING"]
        status = "PASS" if not warnings else "WARNING"
        return {
            "status": status,
            "symbols": normalized,
            "summary": {
                "checks": len(checks),
                "warnings": len(warnings),
                "symbols_checked": len(normalized),
            },
            "quality_checks": checks,
            "warnings": warnings,
        }

    def _row_checks(self, statement: str, row: dict) -> list[dict]:
        checks = []
        symbol = row.get("symbol")
        if not row.get("fiscal_period_end"):
            checks.append(self._warning("MISSING_FISCAL_PERIOD_END", statement, symbol, "missing fiscal_period_end"))
        if not row.get("report_date"):
            checks.append(self._warning("MISSING_REPORT_DATE", statement, symbol, "missing report_date"))
        if row.get("report_date") and row.get("fiscal_period_end") and row["report_date"] < row["fiscal_period_end"]:
            checks.append(self._warning("REPORT_DATE_BEFORE_FISCAL_PERIOD_END", statement, symbol, "report_date precedes fiscal_period_end"))
        if statement == "income_statement":
            if self._num(row.get("revenue")) is not None and self._num(row.get("revenue")) < 0:
                checks.append(self._warning("NEGATIVE_REVENUE", statement, symbol, "negative revenue"))
            if row.get("shares_outstanding_basic") is None and row.get("shares_outstanding_diluted") is None:
                checks.append(self._warning("MISSING_SHARES_OUTSTANDING", statement, symbol, "missing shares outstanding"))
        if statement == "balance_sheet":
            if self._num(row.get("total_assets")) is not None and self._num(row.get("total_assets")) < 0:
                checks.append(self._warning("NEGATIVE_TOTAL_ASSETS", statement, symbol, "negative total_assets"))
            if self._num(row.get("total_equity")) is not None and self._num(row.get("total_equity")) <= 0:
                checks.append(self._warning("ZERO_OR_NEGATIVE_TOTAL_EQUITY", statement, symbol, "zero or negative total_equity"))
        if statement == "fundamental_metrics":
            for field in ("pe_ratio", "pb_ratio", "ps_ratio", "ev_to_ebitda"):
                value = self._num(row.get(field))
                if value is not None and abs(value) > 500:
                    checks.append(self._warning("EXTREME_RATIO", statement, symbol, f"{field}={value}"))
        if row.get("currency") and row.get("currency") != "USD":
            checks.append(self._warning("CURRENCY_MISMATCH", statement, symbol, f"currency={row.get('currency')}"))
        if row.get("report_date"):
            days = (date.today() - datetime.strptime(row["report_date"], "%Y-%m-%d").date()).days
            if days > 550:
                checks.append(self._warning("STALE_REPORT", statement, symbol, f"report is {days} days old"))
        return checks

    def _sequence_checks(self, statement: str, rows: list[dict]) -> list[dict]:
        checks = []
        by_symbol: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
        for row in rows:
            quarter = str(row.get("fiscal_quarter") or "").upper()
            if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
                continue
            try:
                fiscal_year = int(row.get("fiscal_year"))
                quarter_number = int(quarter[1])
            except (TypeError, ValueError):
                continue
            sequence = fiscal_year * 4 + quarter_number
            label = f"{fiscal_year} {quarter}"
            by_symbol[str(row.get("symbol") or "")].append((sequence, quarter_number, label))

        for symbol, periods in sorted(by_symbol.items()):
            unique_periods = sorted({period[0]: period for period in periods}.values())
            for previous, current in zip(unique_periods, unique_periods[1:]):
                if current[0] - previous[0] > 1:
                    checks.append(
                        self._warning(
                            "MISSING_SEQUENTIAL_QUARTERS",
                            statement,
                            symbol,
                            f"missing quarterly records between {previous[2]} and {current[2]}",
                        )
                    )
        return checks

    @staticmethod
    def _readiness_score(total_symbols: int, covered_symbols: int, statement_counts: dict[str, int], missing_required: int) -> int:
        if total_symbols <= 0:
            return 0
        coverage_score = int((covered_symbols / total_symbols) * 50)
        statement_score = sum(10 for value in statement_counts.values() if value > 0)
        penalty = min(20, missing_required * 2)
        return max(0, min(100, coverage_score + statement_score - penalty))

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)

    @staticmethod
    def _warning(code: str, statement: str, symbol: str | None, message: str) -> dict:
        return {"status": "WARNING", "code": code, "statement": statement, "symbol": symbol, "message": message}

    @staticmethod
    def _num(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
