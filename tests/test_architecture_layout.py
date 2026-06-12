from __future__ import annotations

from pathlib import Path

from quant.cli import COMMAND_HANDLERS, build_parser
from tools.project_audit import ignored_generated_paths


def test_layered_imports_resolve_to_existing_implementations() -> None:
    from quant.agent_export.agent_exporter import AgentExporter as OldAgentExporter
    from quant.alpha.alpha_engine import AlphaEngine as OldAlphaEngine
    from quant.core.protocols.account import AccountState
    from quant.core_protocols.account import AccountState as OldAccountState
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.data.layer.data_quality import DataQualityAnalyzer
    from quant.data.layer.universe_manager import UniverseManager
    from quant.data.providers.provider_registry import ProviderRegistry
    from quant.data_layer.data_quality import DataQualityAnalyzer as OldDataQualityAnalyzer
    from quant.data_layer.universe_manager import UniverseManager as OldUniverseManager
    from quant.data_providers.provider_registry import ProviderRegistry as OldProviderRegistry
    from quant.engines.alpha.alpha_engine import AlphaEngine
    from quant.engines.factor_backtest.factor_backtest import FactorBacktest
    from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
    from quant.engines.multi_factor.multi_factor_model import MultiFactorModel
    from quant.engines.portfolio.portfolio_construction import PortfolioConstructionEngine
    from quant.engines.regime.regime_detector import RegimeDetector
    from quant.engines.trading_simulation.trading_simulator import TradingSimulator
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine
    from quant.factor_backtest.factor_backtest import FactorBacktest as OldFactorBacktest
    from quant.factor_eval.factor_evaluation import FactorEvaluation as OldFactorEvaluation
    from quant.factors.factor_registry import FactorRegistry as OldFactorRegistry
    from quant.factors.price.factor_registry import FactorRegistry
    from quant.factors.store.factor_store import FactorStore
    from quant.factor_store.factor_store import FactorStore as OldFactorStore
    from quant.fundamental_data.fundamental_store import FundamentalStore as OldFundamentalStore
    from quant.interfaces.cli_commands.alpha import handle as LayeredAlphaHandle
    from quant.cli_commands.alpha import handle as OldAlphaHandle
    from quant.multi_factor.multi_factor_model import MultiFactorModel as OldMultiFactorModel
    from quant.portfolio_construction.portfolio_construction import (
        PortfolioConstructionEngine as OldPortfolioConstructionEngine,
    )
    from quant.regime_detection.regime_detector import RegimeDetector as OldRegimeDetector
    from quant.reports.agent_export.agent_exporter import AgentExporter
    from quant.reports.visualization.report_visualizer import ReportVisualizer
    from quant.trading_simulation.trading_simulator import TradingSimulator as OldTradingSimulator
    from quant.visualization.report_visualizer import ReportVisualizer as OldReportVisualizer
    from quant.walk_forward.walk_forward import WalkForwardEngine as OldWalkForwardEngine

    assert AccountState is OldAccountState
    assert AlphaEngine is OldAlphaEngine
    assert AgentExporter is OldAgentExporter
    assert FactorBacktest is OldFactorBacktest
    assert FactorEvaluation is OldFactorEvaluation
    assert FactorRegistry is OldFactorRegistry
    assert FactorStore is OldFactorStore
    assert FundamentalStore is OldFundamentalStore
    assert MultiFactorModel is OldMultiFactorModel
    assert PortfolioConstructionEngine is OldPortfolioConstructionEngine
    assert ProviderRegistry is OldProviderRegistry
    assert RegimeDetector is OldRegimeDetector
    assert ReportVisualizer is OldReportVisualizer
    assert TradingSimulator is OldTradingSimulator
    assert UniverseManager is OldUniverseManager
    assert WalkForwardEngine is OldWalkForwardEngine
    assert DataQualityAnalyzer is OldDataQualityAnalyzer
    assert LayeredAlphaHandle is OldAlphaHandle


def test_reserved_interface_and_adapter_packages_are_importable() -> None:
    import quant.adapters.langchain
    import quant.adapters.openclaw
    import quant.adapters.pyfolio
    import quant.adapters.quantstats
    import quant.interfaces.api
    import quant.interfaces.mcp_server

    assert "research" in (quant.interfaces.mcp_server.__doc__ or "").lower()
    assert "future" in (quant.adapters.openclaw.__doc__ or "").lower()


def test_cli_still_registers_existing_commands() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    assert set(subparsers_action.choices) == set(COMMAND_HANDLERS)
    assert "research-run" in COMMAND_HANDLERS
    assert "visualize-report" in COMMAND_HANDLERS


def test_generated_paths_remain_ignored() -> None:
    ignored = ignored_generated_paths(
        [
            "data/quant.db",
            "reports/example.json",
            "reports/charts/example.png",
            "reports/agent_summary.md",
            "reports/agent_export_example.md",
            "examples/portfolio_constructed_targets.json",
        ]
    )

    assert all(ignored.values())


def test_layered_package_directories_exist() -> None:
    root = Path(__file__).resolve().parents[1] / "quant"

    for relative in [
        "core/protocols",
        "data/providers",
        "data/layer",
        "data/fundamental",
        "factors/price",
        "factors/fundamental",
        "factors/store",
        "engines/alpha",
        "reports/agent_export",
        "interfaces/cli_commands",
        "adapters/openclaw",
    ]:
        assert (root / relative / "__init__.py").exists()
