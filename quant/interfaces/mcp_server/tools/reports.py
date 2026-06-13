"""Report MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import READ_ONLY
from quant.interfaces.mcp_server.tool_categories import REPORTS
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


MCP_TOOL_SPECS = (
    MCPToolSpec("export_for_agent", REPORTS, READ_ONLY, "Export an existing report for agent context.", "export_for_agent", ("report",)),
    MCPToolSpec("get_latest_reports", REPORTS, READ_ONLY, "List latest JSON report paths.", "get_latest_reports"),
    MCPToolSpec("get_report_summary", REPORTS, READ_ONLY, "Return compact summary for a report.", "get_report_summary", ("report",)),
)
