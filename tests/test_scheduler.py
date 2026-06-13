from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.cli_commands.common import create_context
from quant.scheduler.daily_research_run import DailyResearchRun
from quant.scheduler.research_scheduler import ResearchScheduler
from quant.scheduler.scheduler_config import SchedulerConfig
from quant.scheduler.scheduler_history import SchedulerHistoryStore
from quant.storage.sqlite_store import SQLitePriceStore
from quant.reports.visualization.report_visualizer import ReportVisualizer


def seed_scheduler_prices(db_path: Path) -> None:
    rows = []
    dates = pd.bdate_range("2023-10-02", periods=180)
    for index, date in enumerate(dates):
        for symbol, slope in {"SPY": 0.10, "QQQ": 0.14, "NVDA": 0.20, "AAPL": 0.08}.items():
            close = 100 + index * slope + (index % 9) * 0.05
            rows.append(
                {
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def scheduler_config(report_dir: Path | None = None) -> SchedulerConfig:
    return SchedulerConfig.from_mapping(
        {
            "run_data_refresh": False,
            "run_data_coverage": True,
            "run_fundamental_coverage": True,
            "run_factor_eval": True,
            "run_factor_store_update": True,
            "run_regime_detection": True,
            "run_trade_sim": True,
            "run_visualization": True,
            "run_agent_export": True,
            "symbols": ["SPY", "QQQ", "NVDA", "AAPL"],
            "factors": ["momentum_20d"],
            "forward_days": 5,
            "trade_sim_start": "2024-01-02",
            "trade_sim_end": "2024-04-30",
            "trade_sim_rebalance_frequency": "monthly",
            "trade_sim_portfolio_method": "equal_weight",
            "alpha_config_path": str((report_dir or Path("missing")) / "missing_alpha.json"),
            "cost_config_path": str((report_dir or Path("missing")) / "missing_cost.json"),
            "market_realism_config_path": str((report_dir or Path("missing")) / "missing_realism.json"),
            "pipeline_mode": "test_lightweight",
            "lightweight_default": True,
        }
    )


def test_scheduler_commands_registered() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    assert {"research-run", "research-status", "research-history", "research-report"} <= set(subparsers_action.choices)
    assert {"research-run", "research-status", "research-history", "research-report"} <= set(COMMAND_HANDLERS)


def test_full_research_run_generates_report_history_agent_and_visuals(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_scheduler_prices(db_path)
    context = create_context(db_path)
    report_dir = tmp_path / "reports"

    report = DailyResearchRun(context, report_dir=report_dir).run(scheduler_config(report_dir))
    SchedulerHistoryStore(db_path).save(report)
    export = AgentExporter().export_file(report["report_path"], output_format="json")
    visual = ReportVisualizer(output_dir=tmp_path / "charts").visualize_file(report["report_path"])
    latest = SchedulerHistoryStore(db_path).latest()

    assert report["metadata"]["report_type"] == "research_run"
    assert report["status"] in {"PASS", "WARNING"}
    assert report["config_source"] == "defaults"
    assert report["pipeline_mode"] == "test_lightweight"
    assert report["lightweight_default"] is True
    assert "enabled_pipeline_steps" in report
    assert "disabled_pipeline_steps" in report
    assert "skipped_steps" in report
    assert "warning_summary" in report
    assert report["daily_research_summary"]["current_regime"]
    assert report["generated_reports"]
    assert report["generated_visualizations"]
    assert report["agent_exports"]
    assert report["generated_agent_exports"] == report["agent_exports"]
    assert report["report_path"]
    assert report["duration_seconds"] >= 0
    assert set(report["pipeline_step_summary"]) >= {"PASS", "WARNING", "FAIL", "SKIPPED"}
    assert latest and latest["run_id"] == report["run_id"]
    assert json.loads(export)["report_type"] == "research_run"
    assert visual.report_type == "research_run"
    assert visual.dashboard_path


def test_scheduler_failure_isolation_continues_later_steps(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "quant.db"
    seed_scheduler_prices(db_path)
    context = create_context(db_path)

    def fail_factor(*args, **kwargs):
        raise ValueError("factor failed intentionally")

    monkeypatch.setattr(context.factor_evaluation, "evaluate", fail_factor)
    report = DailyResearchRun(context, report_dir=tmp_path / "reports").run(scheduler_config(tmp_path))
    steps = {step["name"]: step for step in report["pipeline_steps"]}

    assert report["status"] == "FAIL"
    assert steps["factor_evaluation"]["status"] == "FAIL"
    assert steps["regime_detection"]["status"] in {"PASS", "WARNING"}
    assert steps["trade_simulation"]["status"] in {"PASS", "WARNING"}
    assert any("WARN_PIPELINE_STEP_FAILED" in warning for warning in report["warnings"])


def test_scheduler_skipped_steps_are_explicit(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_scheduler_prices(db_path)
    context = create_context(db_path)
    config = SchedulerConfig.from_mapping(
        scheduler_config(tmp_path).to_dict()
        | {
            "run_data_refresh": False,
            "run_trade_sim": False,
            "run_visualization": False,
            "run_agent_export": False,
        }
    )

    report = DailyResearchRun(context, report_dir=tmp_path / "reports").run(config)

    skipped = {step["name"]: step for step in report["skipped_steps"]}
    assert {"data_refresh", "trade_simulation", "visualization", "agent_export"} <= set(skipped)
    assert all(step["status"] == "SKIPPED" for step in skipped.values())
    assert all(step["reason"] == "disabled_by_config" for step in skipped.values())
    assert report["status"] == "WARNING"


def test_scheduler_all_skipped_run_is_warning_not_pass(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_scheduler_prices(db_path)
    context = create_context(db_path)
    config = SchedulerConfig.from_mapping(
        scheduler_config(tmp_path).to_dict()
        | {
            "run_data_refresh": False,
            "run_data_coverage": False,
            "run_fundamental_coverage": False,
            "run_factor_eval": False,
            "run_factor_store_update": False,
            "run_regime_detection": False,
            "run_trade_sim": False,
            "run_visualization": False,
            "run_agent_export": False,
        }
    )

    report = DailyResearchRun(context, report_dir=tmp_path / "reports").run(config)

    assert report["status"] == "WARNING"
    assert all(step["status"] == "SKIPPED" for step in report["pipeline_steps"])


def test_research_scheduler_status_history_and_latest_report(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_scheduler_prices(db_path)
    context = create_context(db_path)
    scheduler = ResearchScheduler(context, db_path, report_dir=tmp_path / "reports")

    report = scheduler.run(overrides=scheduler_config(tmp_path).to_dict())
    status = scheduler.status()
    history = scheduler.history(limit=5)
    latest_report = scheduler.latest_report()
    selected_report = scheduler.latest_report(run_id=report["run_id"])

    assert status["status"] in {"PASS", "WARNING"}
    assert history["runs"]
    assert latest_report["run_id"] == report["run_id"]
    assert selected_report["run_id"] == report["run_id"]


def test_research_cli_smoke_with_temp_db(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "quant.db"
    seed_scheduler_prices(db_path)
    config_path = tmp_path / "scheduler.json"
    config_path.write_text(json.dumps(scheduler_config(tmp_path).to_dict()), encoding="utf-8")

    assert main(["--db-path", str(db_path), "research-run", "--config", str(config_path)]) == 0
    assert "Daily Research Run Summary" in capsys.readouterr().out
    assert main(["--db-path", str(db_path), "research-status"]) == 0
    assert "Research Status" in capsys.readouterr().out
    assert main(["--db-path", str(db_path), "research-history"]) == 0
    assert "Research History" in capsys.readouterr().out
    assert main(["--db-path", str(db_path), "research-report"]) == 0
    assert "Research Report" in capsys.readouterr().out
    assert main(["--db-path", str(db_path), "research-report", "--run-id", "missing"]) == 0
    assert "NO_RUNS" in capsys.readouterr().out
