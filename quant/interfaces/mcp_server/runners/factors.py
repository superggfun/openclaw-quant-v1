"""Factor MCP runner methods."""

from __future__ import annotations

from typing import Any

from quant.factors.price.factor_registry import FactorRegistry


class FactorMCPRunner:
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
