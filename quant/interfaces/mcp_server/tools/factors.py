"""Factor MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import READ_ONLY
from quant.interfaces.mcp_server.tool_categories import FACTORS
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


MCP_TOOL_SPECS = (
    MCPToolSpec("list_factors", FACTORS, READ_ONLY, "List registered factor metadata.", "list_factors"),
    MCPToolSpec("factor_history", FACTORS, READ_ONLY, "Return persisted factor history.", "factor_history"),
    MCPToolSpec("factor_rank", FACTORS, READ_ONLY, "Return persisted factor ranking diagnostics.", "factor_rank"),
    MCPToolSpec("factor_store_summary", FACTORS, READ_ONLY, "Return factor store table counts and definitions.", "factor_store_summary"),
    MCPToolSpec("evaluate_factor", FACTORS, READ_ONLY, "Run no-lookahead factor evaluation.", "evaluate_factor", ("factor",)),
)
