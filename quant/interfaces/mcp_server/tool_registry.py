"""Central registry for safe MCP research tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant.interfaces.mcp_server.capabilities import (
    LIVE_TRADING_FORBIDDEN,
    OFFLINE_SIMULATION,
    READ_ONLY,
    disabled_status,
    is_enabled,
)
from quant.interfaces.mcp_server.mcp_models import MCPRequest, MCPResponse, MCPTool, MCPToolMetadata, json_safe
from quant.interfaces.mcp_server.tool_categories import (
    DATA,
    FACTORS,
    REGIMES,
    REPORTS,
    RESEARCH,
    SECURITY,
    SIMULATION,
    VISUALIZATION,
)
from quant.interfaces.mcp_server.tool_runner import MCPToolRunner
from quant.interfaces.mcp_server.tool_schemas import object_schema, response_schema


FORBIDDEN_TOOL_NAMES = {
    "place_order",
    "submit_order",
    "cancel_order",
    "modify_position",
    "connect_broker",
    "execute_trade",
    "live_trade",
    "rebalance_live",
    "paper_trade_live",
}


@dataclass
class MCPToolRegistry:
    """Register, inspect, and execute safe MCP tools."""

    tools: dict[str, MCPTool]

    def register(self, tool: MCPTool) -> None:
        self.tools[tool.metadata.name] = tool

    def lookup(self, name: str) -> MCPTool:
        normalized = name.strip()
        if normalized in FORBIDDEN_TOOL_NAMES:
            return self.tools[normalized]
        try:
            return self.tools[normalized]
        except KeyError as exc:
            raise ValueError(f"unknown MCP tool: {name}") from exc

    def list_tools(self, category: str | None = None) -> list[dict[str, Any]]:
        rows = [tool.metadata.to_dict() for tool in self.tools.values()]
        if category:
            rows = [row for row in rows if row["category"] == category.upper()]
        return sorted(rows, key=lambda row: (row["category"], row["name"]))

    def list_categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tool in self.tools.values():
            counts[tool.metadata.category] = counts.get(tool.metadata.category, 0) + 1
        return dict(sorted(counts.items()))

    def list_capabilities(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tool in self.tools.values():
            capability = tool.metadata.capability_level
            counts[capability] = counts.get(capability, 0) + 1
        return dict(sorted(counts.items()))

    def execute(self, request: MCPRequest, context: Any) -> MCPResponse:
        tool = self.lookup(request.tool_name)
        capability = tool.metadata.capability_level
        if not is_enabled(capability):
            return MCPResponse(
                tool_name=request.tool_name,
                status=disabled_status(capability),
                result={"reason": "tool capability is disabled in v0.35 MCP research interface"},
                warnings=["MCP_TOOL_CAPABILITY_DISABLED"],
                metadata={
                    "version": tool.metadata.version,
                    "category": tool.metadata.category,
                    "capability_level": capability,
                    "read_only": True,
                    "offline_only": True,
                },
                request_id=request.request_id,
            )
        missing = [name for name in tool.required_arguments if name not in request.arguments]
        if missing:
            return MCPResponse(
                tool_name=request.tool_name,
                status="ERROR",
                error=f"missing required arguments: {', '.join(missing)}",
                metadata={"version": tool.metadata.version},
                request_id=request.request_id,
            )
        try:
            result = tool.handler(request.arguments, context)
        except Exception as exc:
            return MCPResponse(
                tool_name=request.tool_name,
                status="ERROR",
                error=str(exc),
                metadata={"version": tool.metadata.version},
                request_id=request.request_id,
            )
        return MCPResponse(
            tool_name=request.tool_name,
            status="OK",
            result=json_safe(result),
            warnings=list(result.get("warnings") or []) if isinstance(result, dict) else [],
            metadata={"version": tool.metadata.version, "read_only": _read_only(tool.metadata.name), "offline_only": True},
            request_id=request.request_id,
        )


def create_default_mcp_registry() -> MCPToolRegistry:
    runner = MCPToolRunner()
    registry = MCPToolRegistry(tools={})
    for name, category, capability, description, handler, required in [
        ("get_provider_status", DATA, READ_ONLY, "List data providers and health status.", runner.get_provider_status, ()),
        ("get_data_coverage", DATA, READ_ONLY, "Return stored price coverage for a universe.", runner.get_data_coverage, ()),
        ("get_fundamental_coverage", DATA, READ_ONLY, "Return fundamental data coverage for a universe.", runner.get_fundamental_coverage, ()),
        ("get_universe_summary", DATA, READ_ONLY, "Return available universes and selected symbols.", runner.get_universe_summary, ()),
        ("list_factors", FACTORS, READ_ONLY, "List registered factor metadata.", runner.list_factors, ()),
        ("factor_history", FACTORS, READ_ONLY, "Return persisted factor history.", runner.factor_history, ()),
        ("factor_rank", FACTORS, READ_ONLY, "Return persisted factor ranking diagnostics.", runner.factor_rank, ()),
        ("factor_store_summary", FACTORS, READ_ONLY, "Return factor store table counts and definitions.", runner.factor_store_summary, ()),
        ("evaluate_factor", FACTORS, READ_ONLY, "Run no-lookahead factor evaluation.", runner.evaluate_factor, ("factor",)),
        ("detect_regime", REGIMES, READ_ONLY, "Detect deterministic current market regime.", runner.detect_regime, ()),
        ("regime_history", REGIMES, READ_ONLY, "Return persisted regime history.", runner.regime_history, ()),
        ("regime_report", REGIMES, READ_ONLY, "Return regime diagnostics.", runner.regime_report, ()),
        ("regime_rank", REGIMES, READ_ONLY, "Return factor rankings by regime.", runner.regime_rank, ()),
        ("research_status", RESEARCH, READ_ONLY, "Return latest research run status.", runner.research_status, ()),
        ("research_history", RESEARCH, READ_ONLY, "Return recent research run history.", runner.research_history, ()),
        ("research_report", RESEARCH, READ_ONLY, "Return latest or selected research run report.", runner.research_report, ()),
        ("list_strategies", RESEARCH, READ_ONLY, "List Strategy DSL definitions.", runner.list_strategies, ()),
        ("show_strategy", RESEARCH, READ_ONLY, "Show a Strategy DSL definition.", runner.show_strategy, ()),
        ("validate_strategy", RESEARCH, READ_ONLY, "Validate a Strategy DSL definition.", runner.validate_strategy, ()),
        ("latest_strategy_gate_report", RESEARCH, READ_ONLY, "Return latest Strategy Evaluation Gate report.", runner.latest_strategy_gate_report, ()),
        ("run_research_pipeline", RESEARCH, OFFLINE_SIMULATION, "Run local offline research pipeline.", runner.run_research_pipeline, ()),
        ("run_strategy", RESEARCH, OFFLINE_SIMULATION, "Run a Strategy DSL definition through offline simulation.", runner.run_strategy, ()),
        ("run_strategy_gates", RESEARCH, OFFLINE_SIMULATION, "Run Strategy Evaluation Gates for an offline strategy.", runner.run_strategy_gates, ()),
        ("run_trade_sim", SIMULATION, OFFLINE_SIMULATION, "Run offline historical trading simulation.", runner.run_trade_sim, ()),
        ("trade_sim_summary", SIMULATION, READ_ONLY, "Return latest trade simulation report summary.", runner.trade_sim_summary, ()),
        ("export_for_agent", REPORTS, READ_ONLY, "Export an existing report for agent context.", runner.export_for_agent, ("report",)),
        ("get_latest_reports", REPORTS, READ_ONLY, "List latest JSON report paths.", runner.get_latest_reports, ()),
        ("get_report_summary", REPORTS, READ_ONLY, "Return compact summary for a report.", runner.get_report_summary, ("report",)),
        ("list_visualizations", VISUALIZATION, READ_ONLY, "List generated visualization artifacts.", runner.list_visualizations, ()),
        ("visualization_summary", VISUALIZATION, READ_ONLY, "Summarize visualization artifacts.", runner.visualization_summary, ()),
    ]:
        registry.register(_tool(name, category, capability, description, handler, required))
    for name in sorted(FORBIDDEN_TOOL_NAMES):
        registry.register(_tool(name, SECURITY, LIVE_TRADING_FORBIDDEN, "Forbidden live trading or broker action.", runner.not_supported, ()))
    return registry


def _tool(name: str, category: str, capability_level: str, description: str, handler, required: tuple[str, ...]) -> MCPTool:
    return MCPTool(
        metadata=MCPToolMetadata(
            name=name,
            category=category,
            capability_level=capability_level,
            description=description,
            arguments=object_schema(required=list(required)),
            return_schema=response_schema(description),
        ),
        handler=handler,
        required_arguments=required,
    )


def _read_only(name: str) -> bool:
    return name not in {"run_research_pipeline", "run_strategy", "run_strategy_gates", "run_trade_sim"}
