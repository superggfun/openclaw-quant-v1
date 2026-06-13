from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quant.cli_commands.common import create_context
from quant.interfaces.mcp_server.mcp_models import MCPRequest
from quant.interfaces.mcp_server.tool_registry import create_default_mcp_registry
from quant.research_validation import ResearchValidationRunner
from quant.storage.sqlite_store import SQLitePriceStore
from tools.project_audit import ignored_generated_paths


def seed_prices(db_path: Path, symbols: list[str], days: int = 150) -> None:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 100 + symbol_index * 3
        for offset in range(days):
            close = base + offset * 0.15
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


def test_quick_mode_manifest_and_top_level_outputs_are_compact(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=1,
        max_folds=0,
        timeout_seconds=45,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
    )

    top_level = {path.name for path in (tmp_path / "reports").glob("*") if path.is_file()}
    assert top_level == {
        Path(report["report_path"]).name,
        "research_validation_summary.md",
        "agent_export_research_validation.md",
    }
    assert not (tmp_path / "reports" / "charts").exists()

    manifest = json.loads(Path(report["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["run_type"] == "research_validation"
    assert manifest["mode"] == "quick"
    assert manifest["status"] == report["status"]
    assert manifest["aggregate_report_path"] == report["report_path"]
    assert manifest["summary_paths"] == [report["summary_path"]]
    assert manifest["export_paths"] == [report["agent_summary_path"]]
    assert manifest["substep_report_paths"] == []
    assert manifest["artifact_paths"] == []
    assert manifest["chart_paths"] == []
    for child in ("summaries", "substeps", "artifacts", "charts", "exports", "logs"):
        assert (Path(report["run_artifact_dir"]) / child).is_dir()


def test_opt_in_reports_route_to_run_artifact_directory(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=1,
        max_folds=0,
        timeout_seconds=45,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
        write_substep_reports=True,
        write_batch_artifacts=True,
        charts=True,
    )

    run_dir = Path(report["run_artifact_dir"])
    manifest = json.loads(Path(report["manifest_path"]).read_text(encoding="utf-8"))
    top_level = {path.name for path in (tmp_path / "reports").glob("*") if path.is_file()}
    noisy_prefixes = (
        "alpha_",
        "multi_factor_",
        "portfolio_construction_",
        "trade_sim_",
        "strategy_run_",
        "strategy_gate_",
        "factor_rank_",
        "regime_rank_",
        "regime_detection_",
        "data_coverage_",
        "fundamental_coverage_",
    )
    assert not any(name.startswith(noisy_prefixes) for name in top_level)
    assert manifest["substep_report_paths"]
    assert manifest["artifact_paths"]
    assert manifest["chart_paths"]
    assert all(str(run_dir) in path for path in manifest["substep_report_paths"])
    assert all(str(run_dir) in path for path in manifest["artifact_paths"])
    assert all(str(run_dir) in path for path in manifest["chart_paths"])
    assert len(manifest["chart_paths"]) == len(list((run_dir / "charts").glob("*")))


def test_research_validation_compact_report_excludes_large_detail_fields(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    seed_prices(context.db_path, ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"], days=150)

    report = ResearchValidationRunner(context, report_dir=tmp_path / "reports").run(
        mode="quick",
        start="2024-03-01",
        end="2024-03-10",
        max_factors=1,
        max_strategies=0,
        max_folds=0,
        timeout_seconds=45,
        batch_size=5,
        max_symbols=5,
        factor_family="price",
        bulk_matrix=True,
        write_batch_artifacts=True,
    )

    assert report["factor_eval_results"]
    assert "observations" not in report["factor_eval_results"][0]
    assert report["factor_backtest_results"]
    backtest = report["factor_backtest_results"][0]
    assert "periods" not in backtest
    assert "long_symbols_by_date" not in backtest
    assert "short_symbols_by_date" not in backtest
    assert "observations" not in backtest
    assert backtest["artifact_path"]
    assert Path(backtest["artifact_path"]).exists()
    assert any(row["code"] == "REPORT_COMPACTED" for row in report["warning_statistics"])


def test_agent_export_and_mcp_use_compact_report_metadata(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    registry = create_default_mcp_registry()
    report_path = tmp_path / "factor_backtest_compact.json"
    report_path.write_text(
        json.dumps(
            {
                "factor": "momentum_20d",
                "holding_period": 20,
                "long_short_return": 0.12,
                "sharpe": 1.4,
                "max_drawdown": -0.05,
                "turnover": 0.3,
                "artifact_paths": ["reports/runs/example/artifacts/periods.csv"],
                "periods": [{"date": "2024-01-01", "symbols": ["SPY"]}] * 500,
            }
        ),
        encoding="utf-8",
    )

    response = registry.execute(MCPRequest("get_report_summary", {"report": str(report_path), "max_tokens": 400}), context).to_dict()
    encoded = json.dumps(response, sort_keys=True)

    assert response["status"] == "OK"
    assert response["result"]["report_type"] == "factor_backtest"
    assert "reports/runs/example/artifacts/periods.csv" in encoded
    assert "2024-01-01" not in encoded
    assert "periods" not in response["result"]["key_metrics"]


def test_report_runtime_paths_are_gitignored() -> None:
    ignored = ignored_generated_paths(
        [
            "reports/research_validation_20240101_000000.json",
            "reports/research_validation_summary.md",
            "reports/agent_export_research_validation.md",
            "reports/runs/rv-example/manifest.json",
            "reports/runs/rv-example/artifacts/periods.csv",
            "reports/runs/rv-example/charts/chart.png",
            "reports/research_validation_batches/detail.json",
            "reports/hpc_rolling_001.txt",
        ]
    )

    assert all(ignored.values())
