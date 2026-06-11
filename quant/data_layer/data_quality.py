"""Data quality, coverage, and research readiness diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from quant.config import DEFAULT_START_DATE
from quant.data_source.yfinance_client import YFinanceClient
from quant.data_layer.symbol_metadata import SymbolMetadataStore
from quant.storage.sqlite_store import SQLitePriceStore


@dataclass(frozen=True)
class DataQualityReport:
    symbols: list[str]
    status: str
    diagnostics: dict[str, dict]
    summary: dict
    report_path: str


@dataclass(frozen=True)
class DataRefreshReport:
    symbols: list[str]
    summary: dict
    per_symbol: dict[str, dict]
    report_path: str


class DataRefreshManager:
    """Refresh stored daily prices with explicit inserted/updated/skipped counts."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        data_source: YFinanceClient | None = None,
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.data_source = data_source or YFinanceClient()
        self.report_dir = Path(report_dir)

    def refresh(
        self,
        symbols: list[str],
        start_date: str | date | None = None,
        end_date: str | date | None = None,
    ) -> DataRefreshReport:
        normalized = DataQualityAnalyzer._normalize_symbols(symbols)
        per_symbol: dict[str, dict] = {}

        for symbol in normalized:
            existing = self.price_store.get_price_history(symbol)
            existing_dates = set(existing["date"].astype(str)) if not existing.empty else set()
            latest = self.price_store.latest_date(symbol)
            fetch_start = start_date or self._next_day(latest) or DEFAULT_START_DATE
            skipped = self._skipped_existing_count(existing, fetch_start)

            if self._should_skip_fetch(fetch_start, latest, end_date, start_date):
                per_symbol[symbol] = {
                    "status": "PASS",
                    "inserted": 0,
                    "updated": 0,
                    "skipped": len(existing_dates),
                    "fetched": 0,
                    "fetch_start": str(fetch_start),
                    "end_date": str(end_date) if end_date else None,
                    "error": None,
                    "reason": "up_to_date",
                }
                continue

            try:
                prices = self.data_source.fetch_daily_prices(symbol, start=fetch_start, end=end_date)
            except Exception as exc:  # yfinance/network errors should not abort the whole refresh.
                per_symbol[symbol] = {
                    "status": "ERROR",
                    "inserted": 0,
                    "updated": 0,
                    "skipped": skipped,
                    "fetched": 0,
                    "fetch_start": str(fetch_start),
                    "end_date": str(end_date) if end_date else None,
                    "error": str(exc),
                    "reason": "api_error",
                }
                continue

            fetched_dates = set(prices["date"].astype(str)) if not prices.empty else set()
            inserted = len(fetched_dates - existing_dates)
            updated = len(fetched_dates & existing_dates)
            self.price_store.upsert_prices(prices)
            per_symbol[symbol] = {
                "status": "PASS",
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "fetched": len(fetched_dates),
                "fetch_start": str(fetch_start),
                "end_date": str(end_date) if end_date else None,
                "error": None,
                "reason": "refreshed",
            }

        summary = {
            "total_symbols": len(normalized),
            "inserted": sum(item["inserted"] for item in per_symbol.values()),
            "updated": sum(item["updated"] for item in per_symbol.values()),
            "skipped": sum(item["skipped"] for item in per_symbol.values()),
            "errors": sum(1 for item in per_symbol.values() if item["status"] == "ERROR"),
        }
        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "symbols": normalized,
            "summary": summary,
            "per_symbol": per_symbol,
        }
        path = self._write_report("data_refresh", payload)
        return DataRefreshReport(normalized, summary, per_symbol, str(path))

    @staticmethod
    def _next_day(latest: str | None) -> str | None:
        if not latest:
            return None
        return (datetime.strptime(latest, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()

    @staticmethod
    def _skipped_existing_count(existing: pd.DataFrame, fetch_start: str | date) -> int:
        if existing.empty:
            return 0
        dates = existing["date"].astype(str)
        return int((dates < str(fetch_start)).sum())

    @staticmethod
    def _should_skip_fetch(
        fetch_start: str | date,
        latest: str | None,
        end_date: str | date | None,
        requested_start: str | date | None,
    ) -> bool:
        if requested_start:
            return bool(end_date and str(fetch_start) >= str(end_date))
        if end_date:
            return str(fetch_start) >= str(end_date)
        if not latest:
            return False
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        return latest_date >= date.today() - timedelta(days=1)

    def _write_report(self, prefix: str, payload: dict) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path


class DataQualityAnalyzer:
    """Inspect stored daily prices for research readiness."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        metadata_store: SymbolMetadataStore,
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.metadata_store = metadata_store
        self.report_dir = Path(report_dir)

    def analyze(self, symbols: list[str]) -> DataQualityReport:
        normalized = self._normalize_symbols(symbols)
        diagnostics = {symbol: self._diagnose_symbol(symbol) for symbol in normalized}
        status = self._overall_status(diagnostics)
        summary = {
            "total_symbols": len(normalized),
            "pass": sum(1 for item in diagnostics.values() if item["status"] == "PASS"),
            "warning": sum(1 for item in diagnostics.values() if item["status"] == "WARNING"),
            "fail": sum(1 for item in diagnostics.values() if item["status"] == "FAIL"),
        }
        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "symbols": normalized,
            "status": status,
            "summary": summary,
            "diagnostics": diagnostics,
        }
        path = self._write_report("data_quality", payload)
        return DataQualityReport(normalized, status, diagnostics, summary, str(path))

    def coverage(self, symbols: list[str]) -> dict:
        normalized = self._normalize_symbols(symbols)
        rows = []
        for symbol in normalized:
            history = self.price_store.get_price_history(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "has_price_data": not history.empty,
                    "history_length": int(len(history)),
                    "oldest_date": None if history.empty else str(history["date"].min()),
                    "newest_date": None if history.empty else str(history["date"].max()),
                    "metadata_available": self.metadata_store.get(symbol) is not None,
                }
            )
        with_data = [row for row in rows if row["has_price_data"]]
        lengths = [row["history_length"] for row in rows]
        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "total_symbols": len(rows),
            "symbols_with_price_data": len(with_data),
            "symbols_without_price_data": len(rows) - len(with_data),
            "average_history_length": round(float(sum(lengths) / len(lengths)), 2) if lengths else 0.0,
            "oldest_date": min((row["oldest_date"] for row in with_data if row["oldest_date"]), default=None),
            "newest_date": max((row["newest_date"] for row in with_data if row["newest_date"]), default=None),
            "symbols": rows,
        }
        path = self._write_report("data_coverage", payload)
        payload["report_path"] = str(path)
        return payload

    def readiness(self, symbols: list[str]) -> dict:
        coverage = self.coverage(symbols)
        quality = self.analyze(symbols)
        metadata_rows = [self.metadata_store.get(symbol) for symbol in symbols]
        sectors = sorted({row["sector"] for row in metadata_rows if row})
        factor_ready = [
            row for row in coverage["symbols"]
            if row["has_price_data"] and row["history_length"] >= 61
        ]
        score = 0
        recommendations: list[str] = []

        universe_size = len(symbols)
        if universe_size >= 20:
            score += 20
        else:
            score += max(0, universe_size)
            recommendations.append("Need more symbols")

        coverage_ratio = coverage["symbols_with_price_data"] / max(coverage["total_symbols"], 1)
        score += int(coverage_ratio * 25)
        if coverage_ratio < 0.8:
            recommendations.append("Need broader price coverage")

        avg_history = coverage["average_history_length"]
        score += 20 if avg_history >= 252 else int(min(avg_history / 252, 1.0) * 20)
        if avg_history < 252:
            recommendations.append("Need longer history")

        score += 15 if len(sectors) >= 5 else len(sectors) * 3
        if len(sectors) < 5:
            recommendations.append("Need sector diversity")

        factor_ratio = len(factor_ready) / max(coverage["total_symbols"], 1)
        score += int(factor_ratio * 20)
        if factor_ratio < 0.8:
            recommendations.append("Need factor coverage")

        if quality.status != "PASS":
            recommendations.append("Review data quality warnings")

        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "readiness_score": min(100, max(0, score)),
            "universe_size": universe_size,
            "history_depth_average": avg_history,
            "sector_count": len(sectors),
            "sectors": sectors,
            "factor_coverage_symbols": len(factor_ready),
            "data_quality_status": quality.status,
            "coverage_report_path": coverage["report_path"],
            "data_quality_report_path": quality.report_path,
            "recommendations": sorted(set(recommendations)),
        }
        path = self._write_report("research_readiness", payload)
        payload["report_path"] = str(path)
        return payload

    def _diagnose_symbol(self, symbol: str) -> dict:
        history = self.price_store.get_price_history(symbol)
        checks: dict[str, dict] = {}
        if history.empty:
            return {
                "status": "FAIL",
                "checks": {
                    "missing_ratio": {"status": "FAIL", "value": 1.0, "explanation": "no price rows"},
                    "short_history": {"status": "FAIL", "value": 0, "explanation": "no history"},
                },
            }

        history = history.sort_values("date")
        duplicate_rows = self._duplicate_rows(symbol)
        dates = pd.to_datetime(history["date"])
        business_days = pd.date_range(dates.min(), dates.max(), freq="B")
        observed = set(dates.dt.normalize())
        missing = [date for date in business_days if date.normalize() not in observed]
        missing_ratio = len(missing) / max(len(business_days), 1)
        zero_volume_days = int((pd.to_numeric(history["volume"], errors="coerce").fillna(0) == 0).sum())
        price_columns = ["open", "high", "low", "close", "adj_close"]
        prices = history[price_columns].apply(pd.to_numeric, errors="coerce")
        zero_negative_prices = int((prices <= 0).any(axis=1).sum())
        missing_adj_close = int(pd.to_numeric(history["adj_close"], errors="coerce").isna().sum())
        closes = pd.to_numeric(history["close"], errors="coerce")
        returns = closes.pct_change().dropna()
        outliers = int((returns.abs() > 0.25).sum())
        gaps = int((dates.diff().dt.days.fillna(1) > 5).sum())
        stale_days = (date.today() - dates.max().date()).days

        checks["missing_ratio"] = self._check("missing_ratio", missing_ratio, 0.05, 0.20)
        checks["duplicate_rows"] = self._check_count("duplicate_rows", duplicate_rows, 0, 0)
        checks["price_outliers"] = self._check_count("price_outliers", outliers, 0, 3)
        checks["zero_negative_prices"] = self._check_count("zero_negative_prices", zero_negative_prices, 0, 0)
        checks["zero_volume_days"] = self._check_count("zero_volume_days", zero_volume_days, 0, 5)
        checks["short_history"] = self._check_inverse_count("short_history", len(history), 60, 20)
        checks["data_gaps"] = self._check_count("data_gaps", gaps, 0, 3)
        checks["stale_data"] = self._check_count("stale_data_days", stale_days, 10, 45)
        checks["adjusted_close_availability"] = self._check_count("missing_adjusted_close", missing_adj_close, 0, 0)

        status = self._worst_status([item["status"] for item in checks.values()])
        return {"status": status, "checks": checks}

    def _duplicate_rows(self, symbol: str) -> int:
        with self.price_store.connect() as connection:
            rows = connection.execute(
                """
                SELECT COUNT(*) AS duplicate_count
                FROM (
                    SELECT symbol, date, COUNT(*) AS row_count
                    FROM prices
                    WHERE symbol = ?
                    GROUP BY symbol, date
                    HAVING row_count > 1
                )
                """,
                (symbol.upper(),),
            ).fetchone()
        return int(rows["duplicate_count"] if rows else 0)

    @staticmethod
    def _check(name: str, value: float, warning_threshold: float, fail_threshold: float) -> dict:
        if value >= fail_threshold:
            status = "FAIL"
        elif value > warning_threshold:
            status = "WARNING"
        else:
            status = "PASS"
        return {"status": status, "value": round(float(value), 6), "explanation": name}

    @staticmethod
    def _check_count(name: str, value: int, warning_threshold: int, fail_threshold: int) -> dict:
        if value > fail_threshold:
            status = "FAIL"
        elif value > warning_threshold:
            status = "WARNING"
        else:
            status = "PASS"
        return {"status": status, "value": int(value), "explanation": name}

    @staticmethod
    def _check_inverse_count(name: str, value: int, pass_threshold: int, fail_threshold: int) -> dict:
        if value < fail_threshold:
            status = "FAIL"
        elif value < pass_threshold:
            status = "WARNING"
        else:
            status = "PASS"
        return {"status": status, "value": int(value), "explanation": name}

    @staticmethod
    def _worst_status(statuses: list[str]) -> str:
        if "FAIL" in statuses:
            return "FAIL"
        if "WARNING" in statuses:
            return "WARNING"
        return "PASS"

    def _overall_status(self, diagnostics: dict[str, dict]) -> str:
        return self._worst_status([item["status"] for item in diagnostics.values()])

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for symbol in symbols:
            ticker = symbol.upper().strip()
            if ticker and ticker not in seen:
                normalized.append(ticker)
                seen.add(ticker)
        return normalized

    def _write_report(self, prefix: str, payload: dict) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path
