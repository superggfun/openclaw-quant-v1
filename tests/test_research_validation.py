from __future__ import annotations

from pathlib import Path

from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.cli_commands.common import create_context
from quant.research_validation import ResearchValidationRunner


def test_research_validation_quick_can_write_partial_report(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=0,
        max_strategies=0,
        max_folds=1,
        timeout_seconds=5,
    )

    assert report["metadata"]["report_type"] == "research_validation"
    assert report["mode"] == "quick"
    assert Path(report["report_path"]).exists()
    assert Path(report["summary_path"]).exists()
    assert Path(report["agent_summary_path"]).exists()
    assert "completed_steps" in report
    assert "skipped_steps" in report
    assert "slowest_steps" in report
    assert "recommended_performance_work" in report


def test_research_validation_budget_records_timeout(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=1,
        max_strategies=0,
        max_folds=1,
        timeout_seconds=0,
    )

    assert report["partial_results"] is True
    assert report["timed_out_steps"]
    assert any(row["code"] == "PARTIAL_RESULTS" for row in report["warning_statistics"])


def test_research_validation_cli_registered_and_smoke(tmp_path: Path, capsys) -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    assert "research-validation" in subparsers_action.choices
    assert "research-validation" in COMMAND_HANDLERS

    db_path = tmp_path / "quant.db"
    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "research-validation",
            "--mode",
            "quick",
            "--max-factors",
            "0",
            "--max-strategies",
            "0",
            "--max-folds",
            "1",
            "--timeout-seconds",
            "5",
            "--batch-size",
            "5",
            "--max-symbols",
            "5",
            "--factor-family",
            "price",
        ]
    )

    assert exit_code == 0
    assert "Research Validation Summary" in capsys.readouterr().out


def test_research_validation_reports_batching_and_symbol_diagnostics(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=0,
        max_strategies=0,
        max_folds=1,
        timeout_seconds=5,
        batch_size=2,
        max_symbols=3,
        factor_family="price",
    )

    assert report["parameters"]["batch_size"] == 2
    assert report["parameters"]["max_symbols"] == 3
    assert report["parameters"]["factor_family"] == "price"
    assert "symbol_diagnostics" in report
    assert "batching" in report
    assert "factor_evidence_summary" in report


def test_research_validation_factor_family_filter(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    runner = ResearchValidationRunner(context, report_dir=tmp_path / "reports")

    price_factors = runner._select_factors("quick", 5, "price")
    fundamental_factors = runner._select_factors("quick", 5, "fundamental")

    assert price_factors
    assert fundamental_factors
    assert all(not runner.factor_registry.describe(factor).fundamental_data_required for factor in price_factors)
    assert all(runner.factor_registry.describe(factor).fundamental_data_required for factor in fundamental_factors)
