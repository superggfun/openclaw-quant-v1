"""Historical trading simulation engine layered namespace."""

from quant.trading_simulation import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "portfolio_account": "quant.trading_simulation.portfolio_account",
        "trading_simulator": "quant.trading_simulation.trading_simulator",
    },
)

