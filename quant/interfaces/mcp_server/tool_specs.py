"""Declarative MCP tool specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant.interfaces.mcp_server.mcp_models import MCPTool, MCPToolMetadata
from quant.interfaces.mcp_server.tool_schemas import object_schema, response_schema


@dataclass(frozen=True)
class MCPToolSpec:
    name: str
    category: str
    capability_level: str
    description: str
    handler_name: str
    required_arguments: tuple[str, ...] = ()

    def bind(self, runner: Any) -> MCPTool:
        return MCPTool(
            metadata=MCPToolMetadata(
                name=self.name,
                category=self.category,
                capability_level=self.capability_level,
                description=self.description,
                arguments=object_schema(required=list(self.required_arguments)),
                return_schema=response_schema(self.description),
            ),
            handler=getattr(runner, self.handler_name),
            required_arguments=self.required_arguments,
        )
