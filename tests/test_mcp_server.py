from __future__ import annotations

import json
from pathlib import Path

from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.cli_commands.common import create_context
from quant.interfaces.mcp_server import MCPRequest
from quant.interfaces.mcp_server.capabilities import (
    LIVE_TRADING_FORBIDDEN,
    OFFLINE_SIMULATION,
    PAPER_TRADING_RESERVED,
    READ_ONLY,
)
from quant.interfaces.mcp_server.mcp_models import MCPResponse
from quant.interfaces.mcp_server.server import LocalMCPServer
from quant.interfaces.mcp_server.tool_categories import DATA, FACTORS, RESEARCH, SECURITY
from quant.interfaces.mcp_server.tool_registry import FORBIDDEN_TOOL_NAMES, create_default_mcp_registry


def test_mcp_tool_registration_and_categories() -> None:
    registry = create_default_mcp_registry()
    tools = registry.list_tools()
    categories = registry.list_categories()

    assert len(tools) >= 30
    assert categories[DATA] >= 4
    assert categories[FACTORS] >= 5
    assert categories[RESEARCH] >= 4
    assert categories[SECURITY] == len(FORBIDDEN_TOOL_NAMES)
    assert registry.list_capabilities()[READ_ONLY] >= 20
    assert registry.list_capabilities()[OFFLINE_SIMULATION] == 3
    assert registry.list_capabilities()[LIVE_TRADING_FORBIDDEN] == len(FORBIDDEN_TOOL_NAMES)


def test_mcp_tool_lookup_and_metadata() -> None:
    registry = create_default_mcp_registry()
    tool = registry.lookup("detect_regime")
    metadata = tool.metadata.to_dict()

    assert metadata["name"] == "detect_regime"
    assert metadata["category"] == "REGIMES"
    assert metadata["capability_level"] == READ_ONLY
    assert metadata["version"] == "v0.36.0"
    assert metadata["return_schema"]["json_safe"] is True
    assert metadata["return_schema"]["binary_payloads"] is False


def test_mcp_response_is_json_serializable() -> None:
    response = MCPResponse(
        tool_name="example",
        status="OK",
        result={"path": Path("reports/example.json"), "items": {1, 2}},
    )

    encoded = json.dumps(response.to_dict(), sort_keys=True)

    assert "reports/example.json" in encoded
    assert "items" in encoded


def test_forbidden_trading_tools_return_not_supported(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    registry = create_default_mcp_registry()

    for tool_name in FORBIDDEN_TOOL_NAMES:
        response = registry.execute(MCPRequest(tool_name, {"symbol": "SPY"}), context)
        payload = response.to_dict()
        assert payload["status"] == "NOT_SUPPORTED_LIVE_TRADING_DISABLED"
        assert payload["metadata"]["capability_level"] == LIVE_TRADING_FORBIDDEN
        assert payload["metadata"]["read_only"] is True
        assert "MCP_TOOL_CAPABILITY_DISABLED" in payload["warnings"]


def test_blocked_tool_does_not_call_runner_implementation(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    registry = create_default_mcp_registry()
    tool = registry.lookup("place_order")
    called = {"value": False}

    def should_not_run(arguments, context):
        called["value"] = True
        return {"unexpected": True}

    registry.tools["place_order"] = type(tool)(
        metadata=tool.metadata,
        handler=should_not_run,
        required_arguments=tool.required_arguments,
    )

    response = registry.execute(MCPRequest("place_order"), context)

    assert response.status == "NOT_SUPPORTED_LIVE_TRADING_DISABLED"
    assert called["value"] is False


def test_read_only_and_offline_simulation_capabilities_are_allowed(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    registry = create_default_mcp_registry()

    read_only = registry.execute(MCPRequest("list_factors"), context)
    offline = registry.execute(
        MCPRequest(
            "run_trade_sim",
            {
                "start": "2024-01-01",
                "end": "2024-03-01",
                "symbols": ["SPY", "AAPL"],
                "portfolio_method": "equal_weight",
            },
        ),
        context,
    )

    assert registry.lookup("list_factors").metadata.capability_level == READ_ONLY
    assert read_only.status == "OK"
    assert registry.lookup("run_trade_sim").metadata.capability_level == OFFLINE_SIMULATION
    assert offline.status in {"OK", "ERROR"}
    if offline.status == "ERROR":
        assert "price data" in (offline.error or "")


def test_reserved_capability_class_exists() -> None:
    assert PAPER_TRADING_RESERVED == "PAPER_TRADING_RESERVED"


def test_mcp_factor_scheduler_report_and_visualization_integrations(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    registry = create_default_mcp_registry()
    report_path = tmp_path / "alpha_report.json"
    report_path.write_text(
        json.dumps(
            {
                "selected_symbols": ["SPY"],
                "target_weights": {"SPY": 0.9, "cash": 0.1},
                "warnings": [],
                "config": {"universe": ["SPY"]},
            }
        ),
        encoding="utf-8",
    )

    factor_response = registry.execute(MCPRequest("list_factors"), context).to_dict()
    status_response = registry.execute(MCPRequest("research_status"), context).to_dict()
    report_response = registry.execute(MCPRequest("get_report_summary", {"report": str(report_path)}), context).to_dict()
    visualization_response = registry.execute(MCPRequest("visualization_summary"), context).to_dict()

    assert factor_response["status"] == "OK"
    assert any(row["factor_name"] == "momentum_20d" for row in factor_response["result"]["factors"])
    assert status_response["status"] == "OK"
    assert status_response["result"]["status"] == "NO_RUNS"
    assert report_response["status"] == "OK"
    assert report_response["result"]["report_type"] == "alpha"
    assert visualization_response["status"] == "OK"
    assert "by_suffix" in visualization_response["result"]


def test_mcp_required_argument_validation(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    registry = create_default_mcp_registry()

    response = registry.execute(MCPRequest("evaluate_factor"), context)

    assert response.status == "ERROR"
    assert "missing required arguments" in (response.error or "")


def test_local_mcp_server_facade(tmp_path: Path) -> None:
    server = LocalMCPServer(create_context(tmp_path / "quant.db"))

    response = server.execute("get_provider_status")

    assert response.status == "OK"
    assert server.list_tools()


def test_mcp_cli_commands_registered() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    assert "mcp-list-tools" in subparsers_action.choices
    assert "mcp-tool-info" in COMMAND_HANDLERS
    assert "mcp-smoke" in COMMAND_HANDLERS


def test_mcp_cli_smoke(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "quant.db"

    exit_code = main(["--db-path", str(db_path), "mcp-smoke"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "get_provider_status: OK" in output
    assert "place_order: NOT_SUPPORTED" in output
    assert "unsupported_tools_blocked: True" in output


def test_all_registered_tools_have_required_metadata() -> None:
    registry = create_default_mcp_registry()

    for row in registry.list_tools():
        assert row["name"]
        assert row["category"]
        assert row["capability_level"] in {READ_ONLY, OFFLINE_SIMULATION, PAPER_TRADING_RESERVED, LIVE_TRADING_FORBIDDEN}
        assert row["description"]
        assert isinstance(row["arguments"], dict)
        assert isinstance(row["return_schema"], dict)
        assert row["version"] == "v0.36.0"


def test_report_and_visualization_responses_have_no_binary_payloads(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")
    registry = create_default_mcp_registry()
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps({"selected_symbols": ["SPY"], "target_weights": {"SPY": 0.9, "cash": 0.1}}),
        encoding="utf-8",
    )

    report = registry.execute(MCPRequest("get_report_summary", {"report": str(report_path)}), context).to_dict()
    visualization = registry.execute(MCPRequest("visualization_summary"), context).to_dict()
    encoded = json.dumps({"report": report, "visualization": visualization}, sort_keys=True)

    assert "<bytes:" not in encoded
    assert "visualizations" in encoded
