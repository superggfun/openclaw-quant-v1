from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.cli import main
from quant.data.fundamental.fundamental_service import FundamentalService
from quant.data.fundamental.fundamental_store import FundamentalStore


def write_csv(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    path = tmp_path / name
    fields = sorted({key for row in rows for key in row})
    lines = [",".join(fields)]
    for row in rows:
        lines.append(",".join(str(row.get(field, "")) for field in fields))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def income_row(**overrides) -> dict:
    row = {
        "statement_type": "income_statement",
        "symbol": "aapl",
        "fiscal_period_end": "2024-03-30",
        "report_date": "2024-05-03",
        "fiscal_year": "2024",
        "fiscal_quarter": "Q2",
        "currency": "USD",
        "revenue": "100",
        "gross_profit": "50",
        "operating_income": "30",
        "net_income": "20",
        "eps_basic": "1.0",
        "eps_diluted": "0.99",
        "shares_outstanding_basic": "1000",
        "shares_outstanding_diluted": "1010",
    }
    row.update(overrides)
    return row


def balance_row(**overrides) -> dict:
    row = {
        "statement_type": "balance_sheet",
        "symbol": "AAPL",
        "fiscal_period_end": "2024-03-30",
        "report_date": "2024-05-03",
        "fiscal_year": "2024",
        "fiscal_quarter": "Q2",
        "currency": "USD",
        "total_assets": "1000",
        "total_liabilities": "400",
        "total_equity": "600",
    }
    row.update(overrides)
    return row


def metrics_row(**overrides) -> dict:
    row = {
        "statement_type": "fundamental_metrics",
        "symbol": "AAPL",
        "fiscal_period_end": "2024-03-30",
        "report_date": "2024-05-03",
        "fiscal_year": "2024",
        "fiscal_quarter": "Q2",
        "currency": "USD",
        "pe_ratio": "25",
        "pb_ratio": "8",
        "ps_ratio": "7",
        "ev_to_ebitda": "20",
        "roe": "0.2",
        "roa": "0.1",
    }
    row.update(overrides)
    return row


def service(tmp_path: Path) -> FundamentalService:
    return FundamentalService(FundamentalStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports")


def test_database_table_creation(tmp_path: Path) -> None:
    FundamentalStore(tmp_path / "quant.db")
    with sqlite3.connect(tmp_path / "quant.db") as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert {"income_statement", "balance_sheet", "cash_flow", "fundamental_metrics", "fundamental_import_log"} <= tables


def test_statement_tables_have_timestamps_and_currency(tmp_path: Path) -> None:
    FundamentalStore(tmp_path / "quant.db")
    with sqlite3.connect(tmp_path / "quant.db") as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(income_statement)")
        }

    assert {"currency", "created_at", "updated_at"} <= columns


def test_idempotent_import_and_symbol_normalization(tmp_path: Path) -> None:
    svc = service(tmp_path)
    csv_path = write_csv(tmp_path, "income.csv", [income_row()])

    first = svc.import_csv(csv_path)
    second = svc.import_csv(csv_path)
    rows = svc.show("AAPL", statement="income")

    assert first["summary"]["inserted"] == 1
    assert second["summary"]["updated"] == 1
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"


def test_older_report_date_does_not_overwrite_without_force(tmp_path: Path) -> None:
    svc = service(tmp_path)
    newer = write_csv(tmp_path, "newer.csv", [income_row(report_date="2024-05-03", revenue="100")])
    older = write_csv(tmp_path, "older.csv", [income_row(report_date="2024-04-01", revenue="50")])

    svc.import_csv(newer)
    skipped = svc.import_csv(older)
    row = svc.show("AAPL", statement="income", latest=True)[0]

    assert skipped["summary"]["skipped"] == 1
    assert row["revenue"] == 100


def test_force_import_allows_older_report_date_update(tmp_path: Path) -> None:
    svc = service(tmp_path)
    newer = write_csv(tmp_path, "newer.csv", [income_row(report_date="2024-05-03", revenue="100")])
    older = write_csv(tmp_path, "older.csv", [income_row(report_date="2024-04-01", revenue="50")])

    svc.import_csv(newer)
    forced = svc.import_csv(older, force=True)
    row = svc.show("AAPL", statement="income", latest=True)[0]

    assert forced["summary"]["updated"] == 1
    assert row["revenue"] == 50


def test_statement_specific_import(tmp_path: Path) -> None:
    svc = service(tmp_path)
    row = income_row()
    row.pop("statement_type")
    csv_path = write_csv(tmp_path, "income_only.csv", [row])

    result = svc.import_csv(csv_path, statement="income")

    assert result["summary"]["inserted"] == 1
    assert svc.show("AAPL", statement="income", latest=True)


def test_malformed_csv_missing_required_columns(tmp_path: Path) -> None:
    svc = service(tmp_path)
    csv_path = write_csv(tmp_path, "bad.csv", [{"symbol": "AAPL"}])

    with pytest.raises(ValueError, match="missing required columns"):
        svc.import_csv(csv_path)


def test_blank_numeric_fields_are_missing(tmp_path: Path) -> None:
    svc = service(tmp_path)
    csv_path = write_csv(tmp_path, "blank.csv", [income_row(revenue="", eps_basic="")])

    svc.import_csv(csv_path)
    row = svc.show("AAPL", statement="income", latest=True)[0]

    assert row["revenue"] is None
    assert row["eps_basic"] is None


def test_annual_and_quarterly_records(tmp_path: Path) -> None:
    svc = service(tmp_path)
    csv_path = write_csv(tmp_path, "mixed.csv", [income_row(fiscal_quarter="FY"), income_row(fiscal_quarter="Q2")])

    result = svc.import_csv(csv_path)

    assert result["summary"]["inserted"] == 2
    assert len(svc.show("AAPL", statement="income")) == 2


def test_coverage_calculation(tmp_path: Path) -> None:
    svc = service(tmp_path)
    svc.import_csv(write_csv(tmp_path, "coverage.csv", [income_row(), balance_row()]))

    report = svc.coverage(["AAPL", "MSFT"])

    coverage = report["coverage"]
    assert coverage["total_symbols"] == 2
    assert coverage["symbols_with_any_fundamental_data"] == 1
    assert coverage["symbols_missing_fundamental_data"] == 1
    assert coverage["statement_coverage"]["income_statement"] == 1


def test_quality_warnings(tmp_path: Path) -> None:
    svc = service(tmp_path)
    csv_path = write_csv(
        tmp_path,
        "quality.csv",
        [
            income_row(revenue="-1", shares_outstanding_basic="", shares_outstanding_diluted="", currency="EUR"),
            balance_row(total_assets="-5", total_equity="0"),
            metrics_row(pe_ratio="999"),
        ],
    )
    svc.import_csv(csv_path)

    report = svc.quality(["AAPL"])
    codes = {item["code"] for item in report["quality_checks"]}

    assert "NEGATIVE_REVENUE" in codes
    assert "MISSING_SHARES_OUTSTANDING" in codes
    assert "CURRENCY_MISMATCH" in codes
    assert "NEGATIVE_TOTAL_ASSETS" in codes
    assert "ZERO_OR_NEGATIVE_TOTAL_EQUITY" in codes
    assert "EXTREME_RATIO" in codes


def test_missing_sequential_quarters_warning(tmp_path: Path) -> None:
    svc = service(tmp_path)
    csv_path = write_csv(
        tmp_path,
        "quarter_gap.csv",
        [
            income_row(fiscal_year="2024", fiscal_quarter="Q1", fiscal_period_end="2024-01-31"),
            income_row(fiscal_year="2024", fiscal_quarter="Q3", fiscal_period_end="2024-07-31"),
        ],
    )
    svc.import_csv(csv_path)

    report = svc.quality(["AAPL"])
    codes = {item["code"] for item in report["quality_checks"]}

    assert "MISSING_SEQUENTIAL_QUARTERS" in codes


def test_fundamental_show_latest_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "quant.db"
    svc = FundamentalService(FundamentalStore(db_path), report_dir=tmp_path / "reports")
    svc.import_csv(write_csv(tmp_path, "cli.csv", [income_row()]))

    assert main(["--db-path", str(db_path), "fundamental-show", "--symbol", "AAPL", "--latest"]) == 0
    output = capsys.readouterr().out

    assert "Fundamental Rows" in output
    assert "income_statement AAPL" in output


def test_agent_export_supports_fundamental_coverage(tmp_path: Path) -> None:
    svc = service(tmp_path)
    svc.import_csv(write_csv(tmp_path, "coverage.csv", [income_row()]))
    report = svc.coverage(["AAPL", "MSFT"])

    rendered = AgentExporter().export_file(report["report_path"], output_format="json")
    payload = json.loads(rendered)

    assert payload["report_type"] == "fundamental_coverage"
    assert payload["key_metrics"]["readiness_score"] == report["coverage"]["readiness_score"]
