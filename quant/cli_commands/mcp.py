"""MCP-compatible research interface CLI commands."""

from __future__ import annotations

import argparse
import json

from quant.cli_commands.common import CLIContext
from quant.interfaces.mcp_server.mcp_models import MCPRequest
from quant.interfaces.mcp_server.tool_registry import FORBIDDEN_TOOL_NAMES, create_default_mcp_registry


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    list_tools = subparsers.add_parser("mcp-list-tools", help="List safe MCP research tools.")
    list_tools.add_argument("--category", default=None)

    info = subparsers.add_parser("mcp-tool-info", help="Show MCP tool metadata.")
    info.add_argument("tool", nargs="?", default=None)

    subparsers.add_parser("mcp-smoke", help="Run a safe MCP interface smoke test.")


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    registry = create_default_mcp_registry()
    if args.command == "mcp-list-tools":
        tools = registry.list_tools(category=args.category)
        print("MCP Tools")
        print("name category capability_level version description")
        for tool in tools:
            print(f"{tool['name']} {tool['category']} {tool['capability_level']} {tool['version']} {tool['description']}")
        print(f"tool_count: {len(tools)}")
        categories = registry.list_categories()
        for category, count in categories.items():
            print(f"category {category}: {count}")
        for capability, count in registry.list_capabilities().items():
            print(f"capability {capability}: {count}")
        return 0

    if args.command == "mcp-tool-info":
        if args.tool:
            tools = [registry.lookup(args.tool).metadata.to_dict()]
        else:
            tools = registry.list_tools()
        print("MCP Tool Info")
        for tool in tools:
            print(json.dumps(tool, indent=2, sort_keys=True))
        return 0

    if args.command == "mcp-smoke":
        smoke_tools = [
            MCPRequest("get_provider_status"),
            MCPRequest("list_factors"),
            MCPRequest("research_status"),
            MCPRequest("get_latest_reports", {"limit": 3}),
            MCPRequest("place_order", {"symbol": "SPY", "quantity": 1}),
        ]
        print("MCP Smoke")
        failures = 0
        for request in smoke_tools:
            response = registry.execute(request, context)
            if response.status == "ERROR":
                failures += 1
            print(f"{request.tool_name}: {response.status}")
            if response.error:
                print(f"  error: {response.error}")
            if response.warnings:
                print(f"  warnings: {', '.join(response.warnings)}")
        blocked = registry.execute(MCPRequest("execute_trade"), context)
        print(f"unsupported_tools_blocked: {blocked.status.startswith('NOT_SUPPORTED')}")
        print(f"forbidden_tool_count: {len(FORBIDDEN_TOOL_NAMES)}")
        return 1 if failures else 0

    raise ValueError(f"unsupported MCP command: {args.command}")
