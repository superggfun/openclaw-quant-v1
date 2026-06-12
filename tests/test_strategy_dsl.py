from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.cli_commands.common import create_context
from quant.interfaces.mcp_server import MCPRequest
from quant.interfaces.mcp_server.capabilities import OFFLINE_SIMULATION, READ_ONLY
from quant.interfaces.mcp_server.tool_registry import create_default_mcp_registry
from quant.scheduler.scheduler_config import SchedulerConfig
from quant.scheduler.daily_research_run import DailyResearchRun
from quant.storage.sqlite_store import SQLitePriceStore
from quant.strategy_dsl.strategy_definition import StrategyDefinition
from quant.strategy_dsl.strategy_loader import StrategyLoader
from quant.strategy_dsl.strategy_parser import StrategyParser
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.strategy_dsl.strategy_validator import StrategyValidator


def _strategy_yaml() -> str:
    return """
name: test_strategy
description: Test strategy
version: v1
author: tests
created_at: 2026-06-12
tags:
  - test
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
regime:
  enabled: false
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
  max_adv_participation: 0.05
validation:
  require_walk_forward: false
  minimum_ic: 0.01
  minimum_coverage: 0.30
  minimum_regime_sample: 30
metadata:
  top_n: 2
"""


def _seed_prices(db_path: Path) -> None:
    rows = []
    for index in range(180):
        date = (pd.Timestamp("2023-10-01") + pd.Timedelta(days=index)).strftime("%Y-%m-%d")
        for symbol, slope in {"SPY": 0.20, "AAPL": 0.35, "QQQ": 0.25, "NVDA": 0.45, "MSFT": 0.30}.items():
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


def test_yaml_and_json_parsing(tmp_path: Path) -> None:
    yaml_path = tmp_path / "test_strategy.yaml"
    json_path = tmp_path / "test_strategy.json"
    yaml_path.write_text(_strategy_yaml(), encoding="utf-8")
    json_path.write_text(json.dumps(StrategyParser().parse_file(yaml_path)), encoding="utf-8")

    yaml_payload = StrategyParser().parse_file(yaml_path)
    json_payload = StrategyParser().parse_file(json_path)

    assert yaml_payload["name"] == "test_strategy"
    assert yaml_payload["factors"][0]["name"] == "momentum_20d"
    assert json_payload["portfolio"]["method"] == "equal_weight"


def test_strategy_definition_and_validation() -> None:
    definition = StrategyDefinition.from_mapping(StrategyParser().parse_yaml(_strategy_yaml()))
    result = StrategyValidator().validate(definition)

    assert definition.factor_weights == {"momentum_20d": 0.5, "low_volatility_score": 0.5}
    assert definition.symbols == ["SPY", "AAPL"]
    assert result.valid is True
    assert result.gates["factor_weight_sum"] == 1.0


def test_invalid_strategy_rejected() -> None:
    definition = StrategyDefinition.from_mapping(
        {
            "name": "bad",
            "factors": [{"name": "not_a_factor", "weight": -1}],
            "portfolio": {"method": "unknown"},
        }
    )

    result = StrategyValidator().validate(definition)

    assert result.valid is False
    assert "MISSING_DESCRIPTION" in result.errors
    assert "MISSING_VERSION" in result.errors
    assert "MISSING_AUTHOR" in result.errors
    assert "MISSING_CREATED_AT" in result.errors
    assert "UNSUPPORTED_FACTOR: not_a_factor" in result.errors
    assert "UNSUPPORTED_PORTFOLIO_METHOD: unknown" in result.errors


def test_unsupported_fields_warn_and_lookahead_override_fails() -> None:
    payload = StrategyParser().parse_yaml(_strategy_yaml())
    payload["portfolio"]["unexpected"] = True
    payload["risk"]["unknown_gate"] = 1
    payload["execution"]["live_trading"] = True
    payload["validation"]["allow_lookahead"] = True

    result = StrategyValidator().validate(StrategyDefinition.from_mapping(payload))

    assert result.valid is False
    assert "LIVE_TRADING_NOT_SUPPORTED" in result.errors
    assert "NO_LOOKAHEAD_OVERRIDE_NOT_ALLOWED" in result.errors
    assert "WARN_UNSUPPORTED_FIELD: portfolio.unexpected" in result.warnings
    assert "WARN_UNSUPPORTED_FIELD: risk.unknown_gate" in result.warnings
    assert "WARN_UNSUPPORTED_FIELD: validation.allow_lookahead" in result.warnings


def test_registry_list_show_and_version_storage(tmp_path: Path) -> None:
    strategy_dir = tmp_path / "strategies"
    strategy_dir.mkdir()
    (strategy_dir / "test_strategy.yaml").write_text(_strategy_yaml(), encoding="utf-8")
    context = create_context(tmp_path / "quant.db")
    registry = StrategyRegistry(context, strategy_dir=strategy_dir, report_dir=tmp_path / "reports")

    listing = registry.list_strategies()
    shown = registry.show("test_strategy")

    assert listing["strategy_count"] == 1
    assert shown["strategy"]["name"] == "test_strategy"
    with sqlite3.connect(context.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM strategy_registry").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM strategy_versions").fetchone()[0] == 1


def test_strategy_execution_and_report(tmp_path: Path) -> None:
    strategy_dir = tmp_path / "strategies"
    strategy_dir.mkdir()
    (strategy_dir / "test_strategy.yaml").write_text(_strategy_yaml(), encoding="utf-8")
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    registry = StrategyRegistry(create_context(db_path), strategy_dir=strategy_dir, report_dir=tmp_path / "reports")

    report = registry.run("test_strategy", start="2024-01-01", end="2024-03-31")

    assert report["metadata"]["report_type"] == "strategy_run"
    assert report["strategy_name"] == "test_strategy"
    assert report["strategy_file"].endswith("test_strategy.yaml")
    assert report["factor_weights"] == {"momentum_20d": 0.5, "low_volatility_score": 0.5}
    assert report["portfolio_settings"]["method"] == "equal_weight"
    assert report["risk_settings"]["max_drawdown_limit"] == 0.25
    assert report["execution_settings"]["cost_model"] == "combined"
    assert report["validation_results"]["valid"] is True
    assert report["generated_reports"]
    assert report["no_lookahead"] is True
    assert report["no_lookahead_notes"]
    assert report["trade_sim_summary"]["final_equity"] is not None
    assert Path(report["report_path"]).exists()
    assert Path(report["artifacts"]["trade_sim_report_path"]).exists()


def test_scheduler_strategy_step_is_optional_and_integrates(tmp_path: Path) -> None:
    strategy_dir = Path("strategies")
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    context = create_context(db_path)
    config = SchedulerConfig.from_mapping(
        {
            "run_data_refresh": False,
            "run_data_coverage": False,
            "run_fundamental_coverage": False,
            "run_factor_eval": False,
            "run_factor_store_update": False,
            "run_regime_detection": False,
            "run_trade_sim": False,
            "run_strategy": True,
            "run_visualization": False,
            "run_agent_export": False,
            "strategy_name": "regime_aware_momentum",
            "strategy_start": "2024-01-01",
            "strategy_end": "2024-03-31",
        }
    )

    report = DailyResearchRun(context, report_dir=tmp_path / "reports").run(config)

    assert any(step["name"] == "strategy_run" and step["status"] in {"PASS", "WARNING"} for step in report["pipeline_steps"])
    assert report["skipped_steps"]
    assert strategy_dir.exists()


def test_mcp_strategy_tools(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    context = create_context(db_path)
    registry = create_default_mcp_registry()

    assert registry.lookup("list_strategies").metadata.capability_level == READ_ONLY
    assert registry.lookup("run_strategy").metadata.capability_level == OFFLINE_SIMULATION
    list_response = registry.execute(MCPRequest("list_strategies"), context)
    validate_response = registry.execute(MCPRequest("validate_strategy", {"strategy": "momentum_fundamental"}), context)

    assert list_response.status == "OK"
    assert list_response.result["strategy_count"] >= 3
    assert validate_response.status == "OK"
    assert validate_response.result["valid"] is True


def test_strategy_run_does_not_see_future_fundamental_report_date(tmp_path: Path) -> None:
    strategy_dir = tmp_path / "strategies"
    strategy_dir.mkdir()
    strategy_yaml = _strategy_yaml().replace(
        """  - name: momentum_20d
    weight: 0.50
  - name: low_volatility_score
    weight: 0.50""",
        """  - name: fundamental_quality_score
    weight: 1.00""",
    )
    (strategy_dir / "fundamental_only.yaml").write_text(strategy_yaml, encoding="utf-8")
    db_path = tmp_path / "quant.db"
    _seed_prices(db_path)
    context = create_context(db_path)
    _seed_fundamentals(context, future=False)
    registry = StrategyRegistry(context, strategy_dir=strategy_dir, report_dir=tmp_path / "reports")

    first = registry.run("test_strategy", start="2024-01-01", end="2024-01-31")
    first_trade_report = json.loads(Path(first["artifacts"]["trade_sim_report_path"]).read_text(encoding="utf-8"))
    first_targets = first_trade_report["rebalance_events"][0]["target_weights"]

    _seed_fundamentals(context, future=True)
    second = registry.run("test_strategy", start="2024-01-01", end="2024-01-31")
    second_trade_report = json.loads(Path(second["artifacts"]["trade_sim_report_path"]).read_text(encoding="utf-8"))
    second_targets = second_trade_report["rebalance_events"][0]["target_weights"]

    assert first_targets == second_targets
    assert first["no_lookahead"] is True


def test_strategy_cli_commands_registered_and_smoke(tmp_path: Path, capsys) -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    for command in ("strategy-list", "strategy-show", "strategy-validate", "strategy-run", "strategy-gate", "strategy-gate-report"):
        assert command in subparsers_action.choices
        assert command in COMMAND_HANDLERS

    db_path = tmp_path / "quant.db"
    assert main(["--db-path", str(db_path), "strategy-list"]) == 0
    assert "strategy_count:" in capsys.readouterr().out
    assert main(["--db-path", str(db_path), "strategy-validate"]) == 0
    assert "valid: true" in capsys.readouterr().out


def _seed_fundamentals(context, future: bool) -> None:
    base_rows = [
        ("SPY", "2023-09-30", "2023-12-15", 0.10),
        ("AAPL", "2023-09-30", "2023-12-15", 0.20),
    ]
    future_rows = [
        ("SPY", "2023-12-31", "2024-02-15", 9.0),
        ("AAPL", "2023-12-31", "2024-02-15", -9.0),
    ]
    for symbol, fiscal_end, report_date, value in base_rows + (future_rows if future else []):
        context.fundamental_store.upsert(
            "fundamental_metrics",
            {
                "symbol": symbol,
                "fiscal_period_end": fiscal_end,
                "report_date": report_date,
                "fiscal_year": 2023,
                "fiscal_quarter": "Q3" if fiscal_end.endswith("09-30") else "Q4",
                "currency": "USD",
                "roe": value,
                "roa": value,
                "gross_margin": value,
                "net_margin": value,
            },
        )
