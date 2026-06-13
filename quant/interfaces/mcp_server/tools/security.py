"""Disabled live-trading MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import LIVE_TRADING_FORBIDDEN
from quant.interfaces.mcp_server.tool_categories import SECURITY
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


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

MCP_TOOL_SPECS = tuple(
    MCPToolSpec(name, SECURITY, LIVE_TRADING_FORBIDDEN, "Forbidden live trading or broker action.", "not_supported")
    for name in sorted(FORBIDDEN_TOOL_NAMES)
)
