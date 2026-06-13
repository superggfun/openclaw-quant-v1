from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant.data.layer.data_quality import DataQualityAnalyzer, DataRefreshManager
from quant.data.layer.symbol_metadata import SymbolMetadataStore
from quant.storage.sqlite_store import SQLitePriceStore


class FakeRefreshSource:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def fetch_daily_prices(self, symbol, start=None, end=None):
        self.calls.append((symbol, start, end))
        if self.fail:
            raise RuntimeError("api unavailable")
        rows = [
            {
                "symbol": symbol,
                "date": "2024-01-02",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "adj_close": 100,
                "volume": 1000,
            },
            {
                "symbol": symbol,
                "date": "2024-01-03",
                "open": 101,
                "high": 102,
                "low": 100,
                "close": 101,
                "adj_close": 101,
                "volume": 1000,
            },
        ]
        if start and str(start) > "2024-01-03":
            rows = []
        return pd.DataFrame(rows)


def seed_prices(db_path: Path, symbol: str = "SPY", days: int = 70, zero_volume: bool = False) -> None:
    rows = []
    for index, date_value in enumerate(pd.bdate_range("2024-01-01", periods=days)):
        close = 100 + index * 0.5
        rows.append(
            {
                "symbol": symbol,
                "date": date_value.strftime("%Y-%m-%d"),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "adj_close": close,
                "volume": 0 if zero_volume and index < 8 else 1000,
            }
        )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def analyzer(db_path: Path, tmp_path: Path) -> DataQualityAnalyzer:
    return DataQualityAnalyzer(
        SQLitePriceStore(db_path),
        SymbolMetadataStore(db_path),
        report_dir=tmp_path / "reports",
    )


def test_missing_data_detection(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    report = analyzer(db_path, tmp_path).analyze(["SPY"])

    assert report.status == "FAIL"
    assert report.diagnostics["SPY"]["checks"]["missing_ratio"]["status"] == "FAIL"


def test_duplicate_detection_check_is_reported(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    report = analyzer(db_path, tmp_path).analyze(["SPY"])

    duplicate_check = report.diagnostics["SPY"]["checks"]["duplicate_rows"]
    assert duplicate_check["value"] == 0
    assert duplicate_check["status"] == "PASS"


def test_zero_volume_and_short_history_warnings(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, days=30, zero_volume=True)
    report = analyzer(db_path, tmp_path).analyze(["SPY"])

    checks = report.diagnostics["SPY"]["checks"]
    assert checks["zero_volume_days"]["status"] == "FAIL"
    assert checks["short_history"]["status"] == "WARNING"
    assert "stale_data" in checks
    assert "adjusted_close_availability" in checks


def test_zero_or_negative_price_detection(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, days=70)
    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "SPY",
                    "date": "2024-04-09",
                    "open": 0,
                    "high": 0,
                    "low": -1,
                    "close": 0,
                    "adj_close": 0,
                    "volume": 1000,
                }
            ]
        )
    )

    report = analyzer(db_path, tmp_path).analyze(["SPY"])

    assert report.diagnostics["SPY"]["checks"]["zero_negative_prices"]["status"] == "FAIL"


def test_stale_data_detection(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, days=70)

    report = analyzer(db_path, tmp_path).analyze(["SPY"])

    assert report.diagnostics["SPY"]["checks"]["stale_data"]["status"] == "FAIL"


def test_coverage_report(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, "SPY", days=10)
    coverage = analyzer(db_path, tmp_path).coverage(["SPY", "QQQ"])

    assert coverage["total_symbols"] == 2
    assert coverage["symbols_with_price_data"] == 1
    assert coverage["symbols_without_price_data"] == 1
    assert "average_history_length" in coverage
    assert "newest_date" in coverage
    assert "symbols" in coverage
    assert coverage["oldest_date"] == "2024-01-01"
    assert coverage["symbols"][0]["metadata_available"] is True
    assert Path(coverage["report_path"]).exists()


def test_data_gap_detection(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, days=70)
    with SQLitePriceStore(db_path).connect() as connection:
        connection.execute("DELETE FROM prices WHERE symbol = ? AND date BETWEEN ? AND ?", ("SPY", "2024-02-01", "2024-02-12"))

    report = analyzer(db_path, tmp_path).analyze(["SPY"])

    assert report.diagnostics["SPY"]["checks"]["data_gaps"]["status"] in {"WARNING", "FAIL"}


def test_readiness_score_and_recommendations(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, "SPY", days=70)
    readiness = analyzer(db_path, tmp_path).readiness(["SPY", "QQQ", "NVDA"])

    assert 0 <= readiness["readiness_score"] <= 100
    assert "Need broader price coverage" in readiness["recommendations"]
    assert Path(readiness["report_path"]).exists()


def test_readiness_score_decreases_for_small_low_coverage_universe(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    for symbol in ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "TSLA"]:
        seed_prices(db_path, symbol, days=300)
    quality = analyzer(db_path, tmp_path)

    weak = quality.readiness(["SPY"])
    stronger = quality.readiness(["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "TSLA"])

    assert weak["readiness_score"] < stronger["readiness_score"]
    assert "Need more symbols" in weak["recommendations"]
    assert "Need sector diversity" in weak["recommendations"]


def test_data_refresh_skips_existing_and_does_not_duplicate_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    store = SQLitePriceStore(db_path)
    source = FakeRefreshSource()
    manager = DataRefreshManager(store, source, report_dir=tmp_path / "reports")

    first = manager.refresh(["SPY"], start_date="2024-01-01")
    second = manager.refresh(["SPY"])

    assert first.per_symbol["SPY"]["inserted"] == 2
    assert second.per_symbol["SPY"]["inserted"] == 0
    assert second.per_symbol["SPY"]["updated"] == 0
    assert second.per_symbol["SPY"]["skipped"] == 2
    assert len(store.get_price_history("SPY")) == 2


def test_data_refresh_updates_stale_requested_range(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    store = SQLitePriceStore(db_path)
    manager = DataRefreshManager(store, FakeRefreshSource(), report_dir=tmp_path / "reports")

    manager.refresh(["SPY"], start_date="2024-01-01")
    second = manager.refresh(["SPY"], start_date="2024-01-01")

    assert second.per_symbol["SPY"]["updated"] == 2
    assert len(store.get_price_history("SPY")) == 2


def test_data_refresh_handles_api_failure_gracefully(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    manager = DataRefreshManager(SQLitePriceStore(db_path), FakeRefreshSource(fail=True), report_dir=tmp_path / "reports")

    report = manager.refresh(["SPY"], start_date="2024-01-01")

    assert report.summary["errors"] == 1
    assert report.per_symbol["SPY"]["status"] == "ERROR"
    assert "api unavailable" in report.per_symbol["SPY"]["error"]
