from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant.agent_export.agent_exporter import AgentExporter
from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.cli_commands.common import create_context
from quant.performance import PerformanceProfiler, RuntimeTracker
from quant.storage.sqlite_store import SQLitePriceStore
from quant.visualization.report_visualizer import ReportVisualizer


def seed_prices(db_path: Path) -> None:
    rows = []
    for index in range(160):
        date = (pd.Timestamp("2023-01-01") + pd.Timedelta(days=index)).strftime("%Y-%m-%d")
        for offset, symbol in enumerate(["SPY", "QQQ", "AAPL", "MSFT", "NVDA"], start=1):
            close = 100 + index * offset * 0.1
            rows.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000 + index,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_runtime_tracker_collects_summary() -> None:
    tracker = RuntimeTracker()
    with tracker.track("unit", "example"):
        pass

    summary = tracker.summary()

    assert summary["event_count"] == 1
    assert summary["by_category"]["unit"]["count"] == 1
    assert summary["slowest_events"][0]["name"] == "example"


def test_performance_profiler_generates_report(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    context = create_context(db_path)

    report = PerformanceProfiler(context, report_dir=tmp_path / "reports").run(
        targets=["factor_eval"],
        factors=["momentum_20d"],
        max_symbols=3,
        max_factors=1,
    )

    assert report["metadata"]["report_type"] == "performance_profile"
    assert report["metadata"]["measurement_only"] is True
    assert report["target_results"]
    assert "call_counts" in report
    assert "runtime_seconds" in report
    assert report["database_profile"]["query_count"] > 0
    assert Path(report["report_path"]).exists()
    assert Path(report["summary_path"]).exists()


def test_performance_agent_export_and_visualization(tmp_path: Path) -> None:
    report = {
        "metadata": {"report_type": "performance_profile"},
        "summary": {"total_runtime_seconds": 1.2, "event_count": 2, "target_count": 1},
        "runtime_breakdown": {"by_category": {"factor_eval": {"count": 1, "runtime_seconds": 1.0}}},
        "database_profile": {"query_count": 2, "runtime_seconds": 0.2, "slowest_queries": [{"name": "get_price_history", "count": 2, "runtime_seconds": 0.2}]},
        "slowest_modules": [{"module": "factor_eval", "runtime_seconds": 1.0, "status": "PASS"}],
        "slowest_functions": [{"category": "factor_eval", "name": "momentum_20d", "runtime_seconds": 1.0}],
        "slowest_queries": [{"name": "get_price_history", "count": 2, "runtime_seconds": 0.2}],
        "recommendations": ["Measure before optimizing."],
    }
    path = tmp_path / "performance_profile.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    export = AgentExporter().export_file(path, output_format="json")
    visualization = ReportVisualizer(output_dir=tmp_path / "charts").visualize_file(path)

    assert '"report_type": "performance_profile"' in export
    assert visualization.report_type == "performance_profile"
    assert visualization.charts


def test_performance_visualization_missing_fields_skips_safely(tmp_path: Path) -> None:
    path = tmp_path / "performance_profile_minimal.json"
    path.write_text(
        json.dumps({"metadata": {"report_type": "performance_profile"}, "summary": {}}),
        encoding="utf-8",
    )

    visualization = ReportVisualizer(output_dir=tmp_path / "charts").visualize_file(path)

    assert visualization.report_type == "performance_profile"
    assert visualization.dashboard_path
    assert any("VISUALIZATION_SKIPPED_CHART" in warning for warning in visualization.warnings)


def test_performance_cli_registered_and_smoke(tmp_path: Path, capsys) -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    assert "performance-profile" in subparsers_action.choices
    assert "performance-summary" in COMMAND_HANDLERS

    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "performance-profile",
            "--target",
            "factor_eval",
            "--factor",
            "momentum_20d",
            "--max-symbols",
            "3",
            "--max-factors",
            "1",
        ]
    )

    assert exit_code == 0
    assert "Performance Profile Summary" in capsys.readouterr().out
