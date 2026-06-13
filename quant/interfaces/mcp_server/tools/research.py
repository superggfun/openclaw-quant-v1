"""Research MCP tool specs."""

from __future__ import annotations

from quant.interfaces.mcp_server.capabilities import OFFLINE_SIMULATION, READ_ONLY
from quant.interfaces.mcp_server.tool_categories import RESEARCH
from quant.interfaces.mcp_server.tool_specs import MCPToolSpec


MCP_TOOL_SPECS = (
    MCPToolSpec("research_status", RESEARCH, READ_ONLY, "Return latest research run status.", "research_status"),
    MCPToolSpec("research_history", RESEARCH, READ_ONLY, "Return recent research run history.", "research_history"),
    MCPToolSpec("research_report", RESEARCH, READ_ONLY, "Return latest or selected research run report.", "research_report"),
    MCPToolSpec("list_strategies", RESEARCH, READ_ONLY, "List Strategy DSL definitions.", "list_strategies"),
    MCPToolSpec("show_strategy", RESEARCH, READ_ONLY, "Show a Strategy DSL definition.", "show_strategy"),
    MCPToolSpec("validate_strategy", RESEARCH, READ_ONLY, "Validate a Strategy DSL definition.", "validate_strategy"),
    MCPToolSpec(
        "latest_strategy_gate_report",
        RESEARCH,
        READ_ONLY,
        "Return latest Strategy Evaluation Gate report.",
        "latest_strategy_gate_report",
    ),
    MCPToolSpec(
        "run_research_pipeline",
        RESEARCH,
        OFFLINE_SIMULATION,
        "Run local offline research pipeline.",
        "run_research_pipeline",
    ),
    MCPToolSpec(
        "run_strategy",
        RESEARCH,
        OFFLINE_SIMULATION,
        "Run a Strategy DSL definition through offline simulation.",
        "run_strategy",
    ),
    MCPToolSpec(
        "run_strategy_gates",
        RESEARCH,
        OFFLINE_SIMULATION,
        "Run Strategy Evaluation Gates for an offline strategy.",
        "run_strategy_gates",
    ),
)
