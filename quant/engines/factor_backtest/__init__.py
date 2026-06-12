"""Factor backtest engine layered namespace."""

from quant.factor_backtest import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(__name__, {"factor_backtest": "quant.factor_backtest.factor_backtest"})

