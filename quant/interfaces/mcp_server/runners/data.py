"""Data MCP runner methods."""

from __future__ import annotations

from typing import Any


class DataMCPRunner:
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
