"""Registry for safe MCP research tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant.interfaces.mcp_server.capabilities import (
    READ_ONLY,
    disabled_status,
    is_enabled,
)
from quant.interfaces.mcp_server.mcp_models import MCPRequest, MCPResponse, MCPTool, json_safe
from quant.interfaces.mcp_server.tool_discovery import discover_mcp_tool_specs
from quant.interfaces.mcp_server.tool_runner import MCPToolRunner
from quant.interfaces.mcp_server.tools.security import FORBIDDEN_TOOL_NAMES


@dataclass
class MCPToolRegistry:
    """Register, inspect, and execute safe MCP tools."""

    tools: dict[str, MCPTool]

    def register(self, tool: MCPTool) -> None:
        self.tools[tool.metadata.name] = tool

    def lookup(self, name: str) -> MCPTool:
        normalized = name.strip()
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
            metadata={
                "version": tool.metadata.version,
                "read_only": tool.metadata.capability_level == READ_ONLY,
                "offline_only": True,
            },
            request_id=request.request_id,
        )


def create_default_mcp_registry() -> MCPToolRegistry:
    runner = MCPToolRunner()
    registry = MCPToolRegistry(tools={})
    for spec in discover_mcp_tool_specs():
        registry.register(spec.bind(runner))
    return registry
