"""Visualization MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import READ_ONLY
from quant.interfaces.mcp_server.tool_categories import VISUALIZATION
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


MCP_TOOL_SPECS = (
    MCPToolSpec("list_visualizations", VISUALIZATION, READ_ONLY, "List generated visualization artifacts.", "list_visualizations"),
    MCPToolSpec("visualization_summary", VISUALIZATION, READ_ONLY, "Summarize visualization artifacts.", "visualization_summary"),
)
