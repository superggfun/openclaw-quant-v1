"""Auto-discovery for MCP tool specs."""

from __future__ import annotations

import importlib
import pkgutil

from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


def discover_mcp_tool_specs(package_name: str = "quant.interfaces.mcp_server.tools") -> tuple[MCPToolSpec, ...]:
    package = importlib.import_module(package_name)
    specs: list[MCPToolSpec] = []
    seen: set[str] = set()

    for module_info in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
        module = importlib.import_module(module_info.name)
        module_specs = getattr(module, "MCP_TOOL_SPECS", ())
        for spec in module_specs:
            if not isinstance(spec, MCPToolSpec):
                raise TypeError(f"{module_info.name}.MCP_TOOL_SPECS must contain MCPToolSpec objects")
            if spec.name in seen:
                raise ValueError(f"duplicate MCP tool spec registered: {spec.name}")
            seen.add(spec.name)
            specs.append(spec)

    return tuple(specs)
