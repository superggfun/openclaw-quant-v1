"""Research and Strategy DSL MCP runner methods."""

from __future__ import annotations

from typing import Any

from quant.scheduler.research_scheduler import ResearchScheduler
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.engines.strategy_gates.gate_runner import StrategyGateRunner


class ResearchMCPRunner:
    def research_status(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return ResearchScheduler(context, context.db_path).status()

    def research_history(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return ResearchScheduler(context, context.db_path).history(limit=int(arguments.get("limit", 20)))

    def research_report(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return ResearchScheduler(context, context.db_path).latest_report(run_id=arguments.get("run_id"))

    def list_strategies(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return StrategyRegistry(context, strategy_dir=arguments.get("strategy_dir", "strategies")).list_strategies()

    def show_strategy(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return StrategyRegistry(context, strategy_dir=arguments.get("strategy_dir", "strategies")).show(
            strategy=arguments.get("strategy", "momentum_fundamental"),
            file=arguments.get("file"),
        )

    def validate_strategy(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return StrategyRegistry(context, strategy_dir=arguments.get("strategy_dir", "strategies")).validate(
            strategy=arguments.get("strategy", "momentum_fundamental"),
            file=arguments.get("file"),
            write_report=bool(arguments.get("write_report", False)),
        )

    def run_research_pipeline(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        scheduler = ResearchScheduler(context, context.db_path)
        config_path = arguments.get("config") or "examples/research_scheduler_config.json"
        overrides = dict(arguments.get("overrides") or {})
        return scheduler.run(config_path=config_path, overrides=overrides)

    def run_strategy(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return StrategyRegistry(context, strategy_dir=arguments.get("strategy_dir", "strategies")).run(
            strategy=arguments.get("strategy", "momentum_fundamental"),
            file=arguments.get("file"),
            start=str(arguments.get("start", "2024-01-01")),
            end=str(arguments.get("end", "2025-01-01")),
            initial_cash=float(arguments.get("initial_cash", 100000.0)),
            rebalance_frequency=str(arguments.get("rebalance_frequency", "monthly")),
        )

    def run_strategy_gates(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return StrategyGateRunner(context, strategy_dir=arguments.get("strategy_dir", "strategies")).run(
            strategy=arguments.get("strategy", "momentum_fundamental"),
            file=arguments.get("file"),
            config_path=arguments.get("config", "examples/strategy_gate_config.json"),
        )

    def latest_strategy_gate_report(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return StrategyGateRunner(context, strategy_dir=arguments.get("strategy_dir", "strategies")).latest_report()
