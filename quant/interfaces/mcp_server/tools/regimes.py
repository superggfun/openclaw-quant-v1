"""Regime MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import READ_ONLY
from quant.interfaces.mcp_server.tool_categories import REGIMES
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


MCP_TOOL_SPECS = (
    MCPToolSpec("detect_regime", REGIMES, READ_ONLY, "Detect deterministic current market regime.", "detect_regime"),
    MCPToolSpec("regime_history", REGIMES, READ_ONLY, "Return persisted regime history.", "regime_history"),
    MCPToolSpec("regime_report", REGIMES, READ_ONLY, "Return regime diagnostics.", "regime_report"),
    MCPToolSpec("regime_rank", REGIMES, READ_ONLY, "Return factor rankings by regime.", "regime_rank"),
)
