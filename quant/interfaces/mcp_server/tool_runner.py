"""Safe MCP tool runner facade over domain-specific runner mixins."""

from __future__ import annotations

from quant.interfaces.mcp_server.runners.base import BaseMCPRunner
from quant.interfaces.mcp_server.runners.data import DataMCPRunner
from quant.interfaces.mcp_server.runners.factors import FactorMCPRunner
from quant.interfaces.mcp_server.runners.regimes import RegimeMCPRunner
from quant.interfaces.mcp_server.runners.reports import ReportMCPRunner
from quant.interfaces.mcp_server.runners.research import ResearchMCPRunner
from quant.interfaces.mcp_server.runners.simulation import SimulationMCPRunner
from quant.interfaces.mcp_server.runners.visualization import VisualizationMCPRunner


class MCPToolRunner(
    DataMCPRunner,
    FactorMCPRunner,
    RegimeMCPRunner,
    ResearchMCPRunner,
    SimulationMCPRunner,
    ReportMCPRunner,
    VisualizationMCPRunner,
    BaseMCPRunner,
):
    """Run read-only or offline-simulation tools without broker side effects."""
