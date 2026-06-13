"""Service layer for fundamental import, query, coverage, and quality reports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from quant.data.fundamental.fundamental_importer import FundamentalCSVImporter
from quant.data.fundamental.fundamental_models import normalize_statement
from quant.data.fundamental.fundamental_quality import FundamentalQualityAnalyzer
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.reports.report_io import generate_report_path, write_json_report


class FundamentalService:
    """Coordinate fundamental store, importer, quality, and report writing."""

    def __init__(self, store: FundamentalStore, report_dir: str | Path = "reports") -> None:
        self.store = store
        self.importer = FundamentalCSVImporter(store)
        self.quality_analyzer = FundamentalQualityAnalyzer(store)
        self.report_dir = Path(report_dir)

    def import_csv(self, path: str | Path, statement: str | None = None, force: bool = False) -> dict:
        payload = self.importer.import_file(path, statement=statement, force=force)
        report_path = self._write_report("fundamental_import", payload)
        payload["report_path"] = str(report_path)
        return payload

    def show(self, symbol: str, statement: str | None = None, latest: bool = False, limit: int = 10) -> list[dict]:
        normalized_statement = self._normalize_optional_statement(statement)
        if latest:
            return self.store.latest(symbol, normalized_statement)
        return self.store.query(symbol, normalized_statement, limit=limit)

    def coverage(self, symbols: list[str], parameters: dict | None = None, write_report: bool = True) -> dict:
        coverage = self.quality_analyzer.coverage(symbols)
        payload = self._base_report(
            "fundamental_coverage",
            parameters or {"symbols": symbols},
            summary={
                "readiness_score": coverage["readiness_score"],
                "total_symbols": coverage["total_symbols"],
                "symbols_with_any_fundamental_data": coverage["symbols_with_any_fundamental_data"],
                "symbols_missing_fundamental_data": coverage["symbols_missing_fundamental_data"],
            },
            coverage=coverage,
            quality_checks={},
            warnings=[],
        )
        if write_report:
            report_path = self._write_report("fundamental_coverage", payload)
            payload["report_path"] = str(report_path)
        else:
            payload["report_path"] = ""
        return payload

    def quality(self, symbols: list[str], parameters: dict | None = None) -> dict:
        quality = self.quality_analyzer.quality(symbols)
        warnings = [f"{item['code']}: {item.get('symbol') or 'ALL'} {item['message']}" for item in quality["warnings"]]
        payload = self._base_report(
            "fundamental_quality",
            parameters or {"symbols": symbols},
            summary=quality["summary"] | {"status": quality["status"]},
            coverage={},
            quality_checks=quality["quality_checks"],
            warnings=warnings,
        )
        report_path = self._write_report("fundamental_quality", payload)
        payload["report_path"] = str(report_path)
        return payload

    @staticmethod
    def _normalize_optional_statement(statement: str | None) -> str | None:
        if statement is None:
            return None
        normalized = normalize_statement(statement)
        if not normalized:
            raise ValueError(f"unsupported statement: {statement}")
        return normalized

    @staticmethod
    def _base_report(
        report_type: str,
        parameters: dict,
        summary: dict,
        coverage: dict,
        quality_checks,
        warnings: list[str],
    ) -> dict:
        return {
            "metadata": {"report_type": report_type, "created_at": datetime.now().isoformat(timespec="seconds")},
            "parameters": parameters,
            "summary": summary,
            "coverage": coverage,
            "quality_checks": quality_checks,
            "warnings": warnings,
            "no_lookahead_notes": ["Use report_date, not fiscal_period_end, when aligning fundamentals with historical signals."],
            "interpretation_notes": ["v0.25 stores, imports, queries, and validates fundamentals only. It does not create fundamental trading factors."],
        }

    def _write_report(self, prefix: str, payload: dict) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, prefix),
            payload,
            sort_keys=True,
        )
