from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.cli_commands.common import create_context
from quant.research_validation import ResearchValidationRunner
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, symbols: list[str], days: int = 150) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 100 + symbol_index * 5
        for offset in range(days):
            close = base + offset * 0.1
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000 + offset,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_research_validation_quick_can_write_partial_report(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=0,
        max_strategies=0,
        max_folds=1,
        timeout_seconds=5,
        cost_profile="realistic",
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
    assert report["parameters"]["cost_profile"] == "realistic"
    saved_report = json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))
    assert saved_report["run_id"] == report["run_id"]
    assert saved_report["manifest_path"] == report["manifest_path"]
    assert saved_report["performance_metadata"]["aggregate_report_size_bytes"] == Path(report["report_path"]).stat().st_size


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
            "--cost-profile",
            "realistic",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Research Validation Plan" in output
    assert "cost_profile: realistic" in output
    assert "expected_task_count:" in output
    assert "Research Validation Summary" in output


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


def test_research_validation_quick_defaults_to_bounded_recent_window(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        max_factors=0,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=10,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
    )

    assert report["start_date"] is None
    assert report["end_date"] is None
    assert report["effective_start_date"] == "2024-01-01"
    assert report["effective_end_date"] == "2024-05-29"
    assert report["frequency"] == "daily"
    assert report["forward_days"] == 20
    assert report["holding_period"] == 20
    assert report["trading_day_count"] == 150
    assert report["symbol_count"] == 5


def test_research_validation_explicit_date_window_is_reported(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=20,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
    )

    assert report["start_date"] == "2024-03-01"
    assert report["end_date"] == "2024-03-10"
    assert report["effective_start_date"] == "2024-03-01"
    assert report["effective_end_date"] == "2024-03-10"
    assert report["trading_day_count"] == 10
    assert report["estimated_observation_count"] == 50
    assert report["factor_eval_results"][0]["observation_count"] == 50


def test_research_validation_charts_are_opt_in(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=20,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
    )

    assert report["charts_enabled"] is False
    assert report["chart_count"] == 0
    assert report["visualizations"] == []
    assert not (tmp_path / "reports" / "charts").exists()


def test_research_validation_can_generate_charts_when_requested(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=20,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
        charts=True,
    )

    assert report["charts_enabled"] is True
    assert report["chart_count"] == len(report["visualizations"])
    assert report["chart_count"] > 0
    assert not (tmp_path / "reports" / "charts").exists()
    assert (Path(report["run_artifact_dir"]) / "charts").exists()


def test_research_validation_quick_default_keeps_top_level_compact(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=1,
        max_folds=0,
        timeout_seconds=30,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
    )

    top_level = {path.name for path in (tmp_path / "reports").glob("*") if path.is_file()}
    assert Path(report["report_path"]).name in top_level
    assert "research_validation_summary.md" in top_level
    assert "agent_export_research_validation.md" in top_level
    assert not any(name.startswith(("alpha_", "multi_factor_", "portfolio_construction_", "trade_sim_", "strategy_run_", "strategy_gate_", "factor_rank_", "regime_rank_")) for name in top_level)
    assert report["visualizations"] == []
    assert not (tmp_path / "reports" / "charts").exists()
    assert Path(report["manifest_path"]).exists()
    manifest = pd.read_json(report["manifest_path"], typ="series").to_dict()
    assert manifest["substep_report_paths"] == []
    assert manifest["artifact_paths"] == []


def test_research_validation_opt_in_artifacts_go_under_run_dir(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=1,
        max_folds=0,
        timeout_seconds=30,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
        write_substep_reports=True,
        write_batch_artifacts=True,
        charts=True,
    )

    run_dir = Path(report["run_artifact_dir"])
    manifest = pd.read_json(report["manifest_path"], typ="series").to_dict()
    assert run_dir.exists()
    assert manifest["substep_report_paths"]
    assert manifest["artifact_paths"]
    assert manifest["chart_paths"]
    assert all(str(run_dir) in path for path in manifest["substep_report_paths"])
    assert all(str(run_dir) in path for path in manifest["artifact_paths"])
    assert all(str(run_dir) in path for path in manifest["chart_paths"])
    top_level = {path.name for path in (tmp_path / "reports").glob("*") if path.is_file()}
    assert not any(name.startswith(("alpha_", "multi_factor_", "portfolio_construction_", "trade_sim_", "strategy_run_", "strategy_gate_")) for name in top_level)


def test_research_validation_factor_family_filter(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    runner = ResearchValidationRunner(context, report_dir=tmp_path / "reports")

    price_factors = runner._select_factors("quick", 5, "price")
    fundamental_factors = runner._select_factors("quick", 5, "fundamental")

    assert price_factors
    assert fundamental_factors
    assert all(not runner.factor_registry.describe(factor).fundamental_data_required for factor in price_factors)
    assert all(runner.factor_registry.describe(factor).fundamental_data_required for factor in fundamental_factors)
