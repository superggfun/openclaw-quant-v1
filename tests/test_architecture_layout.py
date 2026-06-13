from __future__ import annotations

from pathlib import Path

from quant.cli import COMMAND_HANDLERS, build_parser
from tools.project_audit import ignored_generated_paths


def test_layered_imports_resolve_to_existing_implementations() -> None:
    from quant.core.protocols.account import AccountState
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.data.layer.data_quality import DataQualityAnalyzer
    from quant.data.layer.universe_manager import UniverseManager
    from quant.data.providers.provider_registry import ProviderRegistry
    from quant.engines.alpha.alpha_engine import AlphaEngine
    from quant.engines.factor_backtest.factor_backtest import FactorBacktest
    from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
    from quant.engines.multi_factor.multi_factor_model import MultiFactorModel
    from quant.engines.portfolio.portfolio_construction import PortfolioConstructionEngine
    from quant.engines.regime.regime_detector import RegimeDetector
    from quant.engines.strategy_gates.gate_runner import StrategyGateRunner
    from quant.engines.trading_simulation.trading_simulator import TradingSimulator
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine
    from quant.factors.price.factor_registry import FactorRegistry
    from quant.factors.store.factor_store import FactorStore
    from quant.cli_commands.alpha import handle as AlphaHandle
    from quant.reports.agent_export.agent_exporter import AgentExporter
    from quant.reports.visualization.report_visualizer import ReportVisualizer

    assert AccountState.__name__ == "AccountState"
    assert AlphaEngine.__name__ == "AlphaEngine"
    assert AgentExporter.__name__ == "AgentExporter"
    assert DataQualityAnalyzer.__name__ == "DataQualityAnalyzer"
    assert FactorBacktest.__name__ == "FactorBacktest"
    assert FactorEvaluation.__name__ == "FactorEvaluation"
    assert FactorRegistry.__name__ == "FactorRegistry"
    assert FactorStore.__name__ == "FactorStore"
    assert FundamentalStore.__name__ == "FundamentalStore"
    assert MultiFactorModel.__name__ == "MultiFactorModel"
    assert PortfolioConstructionEngine.__name__ == "PortfolioConstructionEngine"
    assert ProviderRegistry.__name__ == "ProviderRegistry"
    assert RegimeDetector.__name__ == "RegimeDetector"
    assert ReportVisualizer.__name__ == "ReportVisualizer"
    assert StrategyGateRunner.__name__ == "StrategyGateRunner"
    assert TradingSimulator.__name__ == "TradingSimulator"
    assert UniverseManager.__name__ == "UniverseManager"
    assert WalkForwardEngine.__name__ == "WalkForwardEngine"
    assert callable(AlphaHandle)


def test_unimplemented_extension_namespaces_are_not_precreated() -> None:
    import quant.interfaces.mcp_server

    root = Path(__file__).resolve().parents[1] / "quant"

    assert "research" in (quant.interfaces.mcp_server.__doc__ or "").lower()
    assert not (root / "adapters").exists()
    assert not (root / "interfaces" / "api").exists()
    assert not (root / "openclaw").exists()
    assert not (root / "portfolio").exists()


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
        "engines/strategy_gates",
        "reports/agent_export",
    ]:
        assert (root / relative / "__init__.py").exists()
