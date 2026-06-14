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
        include_obs = bool(arguments.get("include_observations", False))
        result = context.factor_evaluation.evaluate(
            factor=str(arguments["factor"]),
            start=arguments.get("start"),
            end=arguments.get("end"),
            forward_days=int(arguments.get("forward_days", 20)),
            pipeline_config=None,
            write_report=bool(arguments.get("write_report", False)),
        )
        return result.to_mcp_response(include_observations=include_obs)

    def test_factor(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        """Run factor evaluation + backtest and return compact result with score."""
        from quant.engines.output_modes import score_factor
        include_obs = bool(arguments.get("include_observations", False))
        write_rpt = bool(arguments.get("write_report", False))

        eval_result = context.factor_evaluation.evaluate(
            factor=str(arguments["factor"]),
            start=arguments.get("start"),
            end=arguments.get("end"),
            forward_days=int(arguments.get("forward_days", 20)),
            pipeline_config=None,
            write_report=write_rpt,
        )
        backtest_result = context.factor_backtest_engine.run(
            factor=str(arguments["factor"]),
            start=arguments.get("start"),
            end=arguments.get("end"),
            holding_period=int(arguments.get("holding_period", 20)),
            write_report=write_rpt,
        )

        eval_summary = eval_result.to_summary(include_observations=include_obs)
        bt_summary = backtest_result.to_summary(include_observations=include_obs)
        scoring = score_factor(eval_summary, bt_summary)

        return {
            "factor": eval_summary["factor"],
            "status": scoring["status"],
            "score": scoring["score"],
            "metrics": {
                "ic_mean": eval_summary.get("ic_mean"),
                "rank_ic_mean": eval_summary.get("rank_ic_mean"),
                "icir": eval_summary.get("icir"),
                "decay": eval_summary.get("decay"),
                "total_return": bt_summary.get("total_return"),
                "annualized_return": bt_summary.get("annualized_return"),
                "sharpe": bt_summary.get("sharpe"),
                "max_drawdown": bt_summary.get("max_drawdown"),
                "turnover": bt_summary.get("turnover"),
                "long_short_return": bt_summary.get("long_short_return"),
                "long_leg_return": bt_summary.get("long_leg_return"),
                "short_leg_return": bt_summary.get("short_leg_return"),
            },
            "decision": {
                "useful": scoring["status"] == "PASS",
                "reason": scoring["reason"],
            },
            "scoring": scoring,
            "warnings": eval_summary.get("warnings", []),
            "metadata": {
                "bulk_matrix_enabled": (
                    (eval_summary.get("performance_metadata") or {}).get("bulk_matrix_enabled", True)
                ),
                "serial_reference": False,
                "provider_type": (
                    (eval_summary.get("performance_metadata") or {}).get("provider_type")
                ),
                "fallback_used": (
                    (eval_summary.get("performance_metadata") or {}).get("fallback_used", False)
                ),
                "runtime_seconds": (
                    (eval_summary.get("performance_metadata") or {}).get("eval_seconds", 0.0)
                ),
            },
        }
