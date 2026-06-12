"""Execution, cost, and market realism layered namespace."""

from quant.execution import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "execution_engine": "quant.execution.execution_engine",
        "cost_engine": "quant.cost.cost_engine",
        "execution_constraints": "quant.market_realism.execution_constraints",
        "liquidity_model": "quant.market_realism.liquidity_model",
        "marketability": "quant.market_realism.marketability",
        "slippage_model": "quant.market_realism.slippage_model",
    },
)

