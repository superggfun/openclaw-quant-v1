"""Data MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import READ_ONLY
from quant.interfaces.mcp_server.tool_categories import DATA
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


MCP_TOOL_SPECS = (
    MCPToolSpec("get_provider_status", DATA, READ_ONLY, "List data providers and health status.", "get_provider_status"),
    MCPToolSpec("get_data_coverage", DATA, READ_ONLY, "Return stored price coverage for a universe.", "get_data_coverage"),
    MCPToolSpec(
        "get_fundamental_coverage",
        DATA,
        READ_ONLY,
        "Return fundamental data coverage for a universe.",
        "get_fundamental_coverage",
    ),
    MCPToolSpec("get_universe_summary", DATA, READ_ONLY, "Return available universes and selected symbols.", "get_universe_summary"),
)
