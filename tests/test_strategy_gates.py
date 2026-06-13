from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.cli_commands.common import create_context
from quant.interfaces.mcp_server import MCPRequest
from quant.interfaces.mcp_server.capabilities import OFFLINE_SIMULATION, READ_ONLY
from quant.interfaces.mcp_server.tool_registry import create_default_mcp_registry
from quant.storage.sqlite_store import SQLitePriceStore
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.engines.strategy_gates.gate_discovery import discover_gate_specs
from quant.engines.strategy_gates.gate_registry import GateRegistry
from quant.engines.strategy_gates.gate_runner import StrategyGateRunner
from quant.reports.visualization.report_visualizer import ReportVisualizer


def _strategy_yaml(extra: str = "") -> str:
    return f"""
name: gate_test
description: Gate test strategy
version: v1
author: tests
created_at: 2026-06-12
universe:
  type: custom
  symbols:
    - SPY
    - AAPL
factors:
  - name: momentum_20d
    weight: 0.50
  - name: low_volatility_score
    weight: 0.50
portfolio:
  method: equal_weight
  max_position_weight: 0.50
  cash_buffer: 0.10
risk:
  max_drawdown_limit: 0.25
execution:
  cost_model: combined
  slippage_model: bps
  slippage_bps: 5
validation:
  require_walk_forward: true
  minimum_ic: 0.02
  minimum_coverage: 0.30
  minimum_regime_sample: 30
metadata:
  top_n: 2
{extra}
"""


def _seed_prices(db_path: Path) -> None:
    rows = []
    for index in range(180):
        date = (pd.Timestamp("2023-10-01") + pd.Timedelta(days=index)).strftime("%Y-%m-%d")
        for symbol, slope in {"SPY": 0.20, "AAPL": 0.35}.items():
            close = 100 + index * slope
            rows.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def _write_strategy(tmp_path: Path, text: str | None = None) -> Path:
    strategy_dir = tmp_path / "strategies"
    strategy_dir.mkdir()
    path = strategy_dir / "gate_test.yaml"
    path.write_text(text or _strategy_yaml(), encoding="utf-8")
    return strategy_dir


def test_strategy_gate_runner_reports_warnings_for_missing_evidence(tmp_path: Path) -> None:
    strategy_dir = _write_strategy(tmp_path)
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    context = create_context(db_path)

    report = StrategyGateRunner(context, strategy_dir=strategy_dir, report_dir=tmp_path / "reports").run("gate_test")

    assert report["metadata"]["report_type"] == "strategy_gate"
    assert report["overall_status"] == "WARNING"
    assert any(gate["gate_name"] == "factor_history" for gate in report["gate_results"])
    assert "WARN_FACTOR_EVIDENCE_WEAK" in {gate["reason_code"] for gate in report["gate_results"]}
    assert report["no_lookahead"] is True
    assert Path(report["report_path"]).exists()


def test_strategy_gates_are_auto_discovered() -> None:
    registry = GateRegistry()
    discovered_names = [spec.name for spec in discover_gate_specs()]

    assert registry.names() == discovered_names
    assert discovered_names == [
        "schema_validation",
        "data_quality",
        "factor_history",
        "walk_forward",
        "regime_coverage",
        "trading_simulation",
        "complexity",
    ]


def test_strategy_gate_rejects_invalid_dsl_and_lookahead_override(tmp_path: Path) -> None:
    strategy_dir = _write_strategy(tmp_path, _strategy_yaml("validation:\n  allow_lookahead: true\n"))
    context = create_context(tmp_path / "quant.db")

    report = StrategyGateRunner(context, strategy_dir=strategy_dir, report_dir=tmp_path / "reports").run("gate_test")

    assert report["overall_status"] == "REJECTED"
    assert "NO_LOOKAHEAD_OVERRIDE_NOT_ALLOWED" in " ".join(report["rejection_reasons"])


def test_strategy_run_with_gates_attaches_gate_report(tmp_path: Path) -> None:
    strategy_dir = _write_strategy(tmp_path)
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    context = create_context(db_path)
    registry = StrategyRegistry(context, strategy_dir=strategy_dir, report_dir=tmp_path / "reports")

    report = registry.run("gate_test", start="2024-01-01", end="2024-03-01", with_gates=True)

    assert report["gate_summary"]["overall_status"] in {"PASS", "WARNING"}
    assert Path(report["artifacts"]["strategy_gate_report_path"]).exists()
    assert report["artifacts"]["strategy_gate_report_path"] in report["generated_reports"]


def test_strategy_gate_cli_commands_registered_and_smoke(tmp_path: Path, capsys) -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    for command in ("strategy-gate", "strategy-gate-report"):
        assert command in subparsers_action.choices
        assert command in COMMAND_HANDLERS

    strategy_dir = _write_strategy(tmp_path)
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)

    assert main(["--db-path", str(db_path), "strategy-gate", "--strategy", "gate_test", "--strategy-dir", str(strategy_dir)]) == 0
    assert "Strategy Gate Summary" in capsys.readouterr().out
    assert main(["--db-path", str(db_path), "strategy-gate-report", "--latest"]) == 0
    assert "overall_status:" in capsys.readouterr().out


def test_strategy_gate_agent_export_and_visualization(tmp_path: Path) -> None:
    strategy_dir = _write_strategy(tmp_path)
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    context = create_context(db_path)
    report = StrategyGateRunner(context, strategy_dir=strategy_dir, report_dir=tmp_path / "reports").run("gate_test")

    exported = json.loads(AgentExporter().export_file(report["report_path"], output_format="json"))
    visual = ReportVisualizer(output_dir=tmp_path / "charts").visualize_file(report["report_path"])

    assert exported["report_type"] == "strategy_gate"
    assert exported["key_metrics"]["overall_status"] == report["overall_status"]
    assert visual.report_type == "strategy_gate"
    assert any(chart["chart_id"] == "gate_status_summary" for chart in visual.charts)


def test_strategy_gate_mcp_tools_have_expected_capabilities(tmp_path: Path) -> None:
    strategy_dir = _write_strategy(tmp_path)
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    context = create_context(db_path)
    registry = create_default_mcp_registry()

    assert registry.lookup("run_strategy_gates").metadata.capability_level == OFFLINE_SIMULATION
    assert registry.lookup("latest_strategy_gate_report").metadata.capability_level == READ_ONLY
    response = registry.execute(
        MCPRequest("run_strategy_gates", {"strategy": "gate_test", "strategy_dir": str(strategy_dir)}),
        context,
    )
    latest = registry.execute(MCPRequest("latest_strategy_gate_report"), context)

    assert response.status == "OK"
    assert response.result["metadata"]["report_type"] == "strategy_gate"
    assert latest.status == "OK"
