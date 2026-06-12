"""Safe MCP tool implementations over existing offline engines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant.cli_commands.common import load_alpha_config, load_cost_config, load_market_realism_config
from quant.config import DEFAULT_SYMBOLS
from quant.factors.factor_registry import FactorRegistry
from quant.scheduler.research_scheduler import ResearchScheduler
from quant.strategy_dsl.strategy_registry import StrategyRegistry


class MCPToolRunner:
    """Run read-only or offline-simulation tools without broker side effects."""

    def get_provider_status(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        providers = []
        for item in context.provider_registry.list_providers():
            provider = context.provider_registry.resolve(item.name)
            providers.append(item.__dict__ | {"health": provider.health_check().to_dict()})
        return {"providers": providers, "default_provider": context.provider_registry.default_name}

    def get_data_coverage(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        symbols = self._symbols(arguments)
        return context.data_quality_analyzer.coverage(symbols)

    def get_fundamental_coverage(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        symbols = self._symbols(arguments)
        return context.fundamental_service.coverage(symbols, parameters={"source": "mcp", "symbols": symbols})

    def get_universe_summary(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        universe = arguments.get("universe") or "default_universe"
        result = context.universe_manager.build_universe(
            symbols=arguments.get("symbols"),
            sector=arguments.get("sector"),
            universe=universe,
            max_symbols=arguments.get("max_symbols"),
        )
        return {
            "universes": context.universe_manager.list_universes(),
            "selected_symbols": result.selected_symbols,
            "excluded_symbols": result.excluded_symbols,
            "exclusion_reasons": result.exclusion_reasons,
            "universe_type": result.universe_type,
        }

    def list_factors(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        registry = FactorRegistry(context.fundamental_store)
        return {
            "factors": [
                registry.metadata(definition.name) | {"factor_name": definition.name}
                for definition in registry.list_factors()
            ]
        }

    def factor_history(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return context.factor_store.factor_history(factor=arguments.get("factor"), limit=int(arguments.get("limit", 20)))

    def factor_rank(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return context.factor_store.rank_factors(limit=int(arguments.get("limit", 10)))

    def factor_store_summary(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return context.factor_store.summary()

    def evaluate_factor(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        result = context.factor_evaluation.evaluate(
            factor=str(arguments["factor"]),
            start=arguments.get("start"),
            end=arguments.get("end"),
            forward_days=int(arguments.get("forward_days", 20)),
            pipeline_config=None,
        )
        return result.to_report()

    def detect_regime(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        if arguments.get("benchmark"):
            context.regime_detector.benchmark = str(arguments["benchmark"]).upper()
        return context.regime_analytics.detect_and_save(start=arguments.get("start"), end=arguments.get("end"))

    def regime_history(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return context.regime_analytics.history_report(limit=int(arguments.get("limit", 30)), regime=arguments.get("regime"))

    def regime_report(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        self._ensure_regime_history(context, bool(arguments.get("ensure_history", True)))
        return context.regime_analytics.regime_report()

    def regime_rank(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        self._ensure_regime_history(context, bool(arguments.get("ensure_history", True)))
        return context.regime_analytics.regime_rank(limit=int(arguments.get("limit", 10)))

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

    def run_trade_sim(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        result = context.trading_simulator.run(
            strategy=str(arguments.get("strategy", "alpha")),
            start=str(arguments.get("start", "2024-01-01")),
            end=str(arguments.get("end", "2025-01-01")),
            initial_cash=float(arguments.get("initial_cash", 100000.0)),
            rebalance_frequency=str(arguments.get("rebalance_frequency", "monthly")),
            portfolio_method=str(arguments.get("portfolio_method", "equal_weight")),
            cost_config=load_cost_config(Path(arguments.get("cost_config", "examples/cost_config.json"))),
            market_realism_config=load_market_realism_config(Path(arguments.get("market_realism_config", "examples/market_realism_config.json"))),
            alpha_config=load_alpha_config(Path(arguments.get("alpha_config", "examples/alpha_config.json"))),
            symbols=arguments.get("symbols"),
        )
        return result.to_report()

    def trade_sim_summary(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        report = self._latest_report("trade_sim_*.json")
        if not report:
            return {"status": "NO_REPORTS", "warnings": ["NO_TRADE_SIM_REPORTS"]}
        payload = self._load_json(report)
        return {
            "report_path": str(report),
            "strategy": payload.get("strategy"),
            "portfolio_method": payload.get("portfolio_method"),
            "final_equity": payload.get("final_equity"),
            "total_return": payload.get("total_return"),
            "max_drawdown": payload.get("max_drawdown"),
            "total_cost": payload.get("total_cost"),
            "trade_count": payload.get("trade_count"),
            "warnings": payload.get("warnings") or [],
        }

    def export_for_agent(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        report = arguments["report"]
        output_format = arguments.get("format", "json")
        rendered = context.agent_exporter.export_file(report, output_format=output_format, max_tokens=int(arguments.get("max_tokens", 800)))
        if output_format == "json":
            return json.loads(rendered)
        return {"summary": rendered, "report_path": str(report)}

    def get_latest_reports(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        limit = int(arguments.get("limit", 10))
        report_type = arguments.get("report_type")
        pattern = f"{report_type}_*.json" if report_type else "*.json"
        reports = sorted(Path("reports").glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]
        return {"reports": [str(path) for path in reports], "count": len(reports)}

    def get_report_summary(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        rendered = context.agent_exporter.export_file(arguments["report"], output_format="json", max_tokens=int(arguments.get("max_tokens", 800)))
        return json.loads(rendered)

    def list_visualizations(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        root = Path(arguments.get("charts_dir", "reports/charts"))
        files = sorted(path for path in root.glob("*") if path.is_file()) if root.exists() else []
        return {"charts_dir": str(root), "visualizations": [str(path) for path in files], "count": len(files)}

    def visualization_summary(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        listing = self.list_visualizations(arguments, context)
        by_suffix: dict[str, int] = {}
        for path in listing["visualizations"]:
            suffix = Path(path).suffix.lower() or "<none>"
            by_suffix[suffix] = by_suffix.get(suffix, 0) + 1
        return listing | {"by_suffix": by_suffix}

    def not_supported(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return {"status": "NOT_SUPPORTED"}

    @staticmethod
    def _symbols(arguments: dict[str, Any]) -> list[str]:
        raw = arguments.get("symbols")
        if raw is None:
            return list(DEFAULT_SYMBOLS)
        if isinstance(raw, str):
            return [symbol.strip().upper() for symbol in raw.replace(",", " ").split() if symbol.strip()]
        return [str(symbol).strip().upper() for symbol in raw if str(symbol).strip()]

    @staticmethod
    def _ensure_regime_history(context, enabled: bool) -> None:
        if enabled and context.regime_history_store.latest() is None:
            context.regime_analytics.detect_and_save()

    @staticmethod
    def _latest_report(pattern: str) -> Path | None:
        reports = sorted(Path("reports").glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
        return reports[0] if reports else None

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
