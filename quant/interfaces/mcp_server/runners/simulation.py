"""Simulation MCP runner methods."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quant.cli_commands.common import load_alpha_config, load_cost_config, load_market_realism_config


class SimulationMCPRunner:
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
