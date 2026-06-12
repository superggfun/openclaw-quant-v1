"""Safe MCP-compatible research interface.

The v0.35 interface is local, JSON-safe, and research-only. It does not expose
live trading, broker connectivity, or order submission.
"""

from quant.interfaces.mcp_server.mcp_models import MCPRequest, MCPResponse, MCPTool, MCPToolMetadata
from quant.interfaces.mcp_server.tool_registry import create_default_mcp_registry

__all__ = [
    "MCPRequest",
    "MCPResponse",
    "MCPTool",
    "MCPToolMetadata",
    "create_default_mcp_registry",
]

