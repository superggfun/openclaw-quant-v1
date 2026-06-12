"""CLI command layered namespace."""

from quant.cli_commands import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "agent_export": "quant.cli_commands.agent_export",
        "alpha": "quant.cli_commands.alpha",
        "backtest": "quant.cli_commands.backtest",
        "common": "quant.cli_commands.common",
        "cost": "quant.cli_commands.cost",
        "data": "quant.cli_commands.data",
        "data_layer": "quant.cli_commands.data_layer",
        "execution": "quant.cli_commands.execution",
        "factor_backtest": "quant.cli_commands.factor_backtest",
        "factor_eval": "quant.cli_commands.factor_eval",
        "factor_library": "quant.cli_commands.factor_library",
        "factor_pipeline": "quant.cli_commands.factor_pipeline",
        "factor_store": "quant.cli_commands.factor_store",
        "fundamental_data": "quant.cli_commands.fundamental_data",
        "optimize": "quant.cli_commands.optimize",
        "portfolio": "quant.cli_commands.portfolio",
        "portfolio_construction": "quant.cli_commands.portfolio_construction",
        "providers": "quant.cli_commands.providers",
        "rebalance": "quant.cli_commands.rebalance",
        "regime": "quant.cli_commands.regime",
        "risk": "quant.cli_commands.risk",
        "research_validation": "quant.cli_commands.research_validation",
        "scheduler": "quant.cli_commands.scheduler",
        "strategy_gates": "quant.cli_commands.strategy_gates",
        "strategy_eval": "quant.cli_commands.strategy_eval",
        "trading_simulation": "quant.cli_commands.trading_simulation",
        "visualization": "quant.cli_commands.visualization",
        "walk_forward": "quant.cli_commands.walk_forward",
    },
)
