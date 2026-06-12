"""Local MCP-compatible server facade.

This is an in-process facade, not a network daemon.
"""

from __future__ import annotations

from quant.interfaces.mcp_server.mcp_models import MCPRequest, MCPResponse
from quant.interfaces.mcp_server.tool_registry import MCPToolRegistry, create_default_mcp_registry


class LocalMCPServer:
    """Execute registered MCP tools against an existing CLI context."""

    def __init__(self, context, registry: MCPToolRegistry | None = None) -> None:
        self.context = context
        self.registry = registry or create_default_mcp_registry()

    def list_tools(self) -> list[dict]:
        return self.registry.list_tools()

    def execute(self, tool_name: str, arguments: dict | None = None, request_id: str | None = None) -> MCPResponse:
        return self.registry.execute(MCPRequest(tool_name=tool_name, arguments=arguments or {}, request_id=request_id), self.context)
