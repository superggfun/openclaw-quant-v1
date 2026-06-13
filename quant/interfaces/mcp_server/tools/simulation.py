"""Simulation MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import OFFLINE_SIMULATION, READ_ONLY
from quant.interfaces.mcp_server.tool_categories import SIMULATION
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


MCP_TOOL_SPECS = (
    MCPToolSpec("run_trade_sim", SIMULATION, OFFLINE_SIMULATION, "Run offline historical trading simulation.", "run_trade_sim"),
    MCPToolSpec("trade_sim_summary", SIMULATION, READ_ONLY, "Return latest trade simulation report summary.", "trade_sim_summary"),
)
